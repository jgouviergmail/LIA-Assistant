"""The declared gates decide exactly as the shipped constants did (ADR-374).

The recorded answers of the three qualified classification runs, replayed through
``classify_answers`` with the declared defaults, give exactly the recorded labels; the
policy fingerprint of the defaults is the one those runs were taken under, and a moved
threshold changes it.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from src.domains.agents.services.qualification.policy import classify_answers
from src.domains.agents.services.qualification.service import policy_fingerprint
from src.domains.llm_config.jev_gates import gate_defaults
from src.domains.llm_config.jev_registry import JevUsage
from tests.fixtures.classification_corpus import Corpus, ReplayReport

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).resolve().parents[4] / "fixtures"
RUNS = [("cases", "calibration"), ("holdout", "holdout"), ("adversarial", "adversarial")]


@pytest.mark.parametrize("split,report_name", RUNS)
def test_the_recorded_answers_replay_to_the_recorded_labels(split: str, report_name: str) -> None:
    report = ReplayReport.model_validate_json(
        (FIXTURES / f"jev_classification_qualified_{report_name}.json").read_bytes()
    )
    cases = {
        case.id: case for case in Corpus.read(FIXTURES / f"jev_classification_{split}.json").items
    }
    replayed = 0
    for call in report.calls:
        usage = (
            JevUsage.EMAIL_CLASSIFICATION if call.kind == "email" else JevUsage.EVENT_CLASSIFICATION
        )
        for index, member in enumerate(call.members):
            recorded = report.predictions[member]
            label = classify_answers(
                cases[member].observation(),
                category=call.answers.get(f"i{index}_category"),
                priority=call.answers.get(f"i{index}_priority"),
                reply=call.nouls.get(f"i{index}_reply"),
                now=recorded.evaluated_at,
                thresholds=gate_defaults(usage),
            )
            assert label == recorded, member
            replayed += 1
    assert replayed == len(report.predictions)


def test_the_defaults_keep_the_qualified_fingerprint() -> None:
    assert policy_fingerprint() == policy_fingerprint(
        JevUsage.EMAIL_CLASSIFICATION, gate_defaults(JevUsage.EMAIL_CLASSIFICATION)
    )
    assert policy_fingerprint() == policy_fingerprint(
        JevUsage.EVENT_CLASSIFICATION, gate_defaults(JevUsage.EVENT_CLASSIFICATION)
    )


def test_policy_fingerprint_changes_with_effective_thresholds() -> None:
    moved = {**gate_defaults(JevUsage.EMAIL_CLASSIFICATION), "priority": Decimal("0.50")}
    assert policy_fingerprint(JevUsage.EMAIL_CLASSIFICATION, moved) != policy_fingerprint()
    event = {"category": Decimal("0.90")}
    assert policy_fingerprint(JevUsage.EVENT_CLASSIFICATION, event) != policy_fingerprint(
        JevUsage.EMAIL_CLASSIFICATION, moved
    )
