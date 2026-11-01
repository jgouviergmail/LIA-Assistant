"""
TaskOrchestrator node — single-node parallel plan execution (asyncio waves).

This node executes the validated ExecutionPlan inside ONE graph node, running
each dependency wave with ``asyncio.gather``. This is a deliberate architecture
decision (kept in sync with the ``_handle_execution_plan`` docstring below):
the earlier Map-Reduce topology (Send() dispatch to a ``step_executor_node``
worker + ``wave_aggregator_node`` reducer) was removed because the single-node
version is ~3x less code, has no framework-coupling surface, and keeps
``completed_steps`` management trivially thread-safe.

Flow:
    - If execution_plan (ExecutionPlan) in state → execute waves in-node via
      the parallel executor (asyncio.gather per dependency wave)
    - Else → Legacy: create simple plan and route to agent

Architecture Evolution:
    Version 1 (Legacy): Sequential execution - simple plan routed to first agent
    Version 2 (Phase 5.1): ExecutionPlan with PlanExecutor (sequential)
    Version 3 (Phase 5.2B): Map-Reduce dispatcher with Send() waves (removed)
    Version 4 (CURRENT): Single-node asyncio wave execution

References:
    - orchestration/dependency_graph.py: Wave calculation
    - orchestration/parallel_executor.py: asyncio.gather wave execution
"""

from functools import lru_cache
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt

from src.core.config import settings
from src.core.run_config import run_id_of
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_FOR_EACH_HITL_CTX,
    STATE_KEY_MESSAGES,
    STATE_KEY_ORCHESTRATION_PLAN,
    STATE_KEY_PLANNER_ERROR,
    STATE_KEY_ROUTING_HISTORY,
)
from src.domains.agents.data_registry.state import registry_as_dicts
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.execution_state import state_after_execution
from src.domains.agents.nodes.for_each_hitl_prep import (
    pre_execute_for_each_providers,
    refresh_for_each_scope_claims,
)
from src.domains.agents.nodes.for_each_preview_identity import (
    apply_filtered_source_items,
    original_selection_after_approval,
    prepare_preview_context,
)
from src.domains.agents.nodes.plan_choice import settle_plan_choice
from src.domains.agents.nodes.plan_resume import held_plan_of, resume_due, resume_held_steps
from src.domains.agents.orchestration import (
    create_orchestration_plan,
)
from src.domains.agents.utils.state_cleanup import (
    cleanup_dict_by_turn_id,
    cleanup_list_by_limit,
)
from src.domains.agents.utils.state_tracking import track_state_updates
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
    orchestration_plan_agents_distribution,
    task_orchestrator_plans_created,
)
from src.infrastructure.observability.tracing import trace_node

logger = structlog.get_logger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


# Import ExecutionPlan DSL (Phase 5)
try:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

    HAS_EXECUTION_PLAN = True
except ImportError:
    HAS_EXECUTION_PLAN = False


