"""FOR_EACH HITL preparation — pre-execution, measured claims, previews.

Extracted verbatim from ``task_orchestrator_node`` (2026-08-17, file-size
ratchet): the cohesive unit that runs BEFORE a FOR_EACH bulk confirmation is
shown to the user. It pre-executes the provider steps once, measures the real
item counts, restates the scope claims with those counts (ADR-185: a count
shown is a claim — exact, or absent), extracts the item previews for the
"Informed HITL" card, and filters the pre-executed registry after an EDIT.

The orchestration itself (deciding WHEN to ask, persisting the context,
resuming after approval) stays in ``task_orchestrator_node`` — this module
only prepares what the confirmation shows and what execution resumes from.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.runnables import RunnableConfig

from src.domains.agents.data_registry.models import RegistryItemType, generate_registry_id
from src.domains.agents.orchestration.for_each_utils import parse_for_each_reference
from src.domains.agents.tools.runtime_helpers import extract_value_by_path
from src.infrastructure.observability.metrics_agents import (
    hitl_for_each_items_counted,
    hitl_for_each_pre_execution_duration,
    hitl_for_each_pre_execution_total,
)

if TYPE_CHECKING:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

logger = structlog.get_logger(__name__)


async def pre_execute_for_each_providers(
    execution_plan: ExecutionPlan,
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
        >>> completed_steps, item_counts = await pre_execute_for_each_providers(...)
        >>> # completed_steps = {"get_events": {"events": [...], "success": True}}
        >>> # item_counts = {"$steps.get_events.events": 2}
    """
    from src.core.constants import FOR_EACH_PRE_EXECUTION_METADATA_KEY
    from src.domains.agents.orchestration.for_each_utils import (
        count_items_at_path,
        get_for_each_provider_step_id,
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


def refresh_for_each_scope_claims(
    for_each_steps: list[dict[str, Any]],
    item_counts: dict[str, int],
) -> None:
    """Restate each step's scope claims with the MEASURED item count.

    The HITL decision is made BEFORE pre-execution, when only ``for_each_max``
    is known — so the reason baked into each step dict claimed the cap
    ("will execute 10 times" for a measured count of 1, prod 2026-08-17,
    request d4d2c6ed). Once the providers ran, the real counts exist; the
    executor already recomputes its scope with them at execution time, and the
    payload the user confirms must say the same thing (ADR-185: a count shown
    is a claim — exact, or absent).

    Deliberately touches CLAIMS only (reason, risk_level, is_mutation,
    ``item_count`` stamp): membership of the HITL list was settled before
    pre-execution and is never revisited here — a step whose measured count
    falls below every threshold still asks, it just stops overstating.

    Args:
        for_each_steps: The step dicts persisted in the HITL context (mutated
            in place).
        item_counts: Measured items per ``for_each`` source reference, from
            :func:`pre_execute_for_each_providers`.
    """
    from src.domains.agents.services.hitl.scope_detector import detect_for_each_scope

    for step in for_each_steps:
        measured = item_counts.get(str(step.get("for_each_source")))
        if not isinstance(measured, int) or measured <= 0:
            # No measurement (provider failed / other source) or the 0-item
            # skip path: nothing exact to claim, leave the step untouched.
            continue
        scope = detect_for_each_scope(
            iteration_count=measured,
            tool_name=str(step.get("tool_name") or ""),
            is_mutation=False,  # Auto-detected from tool_name
            for_each_max=int(step.get("for_each_max") or 0) or measured,
        )
        step["item_count"] = measured
        step["is_mutation"] = scope.is_mutation
        step["risk_level"] = scope.risk_level.value
        step["reason"] = scope.reason


def extract_item_previews_for_hitl(
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
    domain = detect_domain_from_items(pre_exec_registry, field_path)

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


def detect_domain_from_items(
    pre_exec_registry: dict[str, Any],
    field_path: str,
) -> str:
    """Detect canonical domain name from registry items or field path.

    Returns the singular domain name (e.g., "email", "event", "reminder")
    for use with FOR_EACH_PREVIEW_FIELDS. Registry meta.domain stores the
    result_key (plural, e.g., "emails", "reminders"), so we normalize it
    via get_domain_from_result_key().

    Args:
        pre_exec_registry: Registry with RegistryItem objects
        field_path: Field path like "emails", "events", "contacts"

    Returns:
        Canonical domain string (e.g., "email", "event", "contact")
    """
    from src.domains.agents.utils.type_domain_mapping import get_domain_from_result_key

    # Try to get domain from registry items (meta.domain is result_key, normalize)
    for item in pre_exec_registry.values():
        if hasattr(item, "meta") and hasattr(item.meta, "domain"):
            meta_domain = item.meta.domain
            # Normalize: meta.domain is result_key (plural) → canonical domain (singular)
            canonical = get_domain_from_result_key(meta_domain)
            if canonical:
                return canonical
            # If mapping doesn't know it, use as-is (unknown domain)
            return meta_domain

    # Fallback: use centralized mapping from field path (DRY)
    domain = get_domain_from_result_key(field_path)
    return domain or "unknown"


def filter_registry_by_items(
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
        is_items_key_for_each_filterable,
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

    # Composite-ID domains (routes/locations/weathers) cannot have their registry
    # ID regenerated from one payload field. Attempting it empties the registry
    # or raises — see FOR_EACH_UNFILTERABLE_ITEMS_KEYS. Keep the registry whole:
    # the response may then mention one item too many, whereas an empty registry
    # strips every card and an exception abandons the confirmed plan entirely.
    if not is_items_key_for_each_filterable(field_path):
        logger.warning(
            "filter_registry_composite_id_domain",
            run_id=run_id,
            field_path=field_path,
            registry_size=len(pre_exec_registry),
        )
        return pre_exec_registry

    registry_type_name, unique_key_field = config

    # Convert type name to RegistryItemType enum
    item_type = RegistryItemType(registry_type_name)

    # Extract unique keys from filtered items and generate expected registry IDs.
    # Only a string key can regenerate an ID; anything else is a mapping/payload
    # mismatch, and crashing here would abandon a plan the user already approved.
    expected_ids: set[str] = set()
    for item in filtered_items:
        unique_key = item.get(unique_key_field)
        if isinstance(unique_key, str) and unique_key:
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
