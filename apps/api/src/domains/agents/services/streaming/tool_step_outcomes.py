"""What each tool step did, for the live trace (owner request 2026-10-24).

The stream used to show a tool as « started » and nothing more: a ReAct turn
calling the same search three times printed one line, a failed call read like
a running one, and the pipeline printed its tools after the orchestrator, still
« started ». Each step now carries what it is known to have done — a closed
status and integers, never words: the trace is persisted with the message.

- ReAct: a call is ``started`` when the model asks for it (``react_call_model``)
  and ``completed`` or ``failed`` when its answer comes back
  (``react_execute_tools``), both under the call's id (``step_key``); the
  answer carries the read's counts (``items_found`` / ``items_shown``, written
  by ``react_call_execution``).
- Pipeline: when the orchestrator completes, ONE step per tool of the plan that
  ran, its calls added up from the ``completed_steps`` the orchestrator writes —
  a FOR_EACH counted by its ITEMS (``step_2_item_0``…), never by the aggregate
  the executor writes back under the step's own id.

The client adds them up per label: calls ×N, results, failures.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from langchain_core.messages import AIMessage, ToolMessage

from src.core.field_names import (
    FIELD_ITEMS_FOUND,
    FIELD_ITEMS_SHOWN,
    FIELD_OUTCOME,
    FIELD_STATUS,
    FIELD_STEP_KEY,
    FIELD_SUCCESS,
)
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.constants import STATE_KEY_COMPLETED_STEPS, STATE_KEY_EXECUTION_PLAN
from src.domains.agents.orchestration.plan_schemas import ExecutionStep
from src.domains.agents.tools.react_tool_wrapper import is_item_list
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

StepStatus = Literal["started", "completed", "failed"]
StepChunks = list[tuple[ChatStreamChunk, str]]

#: The outcome's counts — the same names on both sides of the stream.
OUTCOME_CALLS = "calls"
OUTCOME_FOUND = "found"
OUTCOME_SHOWN = "shown"
OUTCOME_FAILED = "failed"


def tool_step(
    tool_name: str,
    *,
    status: StepStatus,
    step_key: str | None = None,
    outcome: Mapping[str, int] | None = None,
) -> ChatStreamChunk:
    """One tool's ``execution_step``: the catalogue's display, or a visible fallback.

    Args:
        tool_name: The tool's registered name.
        status: Where the step stands.
        step_key: The call's id, joining its « started » and « finished » steps.
        outcome: What it did (counts only).

    Returns:
        The SSE chunk.
    """
    from src.domains.agents.utils.execution_metadata import build_execution_step_event

    event = build_execution_step_event(step_type="tool", step_name=tool_name, status=status)
    if not event:
        # A tool the catalogue does not describe still shows that it ran.
        logger.debug("tool_execution_step_fallback", tool_name=tool_name)
        event = {
            "type": "execution_step",
            "step_type": "tool",
            "step_name": tool_name,
            FIELD_STATUS: status,
            "emoji": "⚙️",
            "i18n_key": "react_tool_execution",
            "category": "tool",
        }
    if step_key:
        event = {**event, FIELD_STEP_KEY: step_key}
    if outcome:
        event = {**event, FIELD_OUTCOME: dict(outcome)}
    return ChatStreamChunk(type="execution_step", content="", metadata=event)


def react_started_steps(state_delta: Mapping[str, Any]) -> StepChunks:
    """A ``started`` step per tool call the ReAct model just asked for.

    Args:
        state_delta: ``react_call_model``'s state update.

    Returns:
        One chunk per named call, keyed by the call's id.
    """
    steps: StepChunks = []
    for message in state_delta.get("messages", []):
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            name = call.get("name")
            if name:
                steps.append((tool_step(name, status="started", step_key=call.get("id")), ""))
    return steps


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def react_finished_steps(state_delta: Mapping[str, Any]) -> StepChunks:
    """A ``completed`` or ``failed`` step per answer the ReAct tools just gave.

    Args:
        state_delta: ``react_execute_tools``' state update.

    Returns:
        One chunk per answer, under its call's id, with the read's counts.
    """
    steps: StepChunks = []
    for message in state_delta.get("messages", []):
        if not isinstance(message, ToolMessage) or not message.name:
            continue
        failed = message.status == "error"
        metadata = message.response_metadata or {}
        outcome = {OUTCOME_FAILED: int(failed)}
        for field, key in ((FIELD_ITEMS_FOUND, OUTCOME_FOUND), (FIELD_ITEMS_SHOWN, OUTCOME_SHOWN)):
            count = _int(metadata.get(field))
            if count is not None:
                outcome[key] = count
        status: StepStatus = "failed" if failed else "completed"
        steps.append(
            (
                tool_step(
                    message.name, status=status, step_key=message.tool_call_id, outcome=outcome
                ),
                "",
            )
        )
    return steps


def _item_count(entry: object) -> int:
    """Items a step's result holds: its longest item list (0 when it has none)."""
    if not isinstance(entry, dict):
        return 0
    return max((len(value) for value in entry.values() if is_item_list(value)), default=0)


