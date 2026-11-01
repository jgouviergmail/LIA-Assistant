"""Each step of a wave gets a config of its own, dated by the turn (ADR-367, lot 8).

The executor enriched a SHALLOW copy of the turn's config: every parallel step
wrote its ``node_name`` into the ONE metadata dict they all shared — the
caller's — so the last step to start named the token usage of all of them.
And nothing carried the turn into a tool's config, so the context list a tool
saved was always dated turn 0.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from src.core.field_names import FIELD_METADATA, FIELD_NODE_NAME, FIELD_TURN_ID
from src.domains.agents.orchestration.parallel_executor import (
    StepResult,
    _execute_single_step_async,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType

pytestmark = pytest.mark.unit


def _step(step_id: str) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="email_agent",
        tool_name="get_emails_tool",
    )


async def test_parallel_steps_never_share_or_touch_the_turns_metadata() -> None:
    seen: dict[str, dict[str, Any]] = {}

    async def _tool_step(*, step: ExecutionStep, config: Any, **_: Any) -> StepResult:
        await asyncio.sleep(0)  # let the other step start in between
        seen[step.step_id] = dict(config[FIELD_METADATA])
        return StepResult(
            step_id=step.step_id, step_type=StepType.TOOL, success=True, execution_time_ms=0
        )

    turn_config: Any = {"configurable": {"thread_id": "t"}, FIELD_METADATA: {"run_id": "r"}}
    with patch(
        "src.domains.agents.orchestration.parallel_executor._execute_tool_step", new=_tool_step
    ):
        await asyncio.gather(
            _execute_single_step_async(_step("s1"), {}, turn_config, 1, None, turn_id=7),
            _execute_single_step_async(_step("s2"), {}, turn_config, 1, None, turn_id=7),
        )

    assert seen["s1"][FIELD_NODE_NAME] == "parallel_executor:s1"
    assert seen["s2"][FIELD_NODE_NAME] == "parallel_executor:s2"
    assert seen["s1"]["run_id"] == "r"  # what the turn carried is kept
    assert turn_config[FIELD_METADATA] == {"run_id": "r"}  # the turn's own dict is untouched


async def test_a_step_carries_the_turn_it_runs_in() -> None:
    seen: dict[str, Any] = {}

    async def _tool_step(*, config: Any, **_: Any) -> StepResult:
        seen.update(config[FIELD_METADATA])
        return StepResult(step_id="s1", step_type=StepType.TOOL, success=True, execution_time_ms=0)

    with patch(
        "src.domains.agents.orchestration.parallel_executor._execute_tool_step", new=_tool_step
    ):
        await _execute_single_step_async(_step("s1"), {}, {}, 1, None, turn_id=7)

    assert seen[FIELD_TURN_ID] == 7


async def test_a_step_another_depends_on_is_marked_intermediate() -> None:
    from src.core.field_names import FIELD_INTERMEDIATE_STEP

    seen: dict[str, Any] = {}

    async def _tool_step(*, config: Any, **_: Any) -> StepResult:
        seen.update(config[FIELD_METADATA])
        return StepResult(step_id="s1", step_type=StepType.TOOL, success=True, execution_time_ms=0)

    with patch(
        "src.domains.agents.orchestration.parallel_executor._execute_tool_step", new=_tool_step
    ):
        await _execute_single_step_async(_step("s1"), {}, {}, 1, None, intermediate=True)

    assert seen[FIELD_INTERMEDIATE_STEP] is True


def test_the_consumed_steps_are_those_another_step_depends_on() -> None:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

    search = _step("search")
    reply = ExecutionStep(
        step_id="reply",
        step_type=StepType.TOOL,
        agent_name="email_agent",
        tool_name="reply_email_tool",
        depends_on=["search"],
    )
    plan = ExecutionPlan(user_id="u", steps=[search, reply])

    assert plan.consumed_step_ids() == {"search"}


def test_a_list_a_for_each_iterates_is_what_the_turn_shows_not_a_means() -> None:
    """« My next three events, and the weather for each »: the events ARE shown —
    « move the second one » must find them, not the list shown before."""
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

    events = ExecutionStep(
        step_id="events",
        step_type=StepType.TOOL,
        agent_name="event_agent",
        tool_name="get_events_tool",
    )
    weather = ExecutionStep(
        step_id="weather",
        step_type=StepType.TOOL,
        agent_name="weather_agent",
        tool_name="get_weather_forecast_tool",
        depends_on=["events"],
        for_each="$steps.events.events",
    )
    plan = ExecutionPlan(user_id="u", steps=[events, weather])

    assert plan.consumed_step_ids() == frozenset()
