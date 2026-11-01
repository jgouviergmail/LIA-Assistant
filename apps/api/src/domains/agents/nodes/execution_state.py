"""The state a plan execution leaves for the rest of the turn (spec 2026-10-29 D7).

Moved verbatim out of ``task_orchestrator_node._handle_execution_plan`` so the
first pass and the RESUME (``plan_resume``) leave the same state: the agent
results the response reads, the registry, the steps for reference resolution,
and the drafts routed to the confirmation sequence. One parameter tells a resume
apart (``reported_steps``): it reports only the steps IT ran, so the intermediate
results the person already saw stay out of the answer — as they do after a
confirmation —, and it counts no new plan in the plan metrics.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.field_names import FIELD_STEP_ID
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_COMPLETED_STEPS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_FOR_EACH_HITL_CTX,
    STATE_KEY_LAST_ACTION_TURN_ID,
    STATE_KEY_LAST_LIST_DOMAIN,
    STATE_KEY_LAST_LIST_TURN_ID,
    STATE_KEY_ORCHESTRATION_PLAN,
    STATE_KEY_ROUTING_HISTORY,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.draft_sequence import STATE_KEY_HELD_PLAN
from src.domains.agents.nodes.for_each_hitl_prep import is_pre_approved_lot
from src.domains.agents.orchestration import (
    build_execution_result,
    map_execution_result_to_agent_result,
)
from src.domains.agents.orchestration.step_failure_metrics import record_pipeline_step_failures
from src.domains.agents.orchestration.step_results import draft_ids
from src.domains.agents.orchestration.tool_data_projection import (
    previous_turns_without_tool_data,
    without_tool_data,
)
from src.domains.agents.utils.state_cleanup import (
    cleanup_dict_by_turn_id,
    cleanup_list_by_limit,
)
from src.domains.agents.utils.state_tracking import track_state_updates
from src.infrastructure.observability.metrics_agents import (
    orchestration_plan_agents_distribution,
    task_orchestrator_plans_created,
)

if TYPE_CHECKING:
    from src.domains.agents.orchestration.parallel_executor import ParallelExecutionResult
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep

logger = structlog.get_logger(__name__)


def state_after_execution(
    execution_plan: ExecutionPlan,
    execution_result_obj: ParallelExecutionResult,
    state: MessagesState,
    run_id: str,
    *,
    held_plan: dict[str, Any] | None,
    reported_steps: list[ExecutionStep] | None = None,
    counted_steps: list[ExecutionStep] | None = None,
) -> dict[str, Any]:
    """The orchestrator's state update after a plan ran.

    Args:
        execution_plan: The plan that ran.
        execution_result_obj: What the parallel executor returned.
        state: The graph state.
        run_id: The run, for the logs.
        held_plan: The steps still waiting for an answer, or None (spec D7).
        reported_steps: The steps whose results reach the answer; the whole
            plan when None, the steps a resume ran (and the work done beside
            the acts, spec D5) otherwise.
        counted_steps: The steps whose failures this pass counts — the
            reported ones when None: a resume counts what it RAN, never the
            work it tells again (the first pass counted it).

    Returns:
        The state update the orchestrator node returns.
    """
    # Data Registry LOT 5.2: Extract completed_steps and registry from result
    completed_steps = execution_result_obj.completed_steps
    data_registry = execution_result_obj.registry

    logger.info(
        "parallel_executor_completed",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        completed_steps=len(completed_steps),
        total_steps=len(execution_plan.steps),
        data_registry_items=len(data_registry),
    )
    # Each failed step counted under its typed code (ADR-346): the one
    # Prometheus view of a failure that happens before a tool is called.
    counted = reported_steps if counted_steps is None else counted_steps
    record_pipeline_step_failures(
        completed_steps
        if counted is None
        else {
            s.step_id: completed_steps[s.step_id] for s in counted if s.step_id in completed_steps
        }
    )

    turn_id = state.get(STATE_KEY_CURRENT_TURN_ID, 0)
    # The plan's steps as the mapper reads them: a FOR_EACH through the
    # aggregate under its own id (ADR-347).
    execution_result = build_execution_result(
        execution_plan.steps if reported_steps is None else reported_steps, completed_steps
    )
    all_steps_success = execution_result.success

    # BugFix 2025-11-26: Pass data_registry for Data Registry mode fallback
    # When tools run with registry_enabled=True, step_results only contain summary text.
    # The data_registry contains the full structured data (RegistryItems).
    agent_results = map_execution_result_to_agent_result(
        execution_result=execution_result,
        plan_id=execution_plan.plan_id,
        turn_id=turn_id,
        data_registry=data_registry,
    )

    # Track metrics — once per plan: a resume runs the same plan again.
    if reported_steps is None:
        task_orchestrator_plans_created.labels(
            intention="execution_plan_phase5.2b_asyncio",
            agents_count=str(len(execution_plan.steps)),
        ).inc()
        orchestration_plan_agents_distribution.observe(len(execution_plan.steps))

    # Cleanup state; a data block serves its own turn's response alone (ADR-347).
    cleaned_agent_results = cleanup_dict_by_turn_id(
        {
            **previous_turns_without_tool_data(state.get(STATE_KEY_AGENT_RESULTS, {}), turn_id),
            **agent_results,
        },
        max_results=settings.max_agent_results,
        label="agent_results",
    )
    cleaned_routing_history = cleanup_list_by_limit(
        state.get(STATE_KEY_ROUTING_HISTORY, []),
        max_items=settings.max_routing_history,
        label="routing_history",
    )

    result = {
        STATE_KEY_ORCHESTRATION_PLAN: None,  # No legacy routing
        STATE_KEY_EXECUTION_PLAN: execution_plan,  # Preserve for observability
        STATE_KEY_AGENT_RESULTS: cleaned_agent_results,
        STATE_KEY_ROUTING_HISTORY: cleaned_routing_history,
        # Read back by the response node to weigh a stale validation
        # verdict against what the turn actually ran — never its data.
        STATE_KEY_COMPLETED_STEPS: without_tool_data(completed_steps),
    }

    # CRITICAL FIX: Update last_action_turn_id for context reference resolution
    # When a successful action is executed, store the current turn_id so that
    # subsequent queries like "detail of the first one" can reference these results.
    # Without this, context_resolution_service.resolve_context() cannot find items.
    if all_steps_success and turn_id is not None:
        result[STATE_KEY_LAST_ACTION_TURN_ID] = turn_id
        logger.info(
            "last_action_turn_id_updated",
            run_id=run_id,
            turn_id=turn_id,
            reason="successful_execution_enables_reference_resolution",
        )

        # ================================================================
        # ORDINAL RESOLUTION: Track last LIST action domain (search/list only)
        # ================================================================
        # ONLY updated when the turn SHOWED a list (two items or more from a
        # step no other step consumed) — never by a lookup that was a means.
        #
        # Example flow:
        #   Turn 1: "search contacts" → last_list_domain = "contacts"
        #   Turn 2: "search tasks"    → last_list_domain = "tasks"
        #   Turn 3: "hi, how are you?" → last_list_domain = "tasks" (unchanged)
        #   Turn 4: "details of the first one"  → uses "tasks" (from state)
        #   Turn 5: "details of the 1st contact" → uses "contacts" (explicit override)
        #
        # This is CRITICAL because last_action_turn_id gets overwritten by
        # EVERY action (including details), but ordinal resolution needs
        # the domain of the LAST SEARCH, not the last action.
        # ================================================================
        list_domain = _detect_list_tool_domain(execution_plan, completed_steps, data_registry)
        if list_domain:
            result[STATE_KEY_LAST_LIST_DOMAIN] = list_domain
            result[STATE_KEY_LAST_LIST_TURN_ID] = turn_id
            logger.info(
                "last_list_domain_updated",
                run_id=run_id,
                turn_id=turn_id,
                domain=list_domain,
                reason="list_tool_executed_for_ordinal_resolution",
            )

    # Data Registry LOT 5.2: Add registry to state if non-empty
    # The registry field uses merge_registry reducer which handles merging
    # BugFix 2025-12-31: Also set current_turn_registry for streaming_service
    # - registry: merged across turns (for context resolution)
    # - current_turn_registry: current turn only (for display/streaming)
    if data_registry:
        result["registry"] = data_registry
        result["current_turn_registry"] = data_registry  # BugFix: no merge for display
        logger.info(
            "data_registry_added_to_state",
            run_id=run_id,
            plan_id=execution_plan.plan_id,
            registry_items_count=len(data_registry),
            registry_ids=list(data_registry.keys()),
        )

    _route_drafts(result, execution_result_obj, state, execution_plan.plan_id, run_id)

    # Purge the consumed FOR_EACH HITL context: once execution completed it
    # is functionally inert (plan/turn guards make it unmatchable), but
    # keeping it would bloat every subsequent checkpoint of the thread.
    if state.get(STATE_KEY_FOR_EACH_HITL_CTX):
        result[STATE_KEY_FOR_EACH_HITL_CTX] = None
    result[STATE_KEY_HELD_PLAN] = held_plan

    track_state_updates(state, result, "task_orchestrator", run_id)
    return result


def _route_drafts(
    result: dict[str, Any],
    execution_result_obj: ParallelExecutionResult,
    state: MessagesState,
    plan_id: str,
    run_id: str,
) -> None:
    """Route the pass's drafts to the confirmation sequence, in place.

    Args:
        result: The state update being built.
        execution_result_obj: What the parallel executor returned.
        state: The graph state.
        plan_id: The plan that ran, for the logs.
        run_id: The run, for the logs.
    """
    # Data Registry LOT 4.3 + HITL Dispatch: Route pending HITL by draft_type
    # Different draft types route to different pending state keys:
    # - tool_confirmation → pending_tool_confirmation (for tools without drafts)
    # - Other types (email, event, contact) → pending_draft_critique (for draft preview)
    #
    # Several draft critiques (ADR-288): the first is presented, the rest
    # queued. They are ONE lot — shown whole, confirmed whole — only when
    # they are the members of a FOR_EACH the person approved this turn;
    # otherwise the dispatch node asks for each in turn. Both keys are
    # ALWAYS written so a previous turn's values can never leak into this one.
    pending_drafts = execution_result_obj.pending_drafts
    result["pending_drafts_grouped"] = False
    result["confirmed_drafts"] = []

    if pending_drafts:
        # Separate drafts by routing type
        draft_critiques = []
        for draft in pending_drafts:
            draft_type = draft.draft_type
            draft_data = draft.model_dump()

            if draft_type == "tool_confirmation":
                result["pending_tool_confirmation"] = draft_data
                logger.info(
                    "registry_pending_tool_confirmation_added",
                    run_id=run_id,
                    plan_id=plan_id,
                    draft_id=draft.draft_id,
                    tool_name=draft.tool_name,
                )

            else:
                # Draft critique (email, event, contact, task, file, label)
                draft_critiques.append(draft_data)

        # Route draft critiques: single → direct, multiple → batch
        if len(draft_critiques) == 1:
            result["pending_draft_critique"] = draft_critiques[0]
            logger.info(
                "registry_pending_draft_added_to_state",
                run_id=run_id,
                plan_id=plan_id,
                draft_id=draft_critiques[0].get("draft_id"),
                draft_type=draft_critiques[0].get("draft_type"),
            )
        elif len(draft_critiques) > 1:
            # First presented, the rest queued; grouped only for a
            # pre-approved FOR_EACH lot (ADR-288).
            grouped = is_pre_approved_lot(
                draft_critiques,
                state.get(STATE_KEY_FOR_EACH_HITL_CTX),
                plan_id=plan_id,
                turn_id=state.get(STATE_KEY_CURRENT_TURN_ID),
            )
            result["pending_draft_critique"] = draft_critiques[0]
            result["pending_drafts_queue"] = draft_critiques[1:]
            result["pending_drafts_grouped"] = grouped
            logger.info(
                "registry_pending_batch_drafts_added_to_state",
                run_id=run_id,
                plan_id=plan_id,
                batch_size=len(draft_critiques),
                grouped=grouped,
                draft_types=sorted({str(d.get("draft_type")) for d in draft_critiques}),
                draft_ids=draft_ids(draft_critiques),
            )


def _detect_list_tool_domain(
    execution_plan: ExecutionPlan,
    completed_steps: dict[str, Any],
    registry: dict[str, Any],
) -> str | None:
    """The domain of the last list the turn SHOWED — what « the 2nd one » points into.

    Used for ordinal resolution when the person names no domain ("details of
    the 2nd one"). A shown list is two items or more that one completed step
    produced and no other step consumed: a lookup another step depends on is a
    means, not what was shown (ADR-367). The tool's NAME used to decide
    (``search_``/``list_``/``find_``/``query_`` prefixes), which no unified
    tool carries (``get_emails_tool``, ``get_events_tool``…): the list the
    person last saw was never recorded for the main domains.

    Args:
        execution_plan: The plan the turn ran.
        completed_steps: Step id → result, for the steps that completed.
        registry: The turn's registry items (each meta names its step and domain).

    Returns:
        The context domain (e.g. "emails"), or None when no list was shown.
    """
    consumed = execution_plan.consumed_step_ids()
    produced: Counter[tuple[str, str]] = Counter()
    for item in registry.values():
        meta = item.get("meta") if isinstance(item, dict) else None
        if isinstance(meta, dict) and meta.get(FIELD_STEP_ID) and meta.get("domain"):
            produced[(str(meta[FIELD_STEP_ID]), str(meta["domain"]))] += 1
    detected_domain: str | None = None
    for step in execution_plan.steps:
        if step.step_id in consumed or step.step_id not in completed_steps:
            continue
        for (step_id, domain), count in produced.items():
            if step_id == step.step_id and count >= 2:
                detected_domain = domain
    return detected_domain
