"""Whole bounded observations and two/one native questions; no hidden body evidence."""

from datetime import UTC, datetime

import pytest

from src.domains.agents.services.qualification.batches import build_batches
from src.domains.agents.services.qualification.contracts import (
    ClassificationObservation,
)
from src.infrastructure.llm.typesafe_client import (
    MAX_QUESTIONS,
    MAX_REQUEST_BYTES,
    encode_decision_request,
)

pytestmark = pytest.mark.unit


def observed(
    index: int, kind: str = "email", text: str = "Please review the project contract."
) -> ClassificationObservation:
    return ClassificationObservation.model_validate(
        {
            "identity": f"private-{index}",
            "kind": kind,
            "container_id": "inbox",
            "item_id": str(index),
            "occurrence": "",
            "revision": "1",
            "evidence_scope": "snippet",
            "evidence": {"subject": "A contract", "snippet": text},
        }
    )


@pytest.mark.parametrize("kind,questions_per_item", [("email", 2), ("event", 1)])
def test_every_whole_item_has_exactly_the_native_questions_for_its_kind(
    kind: str, questions_per_item: int
) -> None:
    values = [observed(i, kind) for i in range(30)]
    batches = build_batches(values, model="a-model", now=datetime.now(UTC), timezone="Europe/Paris")
    seen: list[str] = []
    for batch in batches:
        body = encode_decision_request("a-model", batch.state, batch.questions)
        assert len(body) <= MAX_REQUEST_BYTES
        assert len(batch.questions) <= MAX_QUESTIONS
        assert len(batch.questions) == len(batch.members) * questions_per_item
        assert b"private-" not in body
        for question in batch.questions.values():
            assert next(iter(question.criteria)) == "unknown"
        seen.extend(member.identity for member in batch.members)
    assert seen and len(set(seen)) == len(seen)


def test_oversized_multibyte_evidence_is_skipped_whole_and_never_silently_cut() -> None:
    values = [observed(0, text="界" * MAX_REQUEST_BYTES), observed(1)]
    batches = build_batches(values, model="a-model", now=datetime.now(UTC), timezone="UTC")
    assert [item.identity for batch in batches for item in batch.members] == ["private-1"]


def test_email_category_contains_phishing_instead_of_an_additional_question() -> None:
    batch = build_batches([observed(1)], model="a-model", now=datetime.now(UTC), timezone="UTC")[0]
    assert len(batch.questions) == 2
    assert set(batch.questions["i0_category"].criteria) == {
        "unknown",
        "professional",
        "personal",
        "spam",
        "phishing_scam",
    }
    assert set(batch.questions["i0_priority"].criteria) == {
        "unknown",
        "normal",
        "urgent",
        "critical",
    }


def test_mixed_kinds_and_duplicate_identities_are_refused_before_spend() -> None:
    with pytest.raises(ValueError):
        build_batches(
            [observed(0), observed(1, "event")],
            model="a-model",
            now=datetime.now(UTC),
            timezone="UTC",
        )
    with pytest.raises(ValueError):
        build_batches(
            [observed(0), observed(0)],
            model="a-model",
            now=datetime.now(UTC),
            timezone="UTC",
        )