@trace_node("task_orchestrator")
@track_metrics(
    node_name="task_orchestrator",
    duration_metric=agent_node_duration_seconds,
    counter_metric=agent_node_executions_total,
)
async def task_orchestrator_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """Execute the turn's plan, or route a legacy single-agent request.

    - An ``ExecutionPlan`` from the planner runs INSIDE this node, wave by wave
      (``asyncio.gather`` per dependency wave, TOOL and CONDITIONAL steps), and
      its results reach the response as ``agent_results`` and
      ``completed_steps``. A failed step is never re-run here: the answer states
      it through the runtime failures directive (ADR-303, ADR-346).
    - Without a plan, the legacy path builds a simple orchestration plan from
      the router's intention and routes to the agent node it names.

    Args:
        state: Current LangGraph state with routing_history or execution_plan.
        config: Runnable config with metadata (run_id, etc.).

    Returns:
        Updated state with orchestration_plan and cleaned agent_results.

    Note:
        Basic metrics (duration, success/error counters) are tracked by the
        ``@track_metrics`` decorator; orchestrator-specific metrics
        (plans_created, ...) are tracked within the function.
    """
    run_id = run_id_of(config, "unknown")

    # Runtime semantic guard: expose the turn's resolved person names to the
    # parallel executor via configurable. Sourced from state (survives HITL
    # resume) and inherited by every execute_plan_parallel call below.
    from src.domains.agents.semantic.param_guard import config_with_person_names

    config = config_with_person_names(config, state)

    logger.info(
        "task_orchestrator_started",
        run_id=run_id,
        message_count=len(state[STATE_KEY_MESSAGES]),
        has_execution_plan=STATE_KEY_EXECUTION_PLAN in state,
    )

    try:
        # ====================================================================
        # Phase 5: Check if ExecutionPlan exists (from planner)
        # ====================================================================
        execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
        planner_error = state.get(STATE_KEY_PLANNER_ERROR)
        requires_hitl = state.get("requires_hitl", False)

        # CRITICAL FIX (Session 38): Check planner_error to trigger HITL
        # When plan is invalid, execution_plan = None BUT planner_error exists
        # We should show HITL to let user see error and decide (retry/cancel)
        has_valid_plan = execution_plan is not None and HAS_EXECUTION_PLAN
        has_planning_error = planner_error is not None

        # DEBUG: Log execution_plan state
        logger.info(
            "task_orchestrator_execution_plan_check",
            run_id=run_id,
            has_execution_plan_in_state=STATE_KEY_EXECUTION_PLAN in state,
            execution_plan_is_none=execution_plan is None,
            execution_plan_type=type(execution_plan).__name__ if execution_plan else "None",
            HAS_EXECUTION_PLAN=HAS_EXECUTION_PLAN,
            has_planner_error=has_planning_error,
            requires_hitl=requires_hitl,
            condition_result=has_valid_plan,
        )

        if has_valid_plan and resume_due(state):
            # Spec D7: the person answered; the steps that waited run on the
            # real results of the acts they approved.
            return await resume_held_steps(state, config, run_id)

        if has_valid_plan:
            logger.info(
                "task_orchestrator_using_execution_plan",
                run_id=run_id,
                plan_id=execution_plan.plan_id if hasattr(execution_plan, "plan_id") else "unknown",
                step_count=len(execution_plan.steps) if hasattr(execution_plan, "steps") else 0,
            )

            # Phase 5.2: Execute steps inline with CONDITIONAL support
            return await _handle_execution_plan(execution_plan, state, run_id, config)

        # ====================================================================
        # Legacy: Create simple orchestration plan from router intention
        # ====================================================================
        routing_history = state.get(STATE_KEY_ROUTING_HISTORY, [])

        if not routing_history:
            logger.warning(
                "task_orchestrator_no_routing_history",
                run_id=run_id,
            )
            # Fallback: no plan, will route directly to response
            result = {
                STATE_KEY_ORCHESTRATION_PLAN: None,
                STATE_KEY_AGENT_RESULTS: cleanup_dict_by_turn_id(
                    state.get(STATE_KEY_AGENT_RESULTS, {}),
                    max_results=settings.max_agent_results,
                    label="agent_results",
                ),
                STATE_KEY_ROUTING_HISTORY: cleanup_list_by_limit(
                    state.get(STATE_KEY_ROUTING_HISTORY, []),
                    max_items=settings.max_routing_history,
                    label="routing_history",
                ),
            }
            track_state_updates(state, result, "task_orchestrator", run_id)
            return result

        router_output = routing_history[-1]

        # 2. Create orchestration plan
        plan = await create_orchestration_plan(router_output, state)

        # 3. Cleanup old agent_results and routing_history (memory efficiency)
        cleaned_agent_results = cleanup_dict_by_turn_id(
            state.get(STATE_KEY_AGENT_RESULTS, {}),
            max_results=settings.max_agent_results,
            label="agent_results",
        )
        cleaned_routing_history: list[Any] = cleanup_list_by_limit(
            state.get(STATE_KEY_ROUTING_HISTORY, []),
            max_items=settings.max_routing_history,
            label="routing_history",
        )

        # 4. Track orchestration metrics
        agents_count = len(plan.agents_to_call)

        # Track plan creation
        task_orchestrator_plans_created.labels(
            intention=router_output.intention,
            agents_count=str(agents_count),
        ).inc()

        # Track agents distribution
        orchestration_plan_agents_distribution.observe(agents_count)

        logger.info(
            "task_orchestrator_plan_created",
            run_id=run_id,
            turn_id=state.get(STATE_KEY_CURRENT_TURN_ID, 0),
            intention=router_output.intention,
            agents_count=agents_count,
            agents=plan.agents_to_call,
            execution_mode=plan.execution_mode,
        )

        # 5. Return updated state
        # Note: Agent execution happens via conditional routing, not here
        result = {
            STATE_KEY_ORCHESTRATION_PLAN: plan,
            STATE_KEY_AGENT_RESULTS: cleaned_agent_results,
            STATE_KEY_ROUTING_HISTORY: cleaned_routing_history,
        }
        track_state_updates(state, result, "task_orchestrator", run_id)
        return result

    except GraphInterrupt:
        # LangGraph v1.0 HITL: interrupt() raised GraphInterrupt
        # This exception MUST be propagated to graph runner to pause execution
        logger.info(
            "graph_interrupt_detected_in_main_node",
            run_id=run_id,
            message="HITL approval required - propagating GraphInterrupt to graph runner",
        )
        # Re-raise to propagate to graph runner
        raise

    except Exception as e:
        logger.error(
            "task_orchestrator_failed",
            run_id=run_id,
            error=str(e),
            exc_info=True,
        )

        # Fallback: empty plan will route to response
        result = {
            STATE_KEY_ORCHESTRATION_PLAN: None,
            STATE_KEY_AGENT_RESULTS: cleanup_dict_by_turn_id(
                state.get(STATE_KEY_AGENT_RESULTS, {}),
                max_results=settings.max_agent_results,
                label="agent_results",
            ),
            STATE_KEY_ROUTING_HISTORY: cleanup_list_by_limit(
                state.get(STATE_KEY_ROUTING_HISTORY, []),
                max_items=settings.max_routing_history,
                label="routing_history",
            ),
        }
        track_state_updates(state, result, "task_orchestrator", run_id)
        return result


