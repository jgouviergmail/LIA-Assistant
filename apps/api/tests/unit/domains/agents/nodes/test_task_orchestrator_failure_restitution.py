"""What a failed pipeline plan leaves behind for the answer (ADR-303, ADR-346).

The orchestrator hands three things on when a plan fails: the step results the
honesty directive reads, the turn's agent result the response formatter reads,
and the reference-resolution anchor it must NOT advance. The four failing plans
below are the four failed pipeline plans production recorded on 2026-10-07
(shapes only: the tool, the code the executor stored, where it failed), plus a
clean plan so the assertions cannot pass vacuously.

These tests pinned the behaviour BEFORE the advisory re-planner was removed:
it ran after every one of these plans and changed none of what follows.
"""

from __future__ import annotations

import copy
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from prometheus_client import REGISTRY

from src.core.constants import PIPELINE_STEP_FAILURE_UNCLASSIFIED
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_COMPLETED_STEPS,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_LAST_ACTION_TURN_ID,
    AgentResultStatus,
    make_agent_result_key,
)
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.nodes.task_orchestrator_node import _handle_execution_plan
from src.domains.agents.orchestration.parallel_executor import ParallelExecutionResult
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.diagnostics.failure_context import count_failed_steps

pytestmark = [pytest.mark.unit]

_TURN = 4
_RUN = "run-failure-restitution"
_EXECUTOR = "src.domains.agents.orchestration.parallel_executor.execute_plan_parallel"


def _failed(error: str, code: str | None) -> dict[str, Any]:
    """A failed step exactly as ``_merge_single_step_result`` stores it."""
    return {"success": False, "error": error, "error_code": code}


@dataclass(frozen=True)
class _Case:
    """One executed plan and what the orchestrator must hand on for it."""

    name: str
    tools: tuple[str, ...]
    completed_steps: dict[str, dict[str, Any]]
    status: str
    #: (tool name, typed code or None) per failed step, in plan order.
    failed: tuple[tuple[str, str | None], ...]


_CASES = (
    _Case(
        name="no_connector_single_step",
        tools=("get_emails_tool",),
        completed_steps={
            "step_1": _failed("No email provider is active.", "CONNECTOR_NOT_ACTIVATED"),
        },
        status=AgentResultStatus.ERROR.value,
        failed=(("get_emails_tool", "CONNECTOR_NOT_ACTIVATED"),),
    ),
    _Case(
        name="no_connector_beside_an_answer",
        tools=("get_gmail_settings_tool", "get_events_tool"),
        completed_steps={
            "step_1": _failed("No Gmail connector is active.", "CONNECTOR_NOT_ACTIVATED"),
            "step_2": {"success": True},
        },
        status=AgentResultStatus.SUCCESS.value,
        failed=(("get_gmail_settings_tool", "CONNECTOR_NOT_ACTIVATED"),),
    ),
    _Case(
        # The tool's own code (`invalid_parameters`) is no taxonomy member: the
        # executor stores None and keeps the words — what reached production.
        name="tool_refusal_with_a_free_form_code",
        tools=("get_events_tool", "create_reminder_tool"),
        completed_steps={
            "step_1": {"success": True},
            "step_2": _failed("Say when one way only.", None),
        },
        status=AgentResultStatus.SUCCESS.value,
        failed=(("create_reminder_tool", None),),
    ),
    _Case(
        name="reference_unresolved_before_the_call",
        tools=("get_contacts_tool", "get_contacts_tool", "reply_email_tool"),
        completed_steps={
            "step_1": {"success": True},
            "step_2": {"success": True},
            "step_3": _failed("Failed to resolve references: path not found", "INVALID_INPUT"),
        },
        status=AgentResultStatus.SUCCESS.value,
        failed=(("reply_email_tool", "INVALID_INPUT"),),
    ),
    _Case(
        name="clean_plan",
        tools=("get_events_tool",),
        completed_steps={"step_1": {"success": True}},
        status=AgentResultStatus.SUCCESS.value,
        failed=(),
    ),
)


