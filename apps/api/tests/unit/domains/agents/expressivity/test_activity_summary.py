"""The archive remembers a bounded summary, never replays a performance."""

import json

from src.domains.agents.api.archive_metadata import with_companion_metadata
from src.domains.agents.expressivity.activity import Activity
from src.domains.agents.expressivity.activity_summary import ActivitySummary


def test_summary_distinguishes_preparation_and_effect_and_deduplicates() -> None:
    summary = ActivitySummary()
    prepared = Activity(
        run_id="r",
        invocation_id="a",
        family="communicating",
        intent="prepare",
        phase="finished",
        outcome="prepared",
    )
    completed = prepared.model_copy(
        update={"invocation_id": "b", "intent": "act", "outcome": "succeeded"}
    )
    for event in [prepared, prepared, completed]:
        summary.observe({"activity": event.model_dump()})
    assert summary.snapshot() == {
        "version": 1,
        "families": ["communicating"],
        "performed": ["communicating"],
        "prepared": True,
        "failed": False,
    }


def test_no_terminal_no_success_and_malformed_payloads_do_not_break_stream() -> None:
    summary = ActivitySummary()
    for value in [None, {}, {"activity": "bad"}, {"activity": {"version": 2}}]:
        summary.observe(value)
    assert summary.snapshot() is None


def test_archived_evidence_survives_json_without_mutating_or_retaining_payloads() -> None:
    base = {"run_id": "r"}
    activity = ActivitySummary()
    activity.observe(
        {
            "activity": Activity(
                run_id="r",
                invocation_id="a",
                family="creating",
                intent="prepare",
                phase="finished",
                outcome="prepared",
            ).model_dump()
        }
    )
    tone = {"register": "warm", "intensity": 0.5, "accent": "none"}
    archived = with_companion_metadata(base, tone, activity.snapshot())
    assert json.loads(json.dumps(archived)) == archived
    assert base == {"run_id": "r"}
    assert archived["companion_activity"]["performed"] == []
    assert archived["expressivity"] == tone
    assert "invocation_id" not in json.dumps(archived)