# ============================================================================
# Phase 5: Tool Registry Builder
# ============================================================================


@lru_cache(maxsize=1)
def _build_tool_registry() -> dict[str, Any]:
    """
    Build the tool_registry (mapping tool_name → tool_function).

    The tool_registry is required for PlanExecutor to execute
    tools directly without going through agents.

    Returns:
        Dict {tool_name: tool_function}

    Note:
        This function imports all available tools from tools/__init__.py.
        Any new tool added in tools/ will be automatically available.
        The result is cached so the registry is not rebuilt on every call.
    """
    from src.domains.agents.tools import (
        get_contact_details_tool,
        get_context_list,
        get_context_state,
        list_active_domains,
        list_contacts_tool,
        # Context Tools
        resolve_reference,
        # Google Contacts Tools
        search_contacts_tool,
        set_current_item,
    )

    registry = {
        # Google Contacts
        "search_contacts_tool": search_contacts_tool,
        "list_contacts_tool": list_contacts_tool,
        "get_contact_details_tool": get_contact_details_tool,
        # Context
        "resolve_reference": resolve_reference,
        "list_active_domains": list_active_domains,
        "set_current_item": set_current_item,
        "get_context_state": get_context_state,
        "get_context_list": get_context_list,
    }

    logger.debug("tool_registry_built", tool_count=len(registry), tools=list(registry.keys()))

    return registry


# ============================================================================
# FOR_EACH HITL Pre-Execution
# ============================================================================


# ============================================================================
# Phase 5: ExecutionPlan Handler
# ============================================================================


