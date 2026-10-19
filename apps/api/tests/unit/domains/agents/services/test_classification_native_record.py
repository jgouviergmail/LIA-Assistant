"""A changed publication policy needs fresh, reproducible native corpus evidence."""

import hashlib
from pathlib import Path

import pytest

from src.domains.agents.services.qualification.service import policy_fingerprint
from tests.fixtures.classification_corpus import Corpus, ReplayReport, score

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).resolve().parents[4] / "fixtures"


@pytest.mark.parametrize(
    "split,report_name",
    [("cases", "calibration"), ("holdout", "holdout"), ("adversarial", "adversarial")],
)
def test_shipped_policy_matches_qualified_native_evidence(split: str, report_name: str) -> None:
    report = ReplayReport.model_validate_json(
        (FIXTURES / f"jev_classification_qualified_{report_name}.json").read_bytes()
    )
    corpus_path = FIXTURES / f"jev_classification_{split}.json"
    corpus = Corpus.read(corpus_path)
    assert report.live and report.settings_unchanged and report.stop_reason is None
    assert (
        report.policy_sha256 == policy_fingerprint()
    ), "Requalify changed prompts or acceptance policy"
    assert report.corpus_sha256 == hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    assert len(report.calls) == report.native_calls_planned
    assert all(call.outcome == "success" and call.charge for call in report.calls)
    assert set(report.predictions) == {case.id for case in corpus.items}
    actual = score(corpus, report.predictions)
    assert actual == report.quality and actual.passed and actual.wrong_accepted == 0
    assert report.prior_cost_eur < report.total_cost_eur < report.budget_eur
