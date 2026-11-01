"""The plan resumes once the person answered (spec 2026-10-29 D7).

The first pass ran every step it could; a step reading a result awaiting the
person's approval WAITED (``orchestration/held_steps``). When the confirmation
sequence settles, the graph comes back to the orchestrator (the FOR_EACH
confirmation's own way back): the decided drafts are executed once — through the
same executor the response would have used —, each confirmed act's REAL result
becomes its step's result, and the waiting steps run on it. A waiting step whose
act was refused or failed is left unrun and said (``held_not_run``), never run on
a placeholder nor reported failed — unless it waited by ORDER only (amended
2026-10-30): reading none of the act, it runs whatever the answer was. A resumed
step may ask again: a new round. Work that ran BESIDE the acts (``told``) brings
the decision back here too, so the answer tells it beside the act's account —
answered by its card alone, a refusal read « OK, c'est annulé » over an archive
that did happen (measured 2026-10-30).

Owner rule (2026-10-31): a validated act runs to its end, and the person gets its
result. A confirmed TOOL CALL is reported like the step it is (``acted``): what it
returned — a dedicated agent's task, a read asked under « always ask » — is the
content the person asked for, which its card alone (« Action executed ») dropped.
So a plan that asked a tool call comes back here, and so does every answer to a
question a step of the plan asked: the step's result is then its act's, never the
draft it stood on — a resumed step that asked was reported « awaiting your
confirmation » after its act ran (measured on dev, 2026-10-31).

The response then reads ``executed_drafts`` and executes nothing a second time
(the ledger would only serve a record anyway — probe Hb, 2026-10-29).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING, Any

import structlog

from src.core.field_names import FIELD_RESULT
from src.domains.agents.constants import (
    STATE_KEY_COMPLETED_STEPS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_EXECUTION_PLAN,
)
from src.domains.agents.data_registry.state import registry_as_dicts
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.draft_decision import execute_decided_draft
from src.domains.agents.nodes.draft_sequence import (
    STATE_KEY_DRAFT_ACTION_RESULT,
    STATE_KEY_EXECUTED_DRAFTS,
    STATE_KEY_HELD_PLAN,
)
from src.domains.agents.nodes.execution_state import state_after_execution
from src.domains.agents.orchestration.held_steps import (
    held_by_order_only,
    told_after_the_answer,
)
from src.domains.agents.orchestration.plan_schemas import FOR_EACH_ITEM_INFIX, for_each_parent_id
from src.domains.agents.tools.mcp_task_record import settled_line

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.orchestration.parallel_executor import ParallelExecutionResult
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

logger = structlog.get_logger(__name__)

#: Why a waiting step was left unrun: the person refused an act it needed, the
#: act failed when it was run, or it was approved and still awaits a step of its
#: own (an application command's interaction, ADR-339) — it has not happened yet.
REFUSED, FAILED, WAITING = "refused", "failed", "waiting"


def held_plan_of(
    plan: ExecutionPlan, outcome: ParallelExecutionResult, *, previous: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The plan's waiting steps after a pass, carrying what earlier rounds settled.

    Args:
        plan: The plan that ran.
        outcome: What the pass returned.
        previous: The held plan of the round that resumed, None on a first pass.

    Returns:
        ``{plan_id, held, ordered, pending, told, resumed, not_run, acted}`` —
        ``ordered`` the held steps that wait by order only, ``told`` the steps
        that ran beside the acts (computed on the first pass, then carried),
        ``acted`` the steps reported with what their confirmed tool calls
        returned (carried) —, or None when nothing waits, nothing is to be told,
        no round resumed and no tool call was asked: a native draft's card says
        its act.
    """
    pending: dict[str, list[str]] = {}
    for draft in outcome.pending_drafts:
        if draft.step_id:
            pending.setdefault(draft.step_id, []).append(draft.draft_id)
    resumed = list((previous or {}).get("resumed") or [])
    not_run = dict((previous or {}).get("not_run") or {})
    acted = list((previous or {}).get("acted") or [])
    told = (
        told_after_the_answer(plan, pending, outcome.completed_steps.keys())
        if previous is None
        else list(previous.get("told") or [])
    )
    asked_a_tool_call = any(
        draft.step_id and draft.draft_type == DraftType.TOOL_CALL.value
        for draft in outcome.pending_drafts
    )
    if not any((outcome.held_steps, resumed, not_run, told, acted, asked_a_tool_call)):
        return None
    return {
        "plan_id": plan.plan_id,
        "held": dict(outcome.held_steps),
        "ordered": sorted(held_by_order_only(plan, pending) & outcome.held_steps.keys()),
        "pending": pending,
        "told": told,
        "resumed": resumed,
        "not_run": not_run,
        "acted": acted,
    }


