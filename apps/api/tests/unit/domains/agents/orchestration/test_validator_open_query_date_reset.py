"""Tests for the open/relative query end-of-window date reset in PlanValidator.

The planner sometimes sets a narrow ``time_max`` (e.g. now + 2 days) for a query
that carries NO temporal reference ("my next medical appointments"). That bound
hides the very items the user asked for. When the analyzer reports
``has_temporal_reference`` False, the validator empties any param the tool
declares as ``search_role='range_end'`` so the tool's own default window applies
and the Response LLM filters downstream.

Queries WITH a temporal reference ("tomorrow", "next week", "on Aug 15") report
the flag True and MUST keep their bounds untouched. The reset is deterministic
(a single reliable analyzer boolean, no string matching) and gated by
``settings.planner_open_query_date_reset``.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.validator import (
    PlanValidator,
    ValidationContext,
    ValidationResult,
)
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

pytestmark = [pytest.mark.unit]


# ============================================================================
# Helpers
# ============================================================================


def _make_calendar_manifest(
    *,
    time_max_required: bool = False,
    annotate_range_end: bool = True,
) -> ToolManifest:
    """A calendar-like search tool with a time window and an optional query."""
    return ToolManifest(
        name="get_events_tool",
        agent="event_agent",
        description="Calendar search with a time window",
        parameters=[
            ParameterSchema(name="query", type="string", required=False, description="q"),
            ParameterSchema(name="time_min", type="string", required=False, description="from"),
            ParameterSchema(
                name="time_max",
                type="string",
                required=time_max_required,
                description="to",
                search_role="range_end" if annotate_range_end else None,
            ),
            ParameterSchema(name="max_results", type="integer", required=False, description="n"),
        ],
        outputs=[OutputFieldSchema(path="items[]", type="array", description="Items")],
        cost=CostProfile(est_tokens_in=100, est_tokens_out=200),
        permissions=PermissionProfile(required_scopes=[]),
        text_search_mode="literal",
    )


def _make_validator(*manifests: ToolManifest) -> PlanValidator:
    registry = AgentRegistry()
    for m in manifests:
        registry.register_tool_manifest(m, override=True)
    return PlanValidator(registry)


def _make_step(step_id: str, tool_name: str, parameters: dict[str, Any]) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="event_agent",
        tool_name=tool_name,
        parameters=parameters,
    )


def _make_plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="p", user_id="u", session_id="s", steps=list(steps))


def _make_context(*, has_temporal_reference: bool) -> ValidationContext:
    return ValidationContext(
        user_id="u",
        session_id="s",
        has_temporal_reference=has_temporal_reference,
    )


def _run_reset(validator: PlanValidator, plan: ExecutionPlan, ctx: ValidationContext) -> int:
    """Invoke the reset directly; return the number of reset warnings."""
    result = ValidationResult(is_valid=True)
    validator._apply_open_query_date_reset(plan, ctx, result)
    return sum(
        1
        for w in result.warnings
        if w.context and w.context.get("layer") == "open_query_date_reset"
    )


@pytest.fixture
def reset_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "planner_open_query_date_reset", True, raising=False)


@pytest.fixture
def reset_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "planner_open_query_date_reset", False, raising=False)


# ============================================================================
# Core behaviour
# ============================================================================


class TestOpenQueryDateReset:
    def test_open_query_empties_range_end(self, reset_enabled: None) -> None:
        """No temporal reference -> planner-set time_max is emptied, time_min kept."""
        validator = _make_validator(_make_calendar_manifest())
        plan = _make_plan(
            _make_step(
                "s1",
                "get_events_tool",
                {
                    "query": "médical",
                    "time_min": "2026-07-04T00:00:00Z",
                    "time_max": "2026-07-06T00:00:00Z",  # planner's +2d hallucination
                    "max_results": 5,
                },
            )
        )
        warnings = _run_reset(validator, plan, _make_context(has_temporal_reference=False))
        params = plan.steps[0].parameters
        assert params["time_max"] is None  # end bound emptied
        assert params["time_min"] == "2026-07-04T00:00:00Z"  # start bound preserved
        assert params["query"] == "médical"  # query untouched (tool handles free-text)
        assert warnings == 1

    def test_temporal_reference_preserves_range_end(self, reset_enabled: None) -> None:
        """A query with an explicit temporal reference keeps its bound."""
        validator = _make_validator(_make_calendar_manifest())
        plan = _make_plan(_make_step("s1", "get_events_tool", {"time_max": "2026-08-15T00:00:00Z"}))
        warnings = _run_reset(validator, plan, _make_context(has_temporal_reference=True))
        assert plan.steps[0].parameters["time_max"] == "2026-08-15T00:00:00Z"
        assert warnings == 0

    def test_kill_switch_disables_reset(self, reset_disabled: None) -> None:
        """Setting off -> no reset even for an open query."""
        validator = _make_validator(_make_calendar_manifest())
        plan = _make_plan(_make_step("s1", "get_events_tool", {"time_max": "2026-07-06T00:00:00Z"}))
        warnings = _run_reset(validator, plan, _make_context(has_temporal_reference=False))
        assert plan.steps[0].parameters["time_max"] == "2026-07-06T00:00:00Z"
        assert warnings == 0

    def test_required_range_end_is_skipped(self, reset_enabled: None) -> None:
        """A required range_end param must not be nulled (would fail at execution)."""
        validator = _make_validator(_make_calendar_manifest(time_max_required=True))
        plan = _make_plan(_make_step("s1", "get_events_tool", {"time_max": "2026-07-06T00:00:00Z"}))
        warnings = _run_reset(validator, plan, _make_context(has_temporal_reference=False))
        assert plan.steps[0].parameters["time_max"] == "2026-07-06T00:00:00Z"
        assert warnings == 0

    def test_unannotated_tool_untouched(self, reset_enabled: None) -> None:
        """A tool without a range_end annotation is never touched."""
        validator = _make_validator(_make_calendar_manifest(annotate_range_end=False))
        plan = _make_plan(_make_step("s1", "get_events_tool", {"time_max": "2026-07-06T00:00:00Z"}))
        warnings = _run_reset(validator, plan, _make_context(has_temporal_reference=False))
        assert plan.steps[0].parameters["time_max"] == "2026-07-06T00:00:00Z"
        assert warnings == 0

    def test_missing_or_empty_range_end_is_noop(self, reset_enabled: None) -> None:
        """No time_max set -> nothing to reset, no warning."""
        validator = _make_validator(_make_calendar_manifest())
        plan = _make_plan(_make_step("s1", "get_events_tool", {"max_results": 3}))
        warnings = _run_reset(validator, plan, _make_context(has_temporal_reference=False))
        assert "time_max" not in plan.steps[0].parameters or plan.steps[0].parameters.get(
            "time_max"
        ) in (None, "")
        assert warnings == 0

    def test_multiple_steps_each_reset(self, reset_enabled: None) -> None:
        validator = _make_validator(_make_calendar_manifest())
        plan = _make_plan(
            _make_step("s1", "get_events_tool", {"time_max": "2026-07-06T00:00:00Z"}),
            _make_step("s2", "get_events_tool", {"time_max": "2026-07-07T00:00:00Z"}),
        )
        warnings = _run_reset(validator, plan, _make_context(has_temporal_reference=False))
        assert plan.steps[0].parameters["time_max"] is None
        assert plan.steps[1].parameters["time_max"] is None
        assert warnings == 2

    def test_self_guard_on_temporal_reference(self, reset_enabled: None) -> None:
        """Direct call with has_temporal_reference=True is a no-op (self-guard)."""
        validator = _make_validator(_make_calendar_manifest())
        plan = _make_plan(_make_step("s1", "get_events_tool", {"time_max": "2026-07-06T00:00:00Z"}))
        warnings = _run_reset(validator, plan, _make_context(has_temporal_reference=True))
        assert plan.steps[0].parameters["time_max"] == "2026-07-06T00:00:00Z"
        assert warnings == 0

    def test_default_context_does_not_reset(self, reset_enabled: None) -> None:
        """ValidationContext defaults has_temporal_reference=True -> no reset."""
        validator = _make_validator(_make_calendar_manifest())
        plan = _make_plan(_make_step("s1", "get_events_tool", {"time_max": "2026-07-06T00:00:00Z"}))
        ctx = ValidationContext(user_id="u", session_id="s")
        result = ValidationResult(is_valid=True)
        validator._apply_open_query_date_reset(plan, ctx, result)
        assert plan.steps[0].parameters["time_max"] == "2026-07-06T00:00:00Z"