async def _handle_execution_plan(
    execution_plan: ExecutionPlan, state: MessagesState, run_id: str, config: RunnableConfig
) -> dict[str, Any]:
    """
    Handle ExecutionPlan using asyncio-based parallel execution (Phase 5.2B-asyncio).

    **Phase 5.2B-asyncio Implementation** (CURRENT):
    - Execute plan using native Python asyncio.gather()
    - No LangGraph Command+Send (broken in v1.0)
    - Direct wave-by-wave execution in single function call
    - Convert results to agent_results format for response_node

    **Architecture (asyncio Pattern)**:
        Orchestrator
            ↓ execute_plan_parallel()
        Parallel Executor (asyncio.gather)
            ↓ Wave 0: [step1, step2, step3] in parallel
            ↓ Wave 1: [step4] after wave 0
            ↓ Wave N: ...
        Return completed_steps
            ↓
        Convert to agent_results
            ↓
        Response Node (synthesize final response)

    **Key Changes from Phase 5.2B (Map-Reduce)**:
    - No Send() API → asyncio.gather() for true parallelism
    - No wave_aggregator node → single executor handles all waves
    - No step_executor node → inline step execution
    - Simpler code (~500 lines vs ~1500 lines)
    - No framework coupling bugs

    Args:
        execution_plan: ExecutionPlan from planner with validated steps
        state: Current state with messages, user context
        run_id: Run ID for logging and tracing
        config: RunnableConfig (thread plumbing); tool dependencies travel on the run context

    Returns:
        Updated state dict with:
        - execution_plan: Preserved for observability
        - completed_steps: Final results from execution
        - agent_results: Converted results for response_node

    Example Flow:
        1. Orchestrator: Call execute_plan_parallel()
        2. Executor: Wave 0: [search, fetch_config] → asyncio.gather()
        3. Executor: Wave 1: [validate] → asyncio.gather()
        4. Executor: Return completed_steps
        5. Orchestrator: Convert to agent_results → route to response

    Note:
        This function BLOCKS until all waves complete.
        No iterative dispatch needed - asyncio handles concurrency.
    """

    from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel
    from src.domains.agents.services.hitl.scope_detector import detect_for_each_scope

    try:
        logger.info(
            "parallel_executor_starting",
            run_id=run_id,
            plan_id=execution_plan.plan_id,
            total_steps=len(execution_plan.steps),
            execution_mode=execution_plan.execution_mode,
        )

        # ====================================================================
        # PREPARE REGISTRY FOR PRE-EXECUTION AND EXECUTION
        # ====================================================================
        # BugFix 2025-11-30: Pass existing registry from state for items[N].field resolution
        # This allows "details of the first one" to resolve items[0].id from previous search results
        # (parallel_executor expects dict format, not Pydantic models)
        initial_registry = registry_as_dicts(state.get("registry"))

        current_turn_id = state.get(STATE_KEY_CURRENT_TURN_ID)

        # ADR-367 amendment: an act on the first of several items a lookup found
        # asks which one first — the lookups run once, the plan resumes on them.
        choice = await settle_plan_choice(
            execution_plan, state, config, run_id, initial_registry=initial_registry
        )
        if choice.ask is not None:
            track_state_updates(state, choice.ask, "task_orchestrator", run_id)
            return choice.ask
        # The plan bound to the item the person designated (designation_repair).
        execution_plan = choice.plan_for(execution_plan)

        # ====================================================================
        # FOR_EACH HITL WITH PRE-EXECUTION
        # ====================================================================
        # BugFix 2026-01-19: Pre-execute provider steps to get accurate item count.
        # Before: HITL showed for_each_max (schema default = 10) instead of real count.
        # After: HITL shows real count by executing the provider step (e.g., get_events)
        # BEFORE asking for user confirmation.
        #
        # Flow:
        # 1. Detect FOR_EACH steps requiring HITL
        # 2. Pre-execute their provider steps (e.g., "$steps.get_events.events" → get_events)
        # 3. Count real items from execution results
        # 4. Show HITL with accurate count
        # 5. If approved, pass pre-executed steps to execute_plan_parallel (skip re-execution)
        # ====================================================================
        pre_executed_steps: dict[str, dict[str, Any]] = choice.completed
        # BugFix 2026-01-24: Track pre-executed registry for parent item preservation
        pre_exec_registry: dict[str, Any] = choice.registry

        # NOTE: FOR_EACH HITL is always enabled
        for_each_steps_requiring_hitl = []

        for step in execution_plan.steps:
            if step.for_each:
                # Detect if this for_each step requires HITL
                scope = detect_for_each_scope(
                    iteration_count=step.for_each_max,
                    tool_name=step.tool_name or "",
                    is_mutation=False,  # Auto-detected from tool_name
                    for_each_max=step.for_each_max,
                )

                if scope.requires_approval:
                    for_each_steps_requiring_hitl.append(
                        {
                            "step_id": step.step_id,
                            "tool_name": step.tool_name,
                            "for_each_max": step.for_each_max,
                            "for_each_source": step.for_each,
                            "is_mutation": scope.is_mutation,
                            "risk_level": scope.risk_level.value,
                            "reason": scope.reason,
                        }
                    )

        # Filtered indices from the confirm-node EDIT loop (None = no filtering)
        filtered_indices: list[int] | None = None

        if for_each_steps_requiring_hitl:
            # ================================================================
            # Replay-safe FOR_EACH HITL (2026-07)
            # ================================================================
            # The interrupt loop moved to the dedicated for_each_confirm node.
            # This node pre-executes the providers ONCE, persists everything in
            # for_each_hitl_ctx via a state-update RETURN (checkpointed BEFORE
            # any interrupt), and routes to the confirm node. On approval the
            # confirm node routes back here and execution resumes from the
            # persisted context — a resume never re-fetches providers nor
            # re-runs past LLM item filters.
            # ================================================================
            ctx = state.get(STATE_KEY_FOR_EACH_HITL_CTX)
            ctx_matches = (
                isinstance(ctx, dict)
                and ctx.get("plan_id") == execution_plan.plan_id
                and ctx.get("turn_id") == current_turn_id
            )

            if ctx_matches and ctx.get("approved"):
                # ── Approved: resume from the persisted context (no re-fetch) ──
                pre_executed_steps = ctx.get("pre_executed_steps") or {}
                pre_exec_registry = ctx.get("pre_exec_registry") or {}
                filtered_indices = original_selection_after_approval(
                    ctx, for_each_steps_requiring_hitl
                )
                logger.info(
                    "for_each_hitl_resumed_from_ctx",
                    run_id=run_id,
                    plan_id=execution_plan.plan_id,
                    pre_executed_step_ids=list(pre_executed_steps.keys()),
                    filtered_indices=filtered_indices,
                    final_item_count=ctx.get("total_affected"),
                )
            else:
                # ── First pass: pre-execute providers ONCE ──
                # BugFix 2026-01-24: Also capture pre_exec_registry to preserve
                # parent items (e.g., events) when child steps (e.g., routes) fail
                for_each_steps, item_counts, for_each_registry = (
                    await pre_execute_for_each_providers(
                        execution_plan=execution_plan,
                        for_each_steps=for_each_steps_requiring_hitl,
                        config=config,
                        run_id=run_id,
                        initial_registry=initial_registry,
                        turn_id=current_turn_id,
                    )
                )
                # A lookup narrowed by « which one? » keeps its narrowed result.
                pre_executed_steps = {**for_each_steps, **pre_executed_steps}
                pre_exec_registry = {**for_each_registry, **pre_exec_registry}

                # Note: pre_exec_registry is passed to execute_plan_parallel separately
                # (not merged into initial_registry) so items are added to
                # current_turn_touched_ids

                # Calculate total_affected from real counts
                if item_counts:
                    total_affected = sum(item_counts.values())
                else:
                    # Fallback to for_each_max if pre-execution failed
                    total_affected = sum(s["for_each_max"] for s in for_each_steps_requiring_hitl)

                # The reasons above were computed from for_each_max (the only
                # number known before pre-execution) — restate them with the
                # measured counts before anything user-facing reads them.
                refresh_for_each_scope_claims(for_each_steps_requiring_hitl, item_counts)

                # FIX 2026-01-30: Extract item previews for "Informed HITL"
                preview_context = prepare_preview_context(
                    pre_exec_registry, for_each_steps_requiring_hitl, pre_executed_steps
                )

                logger.info(
                    "for_each_hitl_required",
                    run_id=run_id,
                    plan_id=execution_plan.plan_id,
                    steps_requiring_hitl=len(for_each_steps_requiring_hitl),
                    steps=for_each_steps_requiring_hitl,
                    total_affected=total_affected,
                    item_counts=item_counts,
                    pre_executed_step_ids=list(pre_executed_steps.keys()),
                    item_previews_count=len(preview_context["item_previews"]),
                )

                if total_affected == 0:
                    # Skip HITL entirely when pre-execution yielded 0 items
                    # (e.g. provider failed or returned empty) — historical
                    # behaviour: continue execution with the pre-executed steps.
                    logger.info(
                        "for_each_hitl_skipped_no_items",
                        run_id=run_id,
                        plan_id=execution_plan.plan_id,
                        reason="total_affected is 0 after pre-execution",
                    )
                else:
                    # ── Persist the context and hand off to the confirm node ──
                    # (also reset the bulk-cancel flags from any previous turn)
                    result: dict[str, Any] = {
                        STATE_KEY_EXECUTION_PLAN: execution_plan,
                        "for_each_cancelled": False,
                        "cancellation_reason": None,
                        STATE_KEY_FOR_EACH_HITL_CTX: {
                            "run_id": run_id,
                            "plan_id": execution_plan.plan_id,
                            "turn_id": current_turn_id,
                            "steps": for_each_steps_requiring_hitl,
                            "pre_executed_steps": pre_executed_steps,
                            "pre_exec_registry": pre_exec_registry,
                            **preview_context,
                            "total_affected": total_affected,
                            "iteration": 0,
                            "approved": False,
                        },
                    }
                    track_state_updates(state, result, "task_orchestrator", run_id)
                    return result

            # (Interrupt loop moved to for_each_confirm_node — replay-safe.)

            # ================================================================
            # CRITICAL: Apply filtering to REAL data in pre_executed_steps
            # ================================================================
            # The filtered_indices represent which items to KEEP from the original list.
            # We must update pre_executed_steps so execute_plan_parallel uses filtered data.
            # ================================================================
            if filtered_indices is not None and for_each_steps_requiring_hitl:
                pre_exec_registry = apply_filtered_source_items(
                    pre_executed_steps,
                    pre_exec_registry,
                    for_each_steps_requiring_hitl,
                    filtered_indices,
                    run_id,
                )

        # Execute plan with asyncio-based parallel execution
        # Data Registry LOT 5.2: Returns ParallelExecutionResult with completed_steps and registry
        # Data Registry LOT 4.3: Also returns pending_draft if tool requires confirmation
        # BugFix 2025-12-19: Pass turn_id for RegistryItem.meta injection (context resolution)
        # BugFix 2026-01-19: Pass pre_executed_steps to avoid re-executing provider steps
        # BugFix 2026-01-24: Pass pre_exec_registry to preserve parent items when child steps fail
        # A step nobody chose an item for never runs (ADR-367 amendment); the
        # state keeps the WHOLE plan, so what was left unrun is named from it.
        execution_result_obj = await execute_plan_parallel(
            execution_plan=choice.runnable(execution_plan),
            config=config,
            run_id=run_id,
            initial_registry=initial_registry,
            turn_id=current_turn_id,
            # Empty reads as none: the executor tests both for truth.
            initial_completed_steps=pre_executed_steps,
            pre_executed_registry=pre_exec_registry,
        )

        return state_after_execution(
            execution_plan,
            execution_result_obj,
            state,
            run_id,
            held_plan=held_plan_of(
                execution_plan, execution_result_obj, previous=choice.held_previous()
            ),
        )

    except GraphInterrupt:
        # HITL support (Phase 5.3)
        logger.warning(
            "graph_interrupt_in_parallel_execution",
            run_id=run_id,
            plan_id=execution_plan.plan_id if hasattr(execution_plan, "plan_id") else "unknown",
        )
        raise

    except Exception as e:
        logger.error(
            "parallel_executor_failed",
            run_id=run_id,
            plan_id=execution_plan.plan_id if hasattr(execution_plan, "plan_id") else "unknown",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

        # Fallback: Return to response with error
        result = {
            STATE_KEY_ORCHESTRATION_PLAN: None,
            STATE_KEY_EXECUTION_PLAN: None,
            STATE_KEY_AGENT_RESULTS: cleanup_dict_by_turn_id(
                state.get(STATE_KEY_AGENT_RESULTS, {}),
                max_results=settings.max_agent_results,
                label="agent_results",
            ),
            STATE_KEY_ROUTING_HISTORY: cleanup_list_by_limit(
                state.get(STATE_KEY_ROUTING_HISTORY, []),
                max_items=settings.max_routing_history,
                label="routing_history",
            ),
        }
        track_state_updates(state, result, "task_orchestrator", run_id)
        return result
