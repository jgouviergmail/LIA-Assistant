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
from src.core.field_names import FIELD_METADATA, FIELD_RUN_ID
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_COMPLETED_STEPS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_FOR_EACH_HITL_CTX,
    STATE_KEY_LAST_ACTION_TURN_ID,
    STATE_KEY_LAST_LIST_DOMAIN,
    STATE_KEY_LAST_LIST_TURN_ID,
    STATE_KEY_MESSAGES,
    STATE_KEY_ORCHESTRATION_PLAN,
    STATE_KEY_PLANNER_ERROR,
    STATE_KEY_ROUTING_HISTORY,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.for_each_hitl_prep import (
    extract_item_previews_for_hitl,
    filter_registry_by_items,
    pre_execute_for_each_providers,
    refresh_for_each_scope_claims,
)
from src.domains.agents.orchestration import (
    create_orchestration_plan,
    map_execution_result_to_agent_result,
)
from src.domains.agents.orchestration.for_each_utils import parse_for_each_reference
from src.domains.agents.tools.runtime_helpers import extract_value_by_path
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
    """
    TaskOrchestrator node: Orchestrates agent execution based on plan type.

    **Phase 5 Enhancement**: Dual-mode orchestration
    - Mode 1 (Phase 5): ExecutionPlan from planner → Execute steps sequentially
    - Mode 2 (Legacy): Simple plan from hardcoded mapping → Route to single agent

    Version 1 (Legacy): Sequential execution - simple plan routes to first agent.
    Version 2 (Phase 5 MVP): Executes ExecutionPlan TOOL steps, delegates to agents.
    Version 3 (Future): Parallel execution, CONDITIONAL steps, REPLAN.

    Args:
        state: Current LangGraph state with routing_history or execution_plan.
        config: Runnable config with metadata (run_id, etc.).

    Returns:
        Updated state with orchestration_plan and cleaned agent_results.

    Note:
        Basic metrics (duration, success/error counters) are tracked automatically
        by @track_metrics decorator. Orchestrator-specific metrics (plans_created, etc.)
        are still tracked manually within the function.

    Flow Examples:

    **Phase 5 (ExecutionPlan from planner)**:
        1. Planner generates ExecutionPlan with TOOL/CONDITIONAL steps
        2. TaskOrchestrator detects execution_plan in state
        3. For MVP: Convert ExecutionPlan → simple orchestration_plan
        4. Route to first agent (future: execute steps inline)

    **Legacy (Simple routing)**:
        1. Router detects intention="contacts_search"
        2. TaskOrchestrator creates plan: agents_to_call=["contacts_agent"]
        3. Conditional routing sends to contacts_agent node
        4. Agent executes and returns result
        5. Response node synthesizes

    Note:
        MVP implementation (Phase 5.1): Detect ExecutionPlan and convert to
        simple orchestration_plan for legacy routing. Full step-by-step execution
        with CONDITIONAL/REPLAN support deferred to Phase 5.2.
    """
    run_id = config.get(FIELD_METADATA, {}).get(FIELD_RUN_ID, "unknown")

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
        Le résultat est mis en cache pour éviter de reconstruire le registre à chaque appel.
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
        config: RunnableConfig with __deps for tool dependency injection

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
        # This allows "details du premier" to resolve items[0].id from previous search results
        existing_registry = state.get("registry", {})

        # Convert RegistryItem objects to dicts for parallel_executor
        # (parallel_executor expects dict format, not Pydantic models)
        initial_registry = {}
        for item_id, item in existing_registry.items():
            if hasattr(item, "model_dump"):
                initial_registry[item_id] = item.model_dump()
            elif isinstance(item, dict):
                initial_registry[item_id] = item
            else:
                initial_registry[item_id] = {"payload": item}

        current_turn_id = state.get(STATE_KEY_CURRENT_TURN_ID)

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
        pre_executed_steps: dict[str, dict[str, Any]] = {}
        # BugFix 2026-01-24: Track pre-executed registry for parent item preservation
        pre_exec_registry: dict[str, Any] = {}

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
                filtered_indices = ctx.get("filtered_indices")
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
                pre_executed_steps, item_counts, pre_exec_registry = (
                    await pre_execute_for_each_providers(
                        execution_plan=execution_plan,
                        for_each_steps=for_each_steps_requiring_hitl,
                        config=config,
                        run_id=run_id,
                        initial_registry=initial_registry,
                        turn_id=current_turn_id,
                    )
                )

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
                item_previews = extract_item_previews_for_hitl(
                    pre_exec_registry=pre_exec_registry,
                    for_each_steps=for_each_steps_requiring_hitl,
                    completed_steps=pre_executed_steps,
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
                    item_previews_count=len(item_previews),
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
                            "item_previews": item_previews,
                            "total_affected": total_affected,
                            "filtered_indices": None,
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
                # Get for_each source to identify data location
                for_each_source = for_each_steps_requiring_hitl[0].get("for_each_source", "")
                provider_id, field_path = parse_for_each_reference(for_each_source)

                if provider_id and field_path and provider_id in pre_executed_steps:
                    result_data = pre_executed_steps[provider_id]
                    original_items = extract_value_by_path(result_data, field_path)

                    if original_items and isinstance(original_items, list):
                        # Keep only items at filtered indices
                        filtered_items = [original_items[i] for i in filtered_indices]

                        # Update the step result with filtered items
                        # field_path is simple (e.g., "emails", "events") for FOR_EACH sources
                        if field_path in result_data:
                            result_data[field_path] = filtered_items

                        logger.info(
                            "for_each_data_filtered_in_pre_executed_steps",
                            run_id=run_id,
                            provider_id=provider_id,
                            field_path=field_path,
                            original_count=len(original_items),
                            filtered_count=len(filtered_items),
                            filtered_indices=filtered_indices,
                        )

                        # ================================================================
                        # CRITICAL: Also filter pre_exec_registry (Issue 2 Fix)
                        # ================================================================
                        # Without this, response_node sees all original items and generates
                        # incorrect responses (shows list instead of confirming action).
                        # ================================================================
                        pre_exec_registry = filter_registry_by_items(
                            pre_exec_registry=pre_exec_registry,
                            filtered_items=filtered_items,
                            field_path=field_path,
                            run_id=run_id,
                        )

        # Execute plan with asyncio-based parallel execution
        # Data Registry LOT 5.2: Returns ParallelExecutionResult with completed_steps and registry
        # Data Registry LOT 4.3: Also returns pending_draft if tool requires confirmation
        # BugFix 2025-12-19: Pass turn_id for RegistryItem.meta injection (context resolution)
        # BugFix 2026-01-19: Pass pre_executed_steps to avoid re-executing provider steps
        # BugFix 2026-01-24: Pass pre_exec_registry to preserve parent items when child steps fail
        execution_result_obj = await execute_plan_parallel(
            execution_plan=execution_plan,
            config=config,
            run_id=run_id,
            initial_registry=initial_registry,
            turn_id=current_turn_id,
            initial_completed_steps=pre_executed_steps if pre_executed_steps else None,
            pre_executed_registry=pre_exec_registry if pre_exec_registry else None,
        )

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

        # ====================================================================
        # INTELLIPLANNER Phase E: Adaptive Re-Planning Analysis
        # ====================================================================
        # Analyze execution results and decide if re-planning is beneficial
        from src.domains.agents.orchestration.adaptive_replanner import (
            AdaptiveRePlanner,
            RePlanContext,
            RePlanDecision,
            analyze_execution_results,
            should_trigger_replan,
        )

        # Quick check if re-planning should be considered
        should_replan, replan_trigger = should_trigger_replan(
            execution_plan=execution_plan,
            completed_steps=completed_steps,
        )

        if should_replan:
            # Full analysis for re-planning decision
            execution_analysis = analyze_execution_results(
                execution_plan=execution_plan,
                completed_steps=completed_steps,
            )

            # Advisory-only contract (ADR-128): the replanner is a consultative
            # analyzer — no retry or replan is ever executed, so there is NO
            # attempt progression. The attempt is fixed at 0 (the first and only
            # pass) and is deliberately not read from a state key, because none is
            # ever written (removing that phantom "retry state" keeps the code
            # honest about the committed advisory contract; F017).
            replan_attempt = 0

            # Build context for decision
            user_message = ""
            if state.get(STATE_KEY_MESSAGES):
                last_human = next(
                    (
                        m
                        for m in reversed(state[STATE_KEY_MESSAGES])
                        if hasattr(m, "type") and m.type == "human"
                    ),
                    None,
                )
                if last_human:
                    user_message = (
                        last_human.content if hasattr(last_human, "content") else str(last_human)
                    )

            replan_context = RePlanContext(
                user_request=user_message,
                user_language=state.get("user_language", "fr"),
                execution_plan=execution_plan,
                plan_id=execution_plan.plan_id,
                completed_steps=completed_steps,
                execution_analysis=execution_analysis,
                replan_attempt=replan_attempt,
                max_attempts=settings.adaptive_replanning_max_attempts,
            )

            # Get re-planning decision
            replanner = AdaptiveRePlanner()
            replan_result = replanner.analyze_and_decide(replan_context)

            logger.info(
                "adaptive_replanner_decision",
                run_id=run_id,
                plan_id=execution_plan.plan_id,
                trigger=replan_result.trigger.value,
                decision=replan_result.decision.value,
                reasoning=replan_result.reasoning,
                recovery_strategy=replan_result.recovery_strategy.value,
                attempt=replan_attempt,
            )

            # Handle re-planning decisions.
            #
            # TODO(D4 — adaptive recovery is advisory only, not wired):
            #   The AdaptiveRePlanner computes a recovery decision (RETRY_SAME /
            #   REPLAN_MODIFIED / ESCALATE_USER / ABORT / PROCEED) on every
            #   plan failure, but the orchestrator currently only LOGS it — no
            #   decision changes control flow. Wiring true automatic recovery
            #   requires graph restructuring in the LangGraph builder:
            #     - RETRY_SAME     → a conditional edge from task_orchestrator
            #                        back to parallel_executor, re-running only
            #                        the failed step(s), bounded by
            #                        settings.planner_max_replans, with the
            #                        retry_attempt counter persisted in state
            #                        (a new MessagesState key — undeclared keys
            #                        are dropped by the checkpoint reducer).
            #     - REPLAN_MODIFIED→ a conditional edge back to planner_node_v3
            #                        with replan_result.modified_parameters +
            #                        recovery_strategy (e.g. SKIP_OPTIONAL) fed
            #                        into the prompt, then re-validate + re-exec.
            #     - ESCALATE_USER / ABORT → surface replan_result.user_message
            #                        (already i18n via _get_abort_message) by
            #                        writing it to a state key that response_node
            #                        renders, instead of only logging it.
            #   Until then, keep this block HONEST: every branch below must not
            #   claim an action it does not perform, and must not fabricate a
            #   user message that nothing renders (the failed-step results flow
            #   to response_node, which surfaces the failure). See ADR-128 (D4).
            #   Scope note: this is a genuine feature (a recovery loop), not a
            #   bug — deliberately deferred; do not "fix" it by silently adding
            #   inline messages or fake retries.
            if replan_result.decision == RePlanDecision.ESCALATE_USER:
                # Add user message to state for response_node to display
                if replan_result.user_message:
                    # TODO: Add message to state when implementing full re-planning loop
                    logger.info(
                        "replan_escalate_user_message",
                        message=replan_result.user_message[:200],
                    )

            elif replan_result.decision == RePlanDecision.ABORT:
                # Add error message for response_node
                if replan_result.user_message:
                    # TODO: Add message to state when implementing full re-planning loop
                    logger.warning(
                        "replan_abort_message",
                        message=replan_result.user_message[:200],
                    )

            elif replan_result.decision == RePlanDecision.RETRY_SAME:
                # Automatic retry is NOT wired: it would require a conditional
                # edge back to the parallel executor (graph restructuring). The
                # replanner still emits this decision as an observability signal,
                # but no re-execution happens — log honestly (audit D4). The
                # failed step results already flow to response_node below, which
                # surfaces the failure. No inline user message is fabricated
                # here: nothing reads replan_result.user_message (it is neither
                # written to state nor rendered).
                logger.info(
                    "replan_retry_not_wired",
                    step_id=replan_result.failed_step_id,
                    decision="retry_same",
                    msg="Replanner suggested retry_same; automatic recovery is not "
                    "implemented — surfacing the step failure instead of retrying",
                )

            elif replan_result.decision == RePlanDecision.REPLAN_MODIFIED:
                # Automatic replanning is NOT wired either (would need an edge
                # back to planner_node). Log the suggestion honestly; the
                # failure surfaces via agent_results (audit D4).
                logger.info(
                    "replan_modified_not_wired",
                    original_plan_steps=len(execution_plan.steps),
                    modified_parameters=replan_result.modified_parameters,
                    msg="Replanner suggested a modified plan; automatic recovery "
                    "is not implemented — surfacing the failure instead",
                )

        # Convert completed_steps to agent_results format
        # Reuse conversion logic from wave_aggregator
        from src.domains.agents.orchestration.schemas import (
            ExecutionResult,
        )
        from src.domains.agents.orchestration.schemas import (
            StepResult as LegacyStepResult,
        )

        turn_id = state.get(STATE_KEY_CURRENT_TURN_ID, 0)

        # Build ExecutionResult-like structure for mapper
        legacy_step_results = []
        for idx, step in enumerate(execution_plan.steps):
            if step.step_id in completed_steps:
                step_data = completed_steps[step.step_id]
                legacy_step_results.append(
                    LegacyStepResult(
                        step_index=idx,
                        tool_name=step.tool_name or step.step_id,
                        args=step.parameters or {},
                        result=step_data if isinstance(step_data, dict) else {"data": step_data},
                        success=(
                            step_data.get("success", True) if isinstance(step_data, dict) else True
                        ),
                        error=step_data.get("error") if isinstance(step_data, dict) else None,
                    )
                )

        # Calculate overall success: True only if ALL steps succeeded
        all_steps_success = (
            all(sr.success for sr in legacy_step_results) if legacy_step_results else True
        )

        # Find first failed step for error reporting
        failed_step_index = None
        first_error = None
        for idx, sr in enumerate(legacy_step_results):
            if not sr.success:
                failed_step_index = idx
                first_error = sr.error
                break

        execution_result = ExecutionResult(
            success=all_steps_success,
            step_results=legacy_step_results,
            total_steps=len(execution_plan.steps),
            completed_steps=len(completed_steps),
            failed_step_index=failed_step_index,
            error=first_error,
            total_execution_time_ms=0,  # Already logged by parallel_executor
        )

        # BugFix 2025-11-26: Pass data_registry for Data Registry mode fallback
        # When tools run with registry_enabled=True, step_results only contain summary text.
        # The data_registry contains the full structured data (RegistryItems).
        agent_results = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id=execution_plan.plan_id,
            turn_id=turn_id,
            data_registry=data_registry,
        )

        # Track metrics
        task_orchestrator_plans_created.labels(
            intention="execution_plan_phase5.2b_asyncio",
            agents_count=str(len(execution_plan.steps)),
        ).inc()
        orchestration_plan_agents_distribution.observe(len(execution_plan.steps))

        # Cleanup state
        cleaned_agent_results = cleanup_dict_by_turn_id(
            {**state.get(STATE_KEY_AGENT_RESULTS, {}), **agent_results},
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
            # verdict against what the turn actually ran.
            STATE_KEY_COMPLETED_STEPS: completed_steps,
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
            # ONLY updated when a LIST tool (search_*, list_*, find_*) executes.
            # NOT updated for chat, weather, perplexity, details, etc.
            #
            # Example flow:
            #   Turn 1: "recherche contacts" → last_list_domain = "contacts"
            #   Turn 2: "recherche taches"   → last_list_domain = "taches"
            #   Turn 3: "salut ca va?"       → last_list_domain = "taches" (unchanged)
            #   Turn 4: "detail du premier"  → uses "taches" (from state)
            #   Turn 5: "detail du 1er contact" → uses "contacts" (explicit override)
            #
            # This is CRITICAL because last_action_turn_id gets overwritten by
            # EVERY action (including details), but ordinal resolution needs
            # the domain of the LAST SEARCH, not the last action.
            # ================================================================
            list_domain = _detect_list_tool_domain(execution_plan.steps, completed_steps)
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

        # Data Registry LOT 4.3 + HITL Dispatch: Route pending HITL by draft_type
        # Different draft types route to different pending state keys:
        # - entity_disambiguation → pending_entity_disambiguation (for multiple matches)
        # - tool_confirmation → pending_tool_confirmation (for tools without drafts)
        # - Other types (email, event, contact) → pending_draft_critique (for draft preview)
        #
        # Batch draft support: When FOR_EACH produces multiple drafts of the same type,
        # we store them all in pending_draft_critique as a batch for grouped confirmation.
        pending_drafts = execution_result_obj.pending_drafts

        if pending_drafts:
            # Separate drafts by routing type
            draft_critiques = []
            for draft in pending_drafts:
                draft_type = draft.draft_type
                draft_data = draft.model_dump()

                if draft_type == "entity_disambiguation":
                    if "pending_entity_disambiguation" in result or state.get(
                        "pending_entity_disambiguation"
                    ):
                        # A NEW list, never `state.get(...).append(...)`: mutating
                        # the object held by the state channel makes a replay of
                        # this node (HITL resume re-enters it) append a second
                        # time to the list it already grew.
                        queue = [*state.get("pending_disambiguations_queue", []), draft_data]
                        result["pending_disambiguations_queue"] = queue
                        logger.info(
                            "registry_disambiguation_queued",
                            run_id=run_id,
                            draft_id=draft.draft_id,
                            queue_size=len(queue),
                        )
                    else:
                        result["pending_entity_disambiguation"] = draft_data
                        logger.info(
                            "registry_pending_entity_disambiguation_added",
                            run_id=run_id,
                            plan_id=execution_plan.plan_id,
                            draft_id=draft.draft_id,
                            draft_type=draft_type,
                        )

                elif draft_type == "tool_confirmation":
                    result["pending_tool_confirmation"] = draft_data
                    logger.info(
                        "registry_pending_tool_confirmation_added",
                        run_id=run_id,
                        plan_id=execution_plan.plan_id,
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
                    plan_id=execution_plan.plan_id,
                    draft_id=draft_critiques[0].get("draft_id"),
                    draft_type=draft_critiques[0].get("draft_type"),
                )
            elif len(draft_critiques) > 1:
                # Batch: store first as pending_draft_critique, rest in queue
                # hitl_dispatch_node will handle batch confirmation
                result["pending_draft_critique"] = draft_critiques[0]
                result["pending_drafts_queue"] = draft_critiques[1:]
                logger.info(
                    "registry_pending_batch_drafts_added_to_state",
                    run_id=run_id,
                    plan_id=execution_plan.plan_id,
                    batch_size=len(draft_critiques),
                    draft_type=draft_critiques[0].get("draft_type"),
                    draft_ids=[d.get("draft_id") for d in draft_critiques],
                )

        # Purge the consumed FOR_EACH HITL context: once execution completed it
        # is functionally inert (plan/turn guards make it unmatchable), but
        # keeping it would bloat every subsequent checkpoint of the thread.
        if state.get(STATE_KEY_FOR_EACH_HITL_CTX):
            result[STATE_KEY_FOR_EACH_HITL_CTX] = None

        track_state_updates(state, result, "task_orchestrator", run_id)
        return result

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


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _detect_list_tool_domain(
    steps: list,
    completed_steps: dict,
) -> str | None:
    """
    Detect domain from successfully executed LIST tools (search_*, list_*, find_*).

    Scans executed steps to find LIST-type tools and extract their domain.
    Returns the domain of the LAST successfully executed LIST tool.

    This is used for ordinal resolution: "detail du 2ème" needs to know
    which domain's list to use when the user doesn't specify.

    Uses centralized utilities from type_domain_mapping.py for consistency.

    Args:
        steps: List of ExecutionStep from the execution plan.
        completed_steps: Dict of step_id -> result for completed steps.

    Returns:
        Domain name (e.g., "contacts", "emails") or None if no LIST tool found.

    Examples:
        >>> # search_contacts_tool executed successfully
        >>> _detect_list_tool_domain(steps, completed_steps)
        "contacts"

        >>> # get_contact_details_tool executed (not a LIST tool)
        >>> _detect_list_tool_domain(steps, completed_steps)
        None
    """
    from src.domains.agents.utils.type_domain_mapping import (
        get_domain_from_tool_name,
        is_list_tool,
    )

    detected_domain: str | None = None

    for step in steps:
        # Skip if step wasn't completed successfully
        if step.step_id not in completed_steps:
            continue

        tool_name = step.tool_name
        if not tool_name:
            continue

        # Check if this is a LIST tool and extract domain
        if is_list_tool(tool_name):
            domain = get_domain_from_tool_name(tool_name)
            if domain:
                detected_domain = domain

    return detected_domain
