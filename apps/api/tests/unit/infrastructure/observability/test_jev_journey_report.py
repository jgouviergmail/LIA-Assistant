"""Do not claim an optimization from unrelated traffic or missing measurements."""

import pytest
from pydantic import ValidationError

from src.infrastructure.observability.jev_journey_report import (
    JourneySample,
    compare_journeys,
    samples_from_logs,
)

pytestmark = pytest.mark.unit


def test_log_export_keeps_only_measurements_and_never_guesses_switches_or_quality() -> None:
    records = samples_from_logs(
        [
            "invalid log line",
            '{"event":"first_token_received","run_id":"early","ttft_seconds":0.4}',
            '{"event":"chat_delivery_completed","run_id":"run","duration_ms":2000,"first_useful_ms":300,"cost_eur":0.002,"user_id":"private","query":"secret"}',
        ],
        environment="frozen-dev",
    )
    assert len(records) == 1
    assert records[0].first_useful_ms == 300
    assert records[0].mode == "unknown" and records[0].quality == "unreviewed"
    assert "private" not in records[0].model_dump_json()
    assert "secret" not in records[0].model_dump_json()


def sample(run: str, mode: str, **changes: object) -> JourneySample:
    return JourneySample.model_validate(
        {
            "run_id": run,
            "pair_id": "same-request-1",
            "environment": "dev-snapshot-1",
            "mode": mode,
            "duration_ms": 1000,
            "first_useful_ms": 500,
            "cost_eur": 0.01,
            "quality": "pass",
            "outcome": "completed",
            **changes,
        }
    )


def test_compares_only_paired_same_environment_quality_checked_complete_runs() -> None:
    report = compare_journeys(
        [
            sample("off", "off"),
            sample("on", "on", duration_ms=600, first_useful_ms=200),
            sample("other", "on", pair_id=None, duration_ms=1, first_useful_ms=1),
            sample("mismatch-off", "off", pair_id="mismatch"),
            sample("mismatch-on", "on", pair_id="mismatch", environment="other"),
            sample("bad-off", "off", pair_id="bad"),
            sample("bad-on", "on", pair_id="bad", quality="fail"),
        ]
    )
    assert report["qualified_pairs"] == 1
    assert report["duration_savings_ms"] == {"count": 1, "p50": 400, "p95": 400}
    assert report["first_useful_savings_ms"]["p50"] == 300
    assert report["quality_failures"] == 1


def test_unknown_cost_and_first_result_are_not_replaced_by_zero() -> None:
    report = compare_journeys(
        [sample("off", "off", cost_eur=None, first_useful_ms=None), sample("on", "on")]
    )
    assert report["cost_savings_eur"]["count"] == 0
    assert report["first_useful_savings_ms"]["p50"] is None


def test_duplicates_are_rejected_instead_of_biasing_the_result() -> None:
    with pytest.raises(ValueError, match="duplicate run"):
        compare_journeys([sample("off", "off"), sample("off", "off")])
    with pytest.raises(ValueError, match="ambiguous pair"):
        compare_journeys([sample("off", "off"), sample("off2", "off"), sample("on", "on")])


@pytest.mark.parametrize(
    "changes", [{"duration_ms": -1}, {"cost_eur": float("nan")}, {"first_useful_ms": 1200}]
)
def test_invalid_measurements_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        sample("run", "on", **changes)


def test_unreviewed_or_unfinished_runs_remain_visible_but_do_not_qualify_a_gain() -> None:
    report = compare_journeys(
        [
            sample("off", "off"),
            sample("on", "on", quality="unreviewed"),
            sample("error", "unknown", outcome="error", pair_id=None),
        ]
    )
    assert report["qualified_pairs"] == 0
    assert report["samples"] == 3
    assert report["unreviewed"] == 1
    assert report["incomplete"] == 1