def _call_entries(step: object, completed: Mapping[str, object]) -> list[object]:
    """What a plan step's calls left: one entry per FOR_EACH item, else its own.

    The plan in the state keeps the FOR_EACH step unexpanded, and the executor
    writes the merged items back under its id: read as one call, a loop over
    ten items showed ×1 and lost every failure but a total one. An empty loop,
    a branch not taken and a refused step left nothing — they never ran.
    """
    if isinstance(step, ExecutionStep) and step.is_for_each_step:
        item_ids = (step.item_step_id(index) for index in range(step.for_each_max))
        return [completed[item_id] for item_id in item_ids if item_id in completed]
    entry = completed.get(getattr(step, "step_id", ""))
    return [] if entry is None else [entry]


def _tally(plan_steps: list[Any], completed: Mapping[str, object]) -> dict[str, dict[str, int]]:
    """Per tool, in the plan's order: the calls that ran, their items, their failures."""
    tallies: dict[str, dict[str, int]] = {}
    for step in plan_steps:
        name = getattr(step, "tool_name", None)
        if not name:
            continue
        tally = tallies.setdefault(name, {OUTCOME_CALLS: 0, OUTCOME_FOUND: 0, OUTCOME_FAILED: 0})
        for entry in _call_entries(step, completed):
            tally[OUTCOME_CALLS] += 1
            if isinstance(entry, dict) and entry.get(FIELD_SUCCESS) is False:
                tally[OUTCOME_FAILED] += 1
            else:
                tally[OUTCOME_FOUND] += _item_count(entry)
    return tallies


def pipeline_steps(
    accumulated_state: Mapping[str, Any], state_delta: Mapping[str, Any]
) -> StepChunks:
    """One step per tool of the executed plan, with what its calls did.

    Args:
        accumulated_state: The state streamed so far (holds the plan).
        state_delta: ``task_orchestrator``'s state update (holds the results).

    Returns:
        One chunk per tool that ran, in the plan's order; without results, the
        plan's tools as ``started`` (what the stream always showed).
    """
    plan = state_delta.get(STATE_KEY_EXECUTION_PLAN) or accumulated_state.get(
        STATE_KEY_EXECUTION_PLAN
    )
    plan_steps = getattr(plan, "steps", None)
    if not plan_steps:
        return []
    completed = state_delta.get(STATE_KEY_COMPLETED_STEPS)
    if not isinstance(completed, Mapping):
        names = dict.fromkeys(getattr(step, "tool_name", None) for step in plan_steps)
        return [(tool_step(name, status="started"), "") for name in names if name]
    steps: StepChunks = []
    for name, tally in _tally(plan_steps, completed).items():
        if tally[OUTCOME_CALLS] == 0:
            continue
        status: StepStatus = (
            "failed" if tally[OUTCOME_FAILED] == tally[OUTCOME_CALLS] else "completed"
        )
        steps.append((tool_step(name, status=status, outcome=tally), ""))
    return steps


__all__ = [
    "OUTCOME_CALLS",
    "OUTCOME_FAILED",
    "OUTCOME_FOUND",
    "OUTCOME_SHOWN",
    "pipeline_steps",
    "react_finished_steps",
    "react_started_steps",
    "tool_step",
]
