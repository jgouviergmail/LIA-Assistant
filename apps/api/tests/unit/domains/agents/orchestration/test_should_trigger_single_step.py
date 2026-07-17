"""should_trigger_semantic_validation — single-step skip rules.

Closes the prod regression of 2026-07-17: a single-step MUTATION plan
(create_event_tool) was short-circuited as "single_step_trivial", so a plan
whose parameters ignored the conversational context (breakfast agreed for
Saturday 10:00 planned as a default next-hour slot on Friday) shipped without
semantic validation. Single-step mutations now trigger validation; read-only
single steps and draft-gated telephony calls stay trivial (no extra LLM cost).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.semantic_validator import (
    should_trigger_semantic_validation,
)

pytestmark = pytest.mark.unit


def _make_step(tool_name: str, step_id: str = "step_1") -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="test_agent",
        tool_name=tool_name,
        parameters={},
    )


def _make_plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="test_plan",
        user_id="test_user",
        session_id="test_session",
        steps=list(steps),
    )


def test_single_step_read_stays_trivial() -> None:
    should, reason = should_trigger_semantic_validation(
        _make_plan(_make_step("get_events_tool")), "what's on my calendar?"
    )
    assert should is False
    assert reason == "single_step_trivial"


def test_single_step_mutation_triggers_validation() -> None:
    """The prod regression case: one create step must be validated."""
    should, reason = should_trigger_semantic_validation(
        _make_plan(_make_step("create_event_tool")),
        "Create a calendar appointment for the breakfast with Jérôme on Saturday July 18 at 10:00",
    )
    assert should is True
    assert reason == "single_step_mutation"


def test_single_step_phone_call_stays_trivial() -> None:
    """place_phone_call_tool is draft-gated (HITL) — no validator LLM cost added."""
    should, reason = should_trigger_semantic_validation(
        _make_plan(_make_step("place_phone_call_tool")), "call Jérôme about breakfast"
    )
    assert should is False
    assert reason == "single_step_trivial"


def test_mutation_intent_with_read_tool_still_flagged() -> None:
    """Upstream guard preserved: mutation intent + no mutation tool → validate."""
    intelligence: dict[str, Any] = {"is_mutation_intent": True, "domains": ["event"]}
    should, reason = should_trigger_semantic_validation(
        _make_plan(_make_step("get_events_tool")),
        "delete my meeting",
        query_intelligence=intelligence,
    )
    assert should is True
    assert reason.startswith("mutation_intent_but_no_mutation_tool")
