"""_build_planner_human_message — resolved facts ride in the HUMAN message.

Closes the prod failure of 2026-07-17 (twice observed): the enriched query
carried the agreed facts ("... tomorrow at 9am at the restaurant with Jérôme
Gouvier") in the middle of the system context and the planner substituted
defaults (next-hour slot, generic title). Facts now travel in the human
message with the authority + language constraints attached.
"""

from __future__ import annotations

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.services.planner.human_message import (
    build_planner_human_message,
    format_existing_plan_for_replan,
)

pytestmark = pytest.mark.unit


def _intelligence(enriched: str | None) -> QueryIntelligence:
    return QueryIntelligence(
        original_query="crée le rdv",
        english_query="create the appointment",
        immediate_intent="create",
        immediate_confidence=0.95,
        user_goal=UserGoal.PLAN_ORGANIZE,
        goal_reasoning="user confirms creating the discussed appointment",
        english_enriched_query=enriched,
    )


def test_facts_ride_in_human_message_with_authority_and_language() -> None:
    enriched = (
        "Create the calendar appointment for tomorrow at 9am at the restaurant "
        "with Jérôme Gouvier"
    )
    content = build_planner_human_message(_intelligence(enriched))
    assert content.startswith("Query: crée le rdv")
    assert enriched in content
    assert "authoritative" in content
    assert "NEVER substitute a default" in content
    assert "user's language" in content


def test_without_enriched_query_human_message_is_query_only() -> None:
    content = build_planner_human_message(_intelligence(None))
    assert content == "Query: crée le rdv"


def test_empty_enriched_query_treated_as_absent() -> None:
    content = build_planner_human_message(_intelligence(""))
    assert content == "Query: crée le rdv"


def _wrong_date_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p",
        user_id="u",
        session_id="s",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="event_agent",
                tool_name="create_event_tool",
                parameters={"summary": "Rendez-vous", "start_datetime": "2026-07-17T20:00:00"},
            )
        ],
    )


def test_replan_appends_previous_plan_with_fix_directive() -> None:
    """Validation replan: the previous plan rides in the HUMAN message so the
    planner fixes it (prod 2026-07-17 oscillation) instead of rebuilding."""
    content = build_planner_human_message(
        _intelligence("Create the appointment Saturday July 18 at 9:30 with Jérôme"),
        existing_plan=_wrong_date_plan(),
        validation_feedback="FIX: start_datetime must be 2026-07-18T09:30:00",
    )
    assert "REPLAN" in content
    assert "PREVIOUS PLAN:" in content
    assert "create_event_tool" in content
    assert "byte-for-byte identical" in content
    assert "2026-07-17T20:00:00" in content  # the previous (wrong) value is shown


def test_no_previous_plan_block_without_feedback() -> None:
    """existing_plan present but no feedback (not a replan) → no PREVIOUS PLAN block."""
    content = build_planner_human_message(
        _intelligence("x"), existing_plan=_wrong_date_plan(), validation_feedback=None
    )
    assert "PREVIOUS PLAN" not in content


def test_clarification_path_passes_no_existing_plan_so_no_block() -> None:
    """On the clarification path the caller passes existing_plan=None; the helper
    then never emits the replan block (the clarification machinery is untouched)."""
    content = build_planner_human_message(
        _intelligence("x"), existing_plan=None, validation_feedback="some feedback"
    )
    assert "PREVIOUS PLAN" not in content


def test_format_existing_plan_handles_object_dict_and_empty() -> None:
    assert format_existing_plan_for_replan(_wrong_date_plan()).startswith("PREVIOUS PLAN:")
    # Dict-serialized form (defensive msgpack tolerance)
    dict_plan = {"steps": [{"step_id": "s1", "tool_name": "create_event_tool", "parameters": {}}]}
    assert "create_event_tool" in format_existing_plan_for_replan(dict_plan)  # type: ignore[arg-type]
    # No steps → empty string (ExecutionPlan itself forbids empty steps, so the
    # empty case is only reachable via a dict/degraded form).
    assert format_existing_plan_for_replan({"steps": []}) == ""  # type: ignore[arg-type]
    assert format_existing_plan_for_replan(None) == ""  # type: ignore[arg-type]


def test_no_planner_site_builds_a_bare_query_human_message() -> None:
    """Anti-recurrence guard: the fix initially missed the two strategy files —
    the RUNTIME path — which build their own human message (the service's
    methods are only the fallback). Any site hand-rolling `f"Query: ..."`
    bypasses the resolved-facts contract."""
    import pathlib

    import src.domains.agents.services.planner.strategies.multi_domain as multi
    import src.domains.agents.services.planner.strategies.single_domain as single
    import src.domains.agents.services.smart_planner_service as service

    for module in (service, single, multi):
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert 'HumanMessage(content=f"Query:' not in source, module.__name__
    for module in (single, multi):
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert "build_planner_human_message" in source, module.__name__
