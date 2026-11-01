"""Running some steps of a plan ahead of the rest (ADR-367 amendment, FOR_EACH confirmation).

The question asked before a plan acts stands on what the lookups really return,
so those steps run first — with every step they need, and nothing else: an act
that ran here would run again when the plan resumes, or run before anyone chose.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.constants import FOR_EACH_PRE_EXECUTION_METADATA_KEY
from src.domains.agents.orchestration import parallel_executor
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.pre_execution import execute_steps_first, steps_needed_first

pytestmark = pytest.mark.unit


def _step(step_id: str, depends_on: list[str] | None = None) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="email_agent",
        tool_name=f"{step_id}_tool",
        parameters={},
        depends_on=depends_on or [],
    )


def _plan(execution_mode: str = "parallel") -> ExecutionPlan:
    """contact → find → reply, and a weather step nothing depends on."""
    return ExecutionPlan(
        plan_id="plan-1",
        user_id="u",
        execution_mode=execution_mode,
        steps=[
            _step("weather"),
            _step("contact"),
            _step("find", ["contact"]),
            _step("reply", ["find"]),
        ],
        metadata={"domains": ["emails"], "intent": "reply", "user_goal": "g", "other": "x"},
    )


def test_the_steps_needed_are_the_named_ones_and_their_dependencies_in_plan_order() -> None:
    assert steps_needed_first(_plan(), ["find"]) == ["contact", "find"]


def test_a_sequential_plan_s_order_is_a_dependency_too() -> None:
    """In sequential mode a step with no declared dependency follows the one before it."""
    assert steps_needed_first(_plan("sequential"), ["find"]) == ["weather", "contact", "find"]


async def test_the_sub_plan_runs_the_needed_steps_alone_marked_as_a_pre_execution() -> None:
    runner = AsyncMock(return_value=object())
    with patch.object(parallel_executor, "execute_plan_parallel", runner):
        result = await execute_steps_first(
            _plan(), {"find"}, {}, "run", initial_registry={"r": 1}, turn_id=7
        )

    assert result is runner.return_value
    assert runner.await_args is not None
    kwargs = runner.await_args.kwargs
    sub_plan: ExecutionPlan = kwargs["execution_plan"]
    assert [step.step_id for step in sub_plan.steps] == ["contact", "find"]  # never the act
    assert sub_plan.plan_id == "plan-1_pre_exec"
    assert sub_plan.metadata == {
        FOR_EACH_PRE_EXECUTION_METADATA_KEY: True,
        "domains": ["emails"],
        "intent": "reply",
        "user_goal": "g",
    }
    assert kwargs["initial_registry"] == {"r": 1} and kwargs["turn_id"] == 7


async def test_nothing_to_run_runs_nothing() -> None:
    runner = AsyncMock()
    with patch.object(parallel_executor, "execute_plan_parallel", runner):
        assert await execute_steps_first(_plan(), set(), {}, "run") is None
    runner.assert_not_awaited()
