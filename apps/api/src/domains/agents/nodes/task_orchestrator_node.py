"""
TaskOrchestrator node (Phase 5.2B - Map-Reduce Dispatcher).

This node orchestrates plan execution using Map-Reduce pattern with parallel execution.

Architecture Evolution:
    Version 1 (Legacy): Sequential execution - creates simple plan and routes to first agent
    Version 2 (Phase 5.1): ExecutionPlan with PlanExecutor (sequential)
    Version 3 (Phase 5.2B - CURRENT): Map-Reduce dispatcher with parallel waves

Flow:
    - If execution_plan (ExecutionPlan) in state → Dispatch waves via Send() API
    - Else → Legacy: create simple plan and route to agent

Map-Reduce Pattern:
    1. Dispatcher (task_orchestrator_node):
       - Analyze dependencies with DependencyGraph
       - Initialize completed_steps = {}
       - Dispatch Wave 0 via Send() to step_executor_node
       - Route to wave_aggregator_node

    2. Workers (step_executor_node):
       - Execute steps in parallel
       - Return StepResult

    3. Reducer (wave_aggregator_node):
       - Merge StepResults into completed_steps
       - Check if plan complete
       - If not: dispatch next wave via Send()
       - If complete: route to response_node

Phase 5.2B Changes:
    - _handle_execution_plan() refactored to use DependencyGraph + Send()
    - Removed PlanExecutor (sequential) in favor of parallel dispatcher
    - Added wave_id tracking for Prometheus metrics
    - Thread-safe completed_steps management

References:
    - dependency_graph.py: Wave calculation
    - step_executor_node.py: Worker execution
    - wave_aggregator_node.py: Wave synchronization (to be created)
"""

import time
from functools import lru_cache
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt

from src.core.config import settings
from src.core.constants import API_MAX_ITEMS_PER_REQUEST
from src.core.field_names import FIELD_METADATA, FIELD_RUN_ID
from src.domains.agents.constants import (
    HITL_DECISION_APPROVE,
    HITL_DECISION_EDIT,
    HITL_DECISION_REJECT,
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_FOR_EACH_CANCELLATION_REASON,
    STATE_KEY_FOR_EACH_CANCELLED,
    STATE_KEY_LAST_ACTION_TURN_ID,
    STATE_KEY_LAST_LIST_DOMAIN,
    STATE_KEY_LAST_LIST_TURN_ID,
    STATE_KEY_MESSAGES,
    STATE_KEY_ORCHESTRATION_PLAN,
    STATE_KEY_PLANNER_ERROR,
    STATE_KEY_ROUTING_HISTORY,
)
from src.domains.agents.data_registry.models import RegistryItemType, generate_registry_id
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration import (
    create_orchestration_plan,
    map_execution_result_to_agent_result,
)
from src.domains.agents.orchestration.for_each_utils import parse_for_each_reference
from src.domains.agents.services.hitl.item_filter import get_item_filter_service
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
    hitl_for_each_approval_latency,
    hitl_for_each_decisions,
    hitl_for_each_items_counted,
    hitl_for_each_pre_execution_duration,
    hitl_for_each_pre_execution_total,
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