def resume_due(state: MessagesState) -> bool:
    """Whether the orchestrator is entered to RESUME: the answers are in, and steps
    wait for them, work ran beside the acts for the answer to tell, or a step of the
    plan asked the question — its result becomes its act's."""
    held_plan = state.get(STATE_KEY_HELD_PLAN) or {}
    due = held_plan.get("held") or held_plan.get("told") or held_plan.get("pending")
    return bool(due) and state.get(STATE_KEY_DRAFT_ACTION_RESULT) is not None


async def resume_held_steps(
    state: MessagesState, config: RunnableConfig, run_id: str
) -> dict[str, Any]:
    """Execute the decided drafts, then run the steps that waited for them.

    Args:
        state: The graph state, the sequence settled (``draft_action_result``).
        config: The node's config.
        run_id: The run.

    Returns:
        The orchestrator's state update, with ``executed_drafts`` for the
        response and the next round's ``held_plan``.
    """
    from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel

    held_plan: dict[str, Any] = dict(state.get(STATE_KEY_HELD_PLAN) or {})
    decision, shown = await _settle_decision(state, config, run_id)
    records = _records(decision, shown)
    completed = dict(state.get(STATE_KEY_COMPLETED_STEPS) or {})
    pending: dict[str, list[str]] = held_plan.get("pending") or {}
    injected = _inject(completed, pending, records, state)
    not_run = {
        **(held_plan.get("not_run") or {}),
        **_unrunnable(held_plan["held"], records, ordered=held_plan.get("ordered") or ()),
    }

    plan: ExecutionPlan = state[STATE_KEY_EXECUTION_PLAN]
    runnable = plan.model_copy(
        update={"steps": [s for s in plan.steps if s.step_id not in not_run]}
    )
    outcome = await execute_plan_parallel(
        runnable,
        config,
        run_id,
        initial_registry=registry_as_dicts(state.get("registry")),
        turn_id=state.get(STATE_KEY_CURRENT_TURN_ID),
        initial_completed_steps=completed,
    )
    carried = _carried(
        held_plan,
        plan,
        outcome,
        completed=completed,
        pending=pending,
        injected=injected,
        records=records,
    )
    reported = {*carried["resumed"], *carried["told"], *carried["acted"]}
    logger.info(
        "plan_resumed",
        run_id=run_id,
        plan_id=plan.plan_id,
        resumed=carried["resumed"],
        acted=carried["acted"],
        not_run_count=len(not_run),
        drafts_executed=len(records),
    )
    # The state keeps the WHOLE plan: what was left unrun is named from it.
    update = state_after_execution(
        plan,
        outcome,
        state,
        run_id,
        held_plan=held_plan_of(plan, outcome, previous={**carried, "not_run": not_run}),
        reported_steps=[s for s in plan.steps if s.step_id in reported],
        counted_steps=[s for s in plan.steps if s.step_id in carried["resumed"]],
    )
    update[STATE_KEY_EXECUTED_DRAFTS] = _executed_drafts(state, decision, shown)
    update[STATE_KEY_DRAFT_ACTION_RESULT] = None
    return update


