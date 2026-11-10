"""Frozen disjoint fixtures and meaningful quality scoring: all-unknown cannot pass."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest

from src.core.content_classification import EmailClassification, EventClassification
from tests.fixtures.classification_corpus import Corpus, score

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).resolve().parents[4] / "fixtures"
CALIBRATION_SHA = "7dc6bdf6efdb3052d59e7d9ca08a4daed0dd56931fa298fa7ddaa0386d44ae9e"
HOLDOUT_SHA = "e51bf184eb0e7a253fa2a2e6dcca34be871dcaeb53fbf4d8da912e7fac0f7108"
ADVERSARIAL_SHA = "1c48e14a88847182c387e6bd7c967019e8c6321fd12ee7cf7180909ce4b34586"


@pytest.mark.parametrize("split,digest", [("cases", CALIBRATION_SHA), ("holdout", HOLDOUT_SHA)])
def test_corpus_is_frozen_and_covers_each_language_label_and_abstention(
    split: str, digest: str
) -> None:
    path = FIXTURES / f"jev_classification_{split}.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    corpus = Corpus.read(path)
    assert len({case.id for case in corpus.items}) == len(corpus.items)
    assert {case.language for case in corpus.items} == {
        "en",
        "fr",
        "de",
        "es",
        "it",
        "zh",
    }
    assert {case.expected_category for case in corpus.items} == {
        "unknown",
        "professional",
        "personal",
        "spam",
        "phishing_scam",
    }
    assert {case.expected_priority for case in corpus.items if case.kind == "email"} >= {
        "normal",
        "urgent",
        "critical",
        "unknown",
    }
    # Whether a reply is expected (lot F): both answers, and the undecidable left out.
    assert {case.expected_reply for case in corpus.items if case.kind == "email"} == {
        True,
        False,
        None,
    }
    assert all(case.expected_reply is None for case in corpus.items if case.kind == "event")
    assert not score(corpus, {}).passed
    assert score(corpus, {}).positive_coverage == 0


def test_holdout_has_no_duplicate_evidence_from_calibration() -> None:
    calibration, holdout = (
        Corpus.read(FIXTURES / f"jev_classification_{split}.json") for split in ("cases", "holdout")
    )
    fingerprints = {json.dumps(case.evidence, sort_keys=True) for case in calibration.items}
    assert not fingerprints.intersection(
        json.dumps(case.evidence, sort_keys=True) for case in holdout.items
    )


def test_post_freeze_adversarial_cases_are_frozen_multilingual_and_disjoint() -> None:
    path = FIXTURES / "jev_classification_adversarial.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ADVERSARIAL_SHA
    corpus = Corpus.read(path)
    assert len(corpus.items) == len({case.id for case in corpus.items}) == 36
    assert {case.language for case in corpus.items} == {"en", "fr", "de", "es", "it", "zh"}
    originals = {
        json.dumps(case.evidence, sort_keys=True)
        for split in ("cases", "holdout")
        for case in Corpus.read(FIXTURES / f"jev_classification_{split}.json").items
    }
    assert not originals.intersection(
        json.dumps(case.evidence, sort_keys=True) for case in corpus.items
    )
    assert not score(corpus, {}).passed


def test_quality_scoring_rejects_one_false_phishing_label_even_with_good_global_coverage() -> None:
    corpus = Corpus.read(FIXTURES / "jev_classification_cases.json")
    predictions = {}
    for case in corpus.items:
        fields = {
            "category": case.expected_category,
            "evidence_scope": case.evidence_scope,
            "evaluated_at": corpus.reference_time,
            "valid_until": corpus.reference_time + timedelta(seconds=30),
        }
        if case.kind == "email":
            predictions[case.id] = EmailClassification.model_validate(
                {
                    **fields,
                    "priority": case.expected_priority,
                    "reply_expected": case.expected_reply,
                }
            )
        else:
            predictions[case.id] = EventClassification.model_validate(fields)
    assert score(corpus, predictions).passed
    first = corpus.items[0]
    predictions[first.id] = predictions[first.id].model_copy(update={"category": "phishing_scam"})
    report = score(corpus, predictions)
    assert not report.passed and report.wrong_accepted == 1
    assert report.per_class["email.category.phishing_scam"].false_positives == 1


def test_quality_scoring_rejects_one_reply_wrongly_said_expected() -> None:
    corpus = Corpus.read(FIXTURES / "jev_classification_cases.json")
    predictions = {}
    for case in corpus.items:
        fields = {
            "category": case.expected_category,
            "evidence_scope": case.evidence_scope,
            "evaluated_at": corpus.reference_time,
            "valid_until": corpus.reference_time + timedelta(seconds=30),
        }
        if case.kind == "email":
            predictions[case.id] = EmailClassification.model_validate(
                {
                    **fields,
                    "priority": case.expected_priority,
                    "reply_expected": case.expected_reply,
                }
            )
        else:
            predictions[case.id] = EventClassification.model_validate(fields)
    assert score(corpus, predictions).passed
    silent = next(case for case in corpus.items if case.expected_reply is False)
    predictions[silent.id] = predictions[silent.id].model_copy(update={"reply_expected": True})
    report = score(corpus, predictions)
    assert not report.passed and report.wrong_accepted == 1
    assert report.per_class["email.reply.true"].false_positives == 1