async def _pre_execute_for_each_providers(
    execution_plan: "ExecutionPlan",
    for_each_steps: list[dict],
    config: RunnableConfig,
    run_id: str,
    initial_registry: dict[str, Any] | None = None,
    turn_id: int | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, int], dict[str, Any]]:
    """
    Pre-execute provider steps for FOR_EACH HITL to get accurate item counts.

    This function is called BEFORE HITL confirmation to:
    1. Identify provider steps (e.g., get_events in "$steps.get_events.events")
    2. Execute them (with their dependencies)
    3. Count actual items in results

    This ensures HITL shows the real number of items affected, not the schema
    default (for_each_max). For example, "Crée un rappel pour mes 2 prochains rdv"
    will show "2 éléments" instead of "10 éléments".

    Args:
        execution_plan: The full ExecutionPlan
        for_each_steps: List of dicts with FOR_EACH step info (step_id, for_each_source)
        config: RunnableConfig with user context
        run_id: Run ID for logging
        initial_registry: Registry from state (for reference resolution)
        turn_id: Current turn ID for RegistryItem.meta injection

    Returns:
        Tuple of:
        - completed_steps: Dict of step_id -> result (for passing to execute_plan_parallel)
        - item_counts: Dict of for_each_source -> actual item count (for HITL display)
        - pre_exec_registry: Registry items from pre-executed steps (for merging into initial_registry)

    Example:
        >>> for_each_steps = [{"step_id": "create_reminder", "for_each_source": "$steps.get_events.events"}]
        >>> completed_steps, item_counts = await _pre_execute_for_each_providers(...)
        >>> # completed_steps = {"get_events": {"events": [...], "success": True}}
        >>> # item_counts = {"$steps.get_events.events": 2}
    """
    from src.core.constants import FOR_EACH_PRE_EXECUTION_METADATA_KEY
    from src.domains.agents.orchestration.for_each_utils import (
        count_items_at_path,
        get_for_each_provider_step_id,
        parse_for_each_reference,
    )
    from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel

    pre_exec_start_time = time.time()

    # Identify unique provider step_ids
    provider_step_ids: set[str] = set()
    for_each_sources: dict[str, str] = {}  # step_id -> for_each_source

    for step_info in for_each_steps:
        for_each_source = step_info.get("for_each_source", "")
        provider_id = get_for_each_provider_step_id(for_each_source)
        if provider_id:
            provider_step_ids.add(provider_id)
            for_each_sources[step_info["step_id"]] = for_each_source

    if not provider_step_ids:
        logger.warning(
            "for_each_hitl_no_providers_found",
            run_id=run_id,
            for_each_steps=[s["step_id"] for s in for_each_steps],
        )
        hitl_for_each_pre_execution_total.labels(outcome="failure").inc()
        return {}, {}, {}

    logger.info(
        "for_each_hitl_pre_executing_providers",
        run_id=run_id,
        provider_step_ids=list(provider_step_ids),
        for_each_sources=for_each_sources,
    )

    # Build a sub-plan with only provider steps and their dependencies
    from src.domains.agents.orchestration.dependency_graph import DependencyGraph
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan as EP

    dep_graph = DependencyGraph(execution_plan)
    steps_by_id = {step.step_id: step for step in execution_plan.steps}

    # Collect all steps needed (providers + their dependencies)
    steps_to_execute: set[str] = set()
    for provider_id in provider_step_ids:
        steps_to_execute.add(provider_id)
        deps = dep_graph.get_all_dependencies(provider_id)
        steps_to_execute.update(deps)

    # Create sub-plan with only needed steps
    sub_plan_steps = [
        steps_by_id[step_id] for step_id in steps_to_execute if step_id in steps_by_id
    ]

    if not sub_plan_steps:
        logger.warning(
            "for_each_hitl_no_steps_to_execute",
            run_id=run_id,
            provider_step_ids=list(provider_step_ids),
        )
        hitl_for_each_pre_execution_total.labels(outcome="failure").inc()
        return {}, {}, {}

    # Create sub-plan with essential metadata from original plan
    # Preserve: domains, intent, user_goal (needed for proper tool execution context)
    original_metadata = execution_plan.metadata or {}
    sub_plan_metadata = {
        FOR_EACH_PRE_EXECUTION_METADATA_KEY: True,
        # Propagate essential fields for tool execution context
        "domains": original_metadata.get("domains"),
        "intent": original_metadata.get("intent"),
        "user_goal": original_metadata.get("user_goal"),
    }

    sub_plan = EP(
        plan_id=f"{execution_plan.plan_id}_pre_exec",
        user_id=execution_plan.user_id,
        steps=sub_plan_steps,
        metadata=sub_plan_metadata,
    )

    logger.info(
        "for_each_hitl_sub_plan_created",
        run_id=run_id,
        sub_plan_steps=[s.step_id for s in sub_plan_steps],
        original_plan_steps=len(execution_plan.steps),
    )

    # Execute sub-plan
    try:
        result = await execute_plan_parallel(
            execution_plan=sub_plan,
            config=config,
            run_id=run_id,
            initial_registry=initial_registry,
            turn_id=turn_id,
        )
        completed_steps = result.completed_steps

        # Record success metric and duration
        pre_exec_duration = time.time() - pre_exec_start_time
        hitl_for_each_pre_execution_duration.observe(pre_exec_duration)
        hitl_for_each_pre_execution_total.labels(outcome="success").inc()

        logger.info(
            "for_each_hitl_pre_execution_completed",
            run_id=run_id,
            completed_step_ids=list(completed_steps.keys()),
            duration_seconds=round(pre_exec_duration, 3),
        )

    except Exception as e:
        # Record failure metric
        hitl_for_each_pre_execution_total.labels(outcome="failure").inc()

        logger.error(
            "for_each_hitl_pre_execution_failed",
            run_id=run_id,
            error=str(e),
            exc_info=True,
        )
        return {}, {}, {}

    # Count items in results using centralized utility (DRY)
    item_counts: dict[str, int] = {}

    for step_info in for_each_steps:
        for_each_source = step_info.get("for_each_source", "")
        provider_id, field_path = parse_for_each_reference(for_each_source)

        if not provider_id or not field_path or provider_id not in completed_steps:
            continue

        # Use centralized count function (DRY - from for_each_utils.py)
        result_data = completed_steps[provider_id]
        count = count_items_at_path(result_data, field_path)
        item_counts[for_each_source] = count

        # Record items counted metric
        if count > 0:
            hitl_for_each_items_counted.observe(count)

    logger.info(
        "for_each_hitl_item_counts",
        run_id=run_id,
        item_counts=item_counts,
    )

    # BugFix 2026-01-24: Return the registry from pre-execution
    # This registry contains items from provider steps (e.g., events from get_events_tool)
    # Without this, when dependent steps fail (e.g., routes with null destinations),
    # the parent items are lost and not displayed
    pre_exec_registry = result.registry or {}

    return completed_steps, item_counts, pre_exec_registry