async def _settle_decision(
    state: MessagesState, config: RunnableConfig, run_id: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Execute the person's decision once, through the response's own door.

    Returns:
        The decision, and the record its execution returned (None when it
        executed nothing; an error record when it failed — never a raise).
    """
    decision: dict[str, Any] = dict(state.get(STATE_KEY_DRAFT_ACTION_RESULT) or {})
    return decision, await execute_decided_draft(state, config, run_id)


def _resumed(
    held_plan: dict[str, Any],
    plan: ExecutionPlan,
    outcome: ParallelExecutionResult,
    *,
    already: dict[str, Any],
) -> list[str]:
    """Every step a round resumed: the earlier rounds', then this pass's, in plan order."""
    ran = [
        s.step_id
        for s in plan.steps
        if s.step_id in outcome.completed_steps and s.step_id not in already
    ]
    return [*(held_plan.get("resumed") or []), *ran]


def _carried(
    held_plan: dict[str, Any],
    plan: ExecutionPlan,
    outcome: ParallelExecutionResult,
    *,
    completed: dict[str, Any],
    pending: dict[str, list[str]],
    injected: list[str],
    records: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    """The steps this round reports, and the next one carries: resumed, told, acted.

    A step whose question this decision answered stands on its act now: its
    draft is never reported again, and a tool call's result is (``acted``).

    Args:
        held_plan: The round's held plan.
        plan: The plan.
        outcome: What this round's pass returned.
        completed: The steps completed before the pass, real results injected.
        pending: The drafts this round asked, by step.
        injected: The steps given their real result.
        records: Each decided draft's record, by draft id.

    Returns:
        ``{"resumed", "told", "acted"}``, each in plan or asking order.
    """
    asked = {_plan_step(step_id) for step_id in pending}
    return {
        "resumed": [
            s for s in _resumed(held_plan, plan, outcome, already=completed) if s not in asked
        ],
        "told": list(held_plan.get("told") or []),
        "acted": _acted(held_plan, injected, pending, records),
    }


def _plan_step(step_id: str) -> str:
    """The plan's own step behind an id: a FOR_EACH item reports through its parent."""
    return for_each_parent_id(step_id) or step_id


def _acted(
    held_plan: dict[str, Any],
    injected: list[str],
    pending: dict[str, list[str]],
    records: dict[str, dict[str, Any]],
) -> list[str]:
    """Every round's steps reported with what their confirmed tool calls returned.

    A tool call's account says it ran (« Action executed »); what it returned is
    the step's real result, which only the step's report carries. A native
    draft's account says its act whole, so its step is never reported.
    """
    acted = list(held_plan.get("acted") or [])
    for step_id in injected:
        drafts = pending.get(step_id) or []
        tool_calls = all(
            (records.get(draft) or {}).get("draft_type") == DraftType.TOOL_CALL.value
            for draft in drafts
        )
        if drafts and tool_calls and _plan_step(step_id) not in acted:
            acted.append(_plan_step(step_id))
    return acted


def _executed_drafts(
    state: MessagesState, decision: dict[str, Any], shown: dict[str, Any] | None
) -> dict[str, dict[str, Any]]:
    """Every decision the rounds executed, this one's record added under its key."""
    executed: dict[str, dict[str, Any]] = dict(state.get(STATE_KEY_EXECUTED_DRAFTS) or {})
    if shown is not None:
        executed[_decision_key(decision)] = shown
    return executed


def _decision_key(decision: dict[str, Any]) -> str:
    """One key per decision: a draft's id, or every id of a batch."""
    batch = decision.get("batch")
    if isinstance(batch, list):
        return "batch:" + "+".join(str(entry.get("draft_id")) for entry in batch)
    return str(decision.get("draft_id"))


def _records(decision: dict[str, Any], shown: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Each decided draft's own record (status and data), by draft id."""
    if shown is None:
        return {}
    batch = (shown.get("data") or {}).get("batch_results")
    if isinstance(batch, list):
        return {str(entry.get("draft_id")): entry for entry in batch if isinstance(entry, dict)}
    return {str(decision.get("draft_id")): shown}


def _unrunnable(
    held: dict[str, list[str]],
    records: dict[str, dict[str, Any]],
    *,
    ordered: Collection[str] = (),
) -> dict[str, str]:
    """The waiting steps an act they need did not happen for, and why.

    A step waiting by order only needs the act SETTLED, not done: it stays
    waiting while an approved act still waits on its own, and runs otherwise.
    """
    reasons: dict[str, str] = {}
    for step_id, blockers in held.items():
        statuses = [(records.get(draft) or {}).get("status") for draft in blockers]
        if step_id in ordered:
            if "waiting" in statuses:
                reasons[step_id] = WAITING
            continue
        if all(status == "success" for status in statuses):
            continue
        if "cancelled" in statuses:
            reasons[step_id] = REFUSED
        else:
            reasons[step_id] = WAITING if "waiting" in statuses else FAILED
    return reasons


def _inject(
    completed: dict[str, Any],
    pending: dict[str, list[str]],
    records: dict[str, dict[str, Any]],
    state: MessagesState,
) -> list[str]:
    """Give each step whose acts all ran its REAL result, in place.

    A step with one draft IS that act: its result is the act's (projected like
    a call of the step, Task 3's projection). A step with several — an
    iterative MCP task — keeps its own result, followed by a line the code
    writes stating each act's outcome: no single value of several acts stands
    for them all.

    Returns:
        The steps given their real result, in the order they were asked.
    """
    injected: list[str] = []
    for step_id, drafts in pending.items():
        settled = [records.get(draft) for draft in drafts]
        if not all(record and record.get("status") == "success" for record in settled):
            continue
        injected.append(step_id)
        if len(drafts) == 1 and settled[0] is not None:
            completed[step_id] = _step_result(settled[0], step_id, state)
            continue
        entry = dict(completed.get(step_id) or {})
        names = [_act_name(record or {}) for record in settled]
        entry[FIELD_RESULT] = "\n".join(
            part for part in (str(entry.get(FIELD_RESULT) or ""), settled_line(names)) if part
        )
        completed[step_id] = entry
    _reaggregate(completed, injected)
    return injected


def _reaggregate(completed: dict[str, Any], injected: list[str]) -> None:
    """Aggregate again a FOR_EACH whose items were given their real results.

    Later steps read the PARENT's aggregate, which the first pass built from the
    items' drafts: left as it was, a waiting step would read the placeholders.
    """
    from src.domains.agents.orchestration.for_each_aggregation import (
        aggregate_for_each_results,
    )

    for parent in dict.fromkeys(p for p in map(for_each_parent_id, injected) if p):
        items = sorted((k for k in completed if for_each_parent_id(k) == parent), key=_item_index)
        aggregate_for_each_results(completed, parent, items)


def _item_index(step_id: str) -> int:
    """A FOR_EACH item's position, from its id (``step_2_item_3`` → 3; ``for_each_parent_id``)."""
    return int(step_id.rpartition(FOR_EACH_ITEM_INFIX)[2])


def _act_name(record: dict[str, Any]) -> str:
    """The registered name of the tool a record's act ran (sanitised, never an RPC name)."""
    content = (record.get("data") or {}).get("_draft_content") or {}
    return str(content.get("tool_name") or record.get("draft_type") or "")


def _step_result(record: dict[str, Any], step_id: str, state: MessagesState) -> dict[str, Any]:
    """What the step reads once its act ran: the act's own data."""
    from src.domains.agents.orchestration.step_results import project_tool_result
    from src.domains.agents.tools.output import UnifiedToolOutput

    data = {k: v for k, v in (record.get("data") or {}).items() if not str(k).startswith("_")}
    if {"success", "message", "registry_updates"} <= data.keys():
        projected = project_tool_result(
            UnifiedToolOutput.model_validate(data),
            tool_name=_act_name(record),
            step_id=step_id,
            turn_id=state.get(STATE_KEY_CURRENT_TURN_ID),
            correlation_parent_id=None,
            manifest=None,
            data_share=1,
        )
        result: dict[str, Any] = projected.result["data"]
        return result
    inner = data.get("data")
    return dict(inner) if isinstance(inner, dict) else data