def _plan(case: _Case) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id=f"plan_{case.name}",
        user_id="user",
        session_id="session",
        steps=[
            ExecutionStep(
                step_id=f"step_{index}",
                step_type=StepType.TOOL,
                agent_name="agent",
                tool_name=tool,
                parameters={},
            )
            for index, tool in enumerate(case.tools, start=1)
        ],
    )


def _state() -> MessagesState:
    state = create_initial_state(user_id=uuid.uuid4(), session_id="session", run_id=_RUN)
    state["current_turn_id"] = _TURN
    return state


_CONFIG: RunnableConfig = {
    "configurable": {"thread_id": "thread-failure-restitution"},
    "metadata": {"run_id": _RUN},
}


async def _orchestrate(case: _Case) -> dict[str, Any]:
    outcome = ParallelExecutionResult(
        completed_steps=copy.deepcopy(case.completed_steps), registry={}
    )
    with patch(_EXECUTOR, new=AsyncMock(return_value=outcome)):
        return await _handle_execution_plan(
            execution_plan=_plan(case), state=_state(), run_id=_RUN, config=_CONFIG
        )


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
async def test_the_executed_plan_is_handed_on_whole(case: _Case) -> None:
    """Every step result reaches the honesty directive, its count exact."""
    result = await _orchestrate(case)

    assert result[STATE_KEY_COMPLETED_STEPS] == case.completed_steps
    assert count_failed_steps(result[STATE_KEY_COMPLETED_STEPS]) == len(case.failed)
    assert result[STATE_KEY_EXECUTION_PLAN].plan_id == f"plan_{case.name}"


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
async def test_the_turn_result_names_each_failed_step(case: _Case) -> None:
    """ERROR only when nothing ran well; otherwise SUCCESS carrying the failures."""
    result = await _orchestrate(case)

    agent_result = result[STATE_KEY_AGENT_RESULTS][make_agent_result_key(_TURN, "plan_executor")]
    assert agent_result["status"] == case.status
    assert (
        tuple((step["tool_name"], step["error_code"]) for step in agent_result["failed_steps"])
        == case.failed
    )


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
async def test_only_a_clean_plan_moves_the_reference_anchor(case: _Case) -> None:
    """« the first one » must keep pointing at the last plan that fully ran."""
    result = await _orchestrate(case)

    if case.failed:
        assert STATE_KEY_LAST_ACTION_TURN_ID not in result
    else:
        assert result[STATE_KEY_LAST_ACTION_TURN_ID] == _TURN
    assert "pending_draft_critique" not in result


def _counted(label: str) -> float:
    return REGISTRY.get_sample_value("pipeline_step_failures_total", {"error_code": label}) or 0.0


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
async def test_each_failed_step_is_counted_under_its_code(case: _Case) -> None:
    """The Prometheus view of a failure, including one no tool ever saw."""
    expected = Counter(code or PIPELINE_STEP_FAILURE_UNCLASSIFIED for _tool, code in case.failed)
    before = {label: _counted(label) for label in expected}

    await _orchestrate(case)

    assert {label: _counted(label) - before[label] for label in expected} == dict(expected)


async def test_an_executor_crash_falls_back_without_a_plan() -> None:
    """The node never raises on an executor failure: it hands an empty result on."""
    case = _CASES[0]
    with patch(_EXECUTOR, new=AsyncMock(side_effect=RuntimeError("executor down"))):
        result = await _handle_execution_plan(
            execution_plan=_plan(case), state=_state(), run_id=_RUN, config=_CONFIG
        )

    assert result[STATE_KEY_EXECUTION_PLAN] is None
    assert STATE_KEY_COMPLETED_STEPS not in result
    assert STATE_KEY_LAST_ACTION_TURN_ID not in result