def _extract_item_previews_for_hitl(
    pre_exec_registry: dict[str, Any],
    for_each_steps: list[dict],
    completed_steps: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract item previews from pre-executed registry for FOR_EACH HITL display.

    This function provides "Informed HITL" - showing users exactly what items
    will be affected before they confirm a bulk operation.

    Args:
        pre_exec_registry: Registry items from pre-execution (RegistryItem objects)
        for_each_steps: List of for_each step info dicts
        completed_steps: Completed step results with actual data

    Returns:
        List of preview dicts with key fields per domain type

    Example output:
        [
            {"subject": "Meeting tomorrow", "from": "john@example.com"},
            {"subject": "Project update", "from": "jane@example.com"},
        ]
    """
    from src.core.constants import FOR_EACH_PREVIEW_FIELDS

    previews: list[dict[str, Any]] = []

    # Get the for_each source to identify which items to preview
    if not for_each_steps:
        return previews

    # Use first for_each step's source to find items
    for_each_source = for_each_steps[0].get("for_each_source", "")
    provider_id, field_path = parse_for_each_reference(for_each_source)

    if not provider_id or not field_path or provider_id not in completed_steps:
        return previews

    # Get items from completed step (reuse centralized utility - DRY)
    result_data = completed_steps[provider_id]
    items = extract_value_by_path(result_data, field_path)

    if not items or not isinstance(items, list):
        return previews

    # Detect domain from registry items or field path
    domain = _detect_domain_from_items(pre_exec_registry, field_path)

    # Get preview fields for this domain
    preview_fields = FOR_EACH_PREVIEW_FIELDS.get(domain, [])

    # Build previews for each item (no artificial limit - bounded by api_max_items_per_request)
    for item in items:
        if not isinstance(item, dict):
            continue

        preview: dict[str, Any] = {}
        for field_path_tuple in preview_fields:
            primary_path, fallback_path = field_path_tuple
            value = extract_value_by_path(item, primary_path)
            if value is None and fallback_path:
                value = extract_value_by_path(item, fallback_path)
            if value is not None:
                # Use last part of path as key (e.g., "names.0.displayName" -> "displayName")
                key = primary_path.split(".")[-1]
                preview[key] = value

        if preview:
            previews.append(preview)

    logger.debug(
        "item_previews_extracted",
        domain=domain,
        preview_count=len(previews),
        total_items=len(items),
    )

    return previews


def _detect_domain_from_items(
    pre_exec_registry: dict[str, Any],
    field_path: str,
) -> str:
    """
    Detect domain from registry items or field path.

    Uses registry item types or infers from centralized mapping (DRY).

    Args:
        pre_exec_registry: Registry with RegistryItem objects
        field_path: Field path like "emails", "events", "contacts"

    Returns:
        Domain string (e.g., "email", "event", "contact")
    """
    from src.domains.agents.utils.type_domain_mapping import get_domain_from_result_key

    # Try to get domain from registry items
    for item in pre_exec_registry.values():
        if hasattr(item, "meta") and hasattr(item.meta, "domain"):
            return item.meta.domain

    # Fallback: use centralized mapping (DRY)
    domain = get_domain_from_result_key(field_path)
    return domain or "unknown"


def _filter_registry_by_items(
    pre_exec_registry: dict[str, Any],
    filtered_items: list[dict[str, Any]],
    field_path: str,
    run_id: str,
) -> dict[str, Any]:
    """
    Filter pre_exec_registry to keep only items matching filtered_items.

    After FOR_EACH HITL filtering, pre_executed_steps contains filtered items
    but pre_exec_registry still has all original items. This causes response_node
    to see the full list and generate incorrect responses.

    This function:
    1. Gets registry config from centralized mapping (type_domain_mapping)
    2. Extracts unique keys from filtered_items
    3. Regenerates expected registry IDs
    4. Filters pre_exec_registry to keep only matching items

    Args:
        pre_exec_registry: Registry dict with RegistryItem objects (keyed by registry_id)
        filtered_items: List of items to KEEP (from pre_executed_steps after filtering)
        field_path: Field path like "emails", "events", "contacts"
        run_id: For logging

    Returns:
        Filtered registry dict containing only items matching filtered_items
    """
    from src.domains.agents.utils.type_domain_mapping import (
        ITEMS_KEY_TO_REGISTRY_CONFIG,
        get_registry_config_for_items_key,
    )

    if not pre_exec_registry or not filtered_items:
        return pre_exec_registry

    # Get domain config from centralized mapping (DRY)
    config = get_registry_config_for_items_key(field_path)
    if not config:
        logger.warning(
            "filter_registry_unknown_domain",
            run_id=run_id,
            field_path=field_path,
            available_domains=list(ITEMS_KEY_TO_REGISTRY_CONFIG.keys()),
        )
        return pre_exec_registry

    registry_type_name, unique_key_field = config

    # Convert type name to RegistryItemType enum
    item_type = RegistryItemType(registry_type_name)

    # Extract unique keys from filtered items and generate expected registry IDs
    expected_ids: set[str] = set()
    for item in filtered_items:
        unique_key = item.get(unique_key_field)
        if unique_key:
            registry_id = generate_registry_id(item_type, unique_key)
            expected_ids.add(registry_id)

    if not expected_ids:
        logger.warning(
            "filter_registry_no_unique_keys",
            run_id=run_id,
            field_path=field_path,
            unique_key_field=unique_key_field,
            item_count=len(filtered_items),
        )
        return pre_exec_registry

    # Filter registry to keep only expected items
    filtered_registry = {
        registry_id: item
        for registry_id, item in pre_exec_registry.items()
        if registry_id in expected_ids
    }

    logger.info(
        "registry_filtered_after_for_each",
        run_id=run_id,
        field_path=field_path,
        original_count=len(pre_exec_registry),
        filtered_count=len(filtered_registry),
        expected_ids_count=len(expected_ids),
    )

    return filtered_registry


# ============================================================================
# Phase 5: ExecutionPlan Handler
# ============================================================================


async def _handle_execution_plan(
    execution_plan: "ExecutionPlan", state: MessagesState, run_id: str, config: RunnableConfig
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
    from langgraph.types import interrupt

    from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel
    from src.domains.agents.services.hitl.protocols import HitlInteractionType
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

        if for_each_steps_requiring_hitl:
            user_language = state.get("user_language", "fr")
            user_timezone = state.get("user_timezone", "Europe/Paris")

            # ================================================================
            # PRE-EXECUTE provider steps to get REAL item count
            # ================================================================
            # BugFix 2026-01-24: Also capture pre_exec_registry to preserve parent items
            # (e.g., events) when child steps (e.g., routes) fail
            pre_executed_steps, item_counts, pre_exec_registry = (
                await _pre_execute_for_each_providers(
                    execution_plan=execution_plan,
                    for_each_steps=for_each_steps_requiring_hitl,
                    config=config,
                    run_id=run_id,
                    initial_registry=initial_registry,
                    turn_id=current_turn_id,
                )
            )

            # Note: pre_exec_registry is passed to execute_plan_parallel separately
            # (not merged into initial_registry) so items are added to current_turn_touched_ids

            # Calculate total_affected from real counts
            if item_counts:
                # Sum of real counts from pre-execution
                total_affected = sum(item_counts.values())
            else:
                # Fallback to for_each_max if pre-execution failed
                total_affected = sum(s["for_each_max"] for s in for_each_steps_requiring_hitl)

            # FIX 2026-01-30: Extract item previews for "Informed HITL"
            # Shows users exactly what items will be affected before confirmation
            item_previews = _extract_item_previews_for_hitl(
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

            # ================================================================
            # FOR_EACH HITL EDIT Loop (2026-01-30)
            # ================================================================
            # Pattern: Similar to draft_critique EDIT loop in hitl_dispatch_node
            # Allows user to exclude items from the list before confirmation
            # Example: "remove emails from Guy Savoy" filters out matching items
            # ================================================================
            # Safety limit: max iterations = max items possible in a request
            # (user can't filter more times than there are items)
            max_edit_iterations = API_MAX_ITEMS_PER_REQUEST
            iteration = 0
            current_item_previews = item_previews  # Start with full list
            current_total_affected = total_affected
            # Track filtered indices mapping (for applying to real data)
            filtered_indices: list[int] | None = None

            # Helper to build cancellation result (DRY)
            def _build_cancel_result(reason: str) -> dict[str, Any]:
                return {
                    STATE_KEY_EXECUTION_PLAN: execution_plan,
                    STATE_KEY_AGENT_RESULTS: {},
                    STATE_KEY_FOR_EACH_CANCELLED: True,
                    STATE_KEY_FOR_EACH_CANCELLATION_REASON: reason,
                }

            # Skip HITL entirely when pre-execution yielded 0 items
            # (e.g. provider step failed with ClosedResourceError, or returned empty)
            if total_affected == 0:
                logger.info(
                    "for_each_hitl_skipped_no_items",
                    run_id=run_id,
                    plan_id=execution_plan.plan_id,
                    reason="total_affected is 0 after pre-execution",
                )

            while total_affected > 0 and iteration < max_edit_iterations:
                iteration += 1

                # Build interrupt payload with current (possibly filtered) items
                interrupt_payload = {
                    "action_requests": [
                        {
                            "type": HitlInteractionType.FOR_EACH_CONFIRMATION.value,
                            "plan_id": execution_plan.plan_id,
                            "steps": for_each_steps_requiring_hitl,
                            "total_affected": current_total_affected,
                            "item_previews": current_item_previews,
                            "iteration": iteration,
                        }
                    ],
                    "generate_question_streaming": True,
                    "user_language": user_language,
                    "user_timezone": user_timezone,
                }

                # Track start time for latency metric
                hitl_start_time = time.time()

                # Interrupt and wait for user decision
                decision_data = interrupt(interrupt_payload)

                # Record latency metric
                hitl_latency = time.time() - hitl_start_time
                hitl_for_each_approval_latency.observe(hitl_latency)

                # No decision - treat as cancellation
                if not decision_data:
                    hitl_for_each_decisions.labels(decision="cancel").inc()
                    logger.warning(
                        "for_each_hitl_no_decision",
                        run_id=run_id,
                        plan_id=execution_plan.plan_id,
                        iteration=iteration,
                        latency_seconds=round(hitl_latency, 2),
                    )
                    result = _build_cancel_result("No user decision received")
                    track_state_updates(state, result, "task_orchestrator", run_id)
                    return result

                decision = decision_data.get("decision", HITL_DECISION_REJECT)

                # ---- APPROVE: User confirmed, exit loop ----
                if decision == HITL_DECISION_APPROVE:
                    hitl_for_each_decisions.labels(decision="confirm").inc()
                    logger.info(
                        "for_each_hitl_confirmed",
                        run_id=run_id,
                        plan_id=execution_plan.plan_id,
                        iteration=iteration,
                        final_item_count=current_total_affected,
                        latency_seconds=round(hitl_latency, 2),
                    )
                    break  # Exit loop, continue to execution

                # ---- REJECT: User cancelled ----
                elif decision == HITL_DECISION_REJECT:
                    hitl_for_each_decisions.labels(decision="cancel").inc()
                    logger.info(
                        "for_each_hitl_cancelled",
                        run_id=run_id,
                        plan_id=execution_plan.plan_id,
                        decision=decision,
                        iteration=iteration,
                        latency_seconds=round(hitl_latency, 2),
                    )
                    reason = decision_data.get("rejection_reason", "User cancelled bulk operation")
                    result = _build_cancel_result(reason)
                    track_state_updates(state, result, "task_orchestrator", run_id)
                    return result

                # ---- EDIT: User wants to exclude items ----
                elif decision == HITL_DECISION_EDIT:
                    hitl_for_each_decisions.labels(decision="edit").inc()

                    exclude_criteria = decision_data.get("exclude_criteria", "")
                    if not exclude_criteria:
                        # No criteria provided - re-interrupt with same items
                        logger.warning(
                            "for_each_edit_no_criteria",
                            run_id=run_id,
                            plan_id=execution_plan.plan_id,
                            iteration=iteration,
                        )
                        continue

                    logger.info(
                        "for_each_edit_filtering_items",
                        run_id=run_id,
                        plan_id=execution_plan.plan_id,
                        iteration=iteration,
                        exclude_criteria=exclude_criteria[:100],
                        current_item_count=len(current_item_previews),
                    )

                    # Filter items using LLM-based ItemFilterService (imported at module level)
                    filter_service = get_item_filter_service()

                    try:
                        indices_to_keep = await filter_service.filter(
                            item_previews=current_item_previews,
                            exclude_criteria=exclude_criteria,
                            user_language=user_language,
                            run_id=run_id,
                        )
                    except Exception as filter_error:
                        logger.error(
                            "for_each_edit_filter_error",
                            run_id=run_id,
                            error=str(filter_error),
                            error_type=type(filter_error).__name__,
                        )
                        # On filter error, re-interrupt with same items
                        continue

                    # Apply filter to get new item preview list
                    filtered_previews = [current_item_previews[i] for i in indices_to_keep]

                    # Check if all items were excluded
                    if not filtered_previews:
                        hitl_for_each_decisions.labels(decision="cancel").inc()
                        logger.info(
                            "for_each_edit_all_excluded",
                            run_id=run_id,
                            plan_id=execution_plan.plan_id,
                            exclude_criteria=exclude_criteria[:100],
                            original_count=len(current_item_previews),
                        )
                        result = _build_cancel_result("All items excluded by user filter")
                        track_state_updates(state, result, "task_orchestrator", run_id)
                        return result

                    # Update tracking for filtered indices (cumulative mapping)
                    if filtered_indices is None:
                        # First filter - use original indices
                        filtered_indices = indices_to_keep
                    else:
                        # Subsequent filter - map through previous indices
                        filtered_indices = [filtered_indices[i] for i in indices_to_keep]

                    logger.info(
                        "for_each_edit_items_filtered",
                        run_id=run_id,
                        plan_id=execution_plan.plan_id,
                        iteration=iteration,
                        original_count=len(current_item_previews),
                        filtered_count=len(filtered_previews),
                        excluded_count=len(current_item_previews) - len(filtered_previews),
                        exclude_criteria=exclude_criteria[:100],
                    )

                    # Update for next iteration
                    current_item_previews = filtered_previews
                    current_total_affected = len(filtered_previews)
                    # Loop continues to re-interrupt with filtered items

                else:
                    # Unknown decision - treat as cancellation for safety
                    hitl_for_each_decisions.labels(decision="cancel").inc()
                    logger.warning(
                        "for_each_hitl_unknown_decision",
                        run_id=run_id,
                        plan_id=execution_plan.plan_id,
                        decision=decision,
                        iteration=iteration,
                    )
                    result = _build_cancel_result(f"Unknown decision: {decision}")
                    track_state_updates(state, result, "task_orchestrator", run_id)
                    return result

            # Check if we exited due to max iterations (without APPROVE)
            if iteration >= max_edit_iterations and decision != HITL_DECISION_APPROVE:
                logger.warning(
                    "for_each_hitl_max_iterations",
                    run_id=run_id,
                    plan_id=execution_plan.plan_id,
                    max_iterations=max_edit_iterations,
                )
                result = _build_cancel_result("Max HITL iterations reached")
                track_state_updates(state, result, "task_orchestrator", run_id)
                return result

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
                        pre_exec_registry = _filter_registry_by_items(
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
        # Data Registry LOT 4.3: Extract pending_draft for draft_critique_node
        pending_draft = execution_result_obj.pending_draft

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

            # Get re-plan attempt count from state (default 0 for first execution)
            replan_attempt = state.get("replan_attempt", 0)

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
                user_language="fr",  # TODO: Get from user preferences
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

            # Handle re-planning decisions
            # Note: For initial implementation, we log decisions and add user message if needed.
            # Full re-planning loop (regenerating plan) will be added in future iteration.
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
                # RETRY: Re-execute the failed step with same parameters
                # NOTE: Full implementation requires graph restructuring (edge back to executor)
                # For now, escalate to user if max retries exceeded
                retry_count = replan_result.retry_attempt or 0
                max_retries = settings.planner_max_replans

                logger.info(
                    "replan_retry_same",
                    step_id=replan_result.failed_step_id,
                    attempt=retry_count + 1,
                    max_retries=max_retries,
                )

                if retry_count >= max_retries:
                    # Max retries reached - escalate to user
                    replan_result.decision = RePlanDecision.ESCALATE_USER
                    replan_result.user_message = (
                        f"L'étape '{replan_result.failed_step_id}' a échoué après "
                        f"{retry_count} tentatives. Veuillez réessayer ou reformuler votre demande."
                    )
                    logger.warning(
                        "replan_retry_max_reached",
                        step_id=replan_result.failed_step_id,
                        max_retries=max_retries,
                    )
                # TODO: Implement actual retry via conditional edge to parallel_executor

            elif replan_result.decision == RePlanDecision.REPLAN_MODIFIED:
                # REPLAN: Generate a new plan with modifications
                # NOTE: Full implementation requires graph restructuring (edge back to planner)
                # For now, escalate to user with suggested modifications
                logger.info(
                    "replan_modified",
                    original_plan_steps=len(execution_plan.steps),
                    modified_parameters=replan_result.modified_parameters,
                )

                # Escalate to user with modification suggestions
                # TODO: Implement actual replanning via conditional edge to planner_node
                replan_result.decision = RePlanDecision.ESCALATE_USER
                modifications_summary = (
                    str(replan_result.modified_parameters)
                    if replan_result.modified_parameters
                    else "modifications suggérées"
                )
                replan_result.user_message = (
                    f"Le plan initial a rencontré des problèmes. "
                    f"Modifications suggérées: {modifications_summary[:200]}"
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
            "completed_steps": completed_steps,  # Preserve for debugging
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
        if pending_draft:
            draft_type = pending_draft.draft_type
            draft_data = pending_draft.model_dump()

            if draft_type == "entity_disambiguation":
                # Entity disambiguation: multiple entities match, need user choice
                # Check if there's already a pending disambiguation (multi-disambiguation protection)
                if "pending_entity_disambiguation" in result or state.get(
                    "pending_entity_disambiguation"
                ):
                    # Queue this disambiguation for later processing
                    queue = state.get("pending_disambiguations_queue", [])
                    queue.append(draft_data)
                    result["pending_disambiguations_queue"] = queue
                    logger.info(
                        "registry_disambiguation_queued",
                        run_id=run_id,
                        draft_id=pending_draft.draft_id,
                        queue_size=len(queue),
                    )
                else:
                    result["pending_entity_disambiguation"] = draft_data
                    logger.info(
                        "registry_pending_entity_disambiguation_added",
                        run_id=run_id,
                        plan_id=execution_plan.plan_id,
                        draft_id=pending_draft.draft_id,
                        draft_type=draft_type,
                    )

            elif draft_type == "tool_confirmation":
                # Tool confirmation: tools without drafts need explicit approval
                result["pending_tool_confirmation"] = draft_data
                logger.info(
                    "registry_pending_tool_confirmation_added",
                    run_id=run_id,
                    plan_id=execution_plan.plan_id,
                    draft_id=pending_draft.draft_id,
                    tool_name=pending_draft.tool_name,
                )

            else:
                # Default: draft critique for email/event/contact drafts
                result["pending_draft_critique"] = draft_data
                logger.info(
                    "registry_pending_draft_added_to_state",
                    run_id=run_id,
                    plan_id=execution_plan.plan_id,
                    draft_id=pending_draft.draft_id,
                    draft_type=draft_type,
                )

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
