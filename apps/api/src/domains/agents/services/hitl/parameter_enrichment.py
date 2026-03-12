"""
HITL Parameter Enrichment - Resolve IDs to User-Friendly Labels.

This module provides generic enrichment logic to transform raw tool parameters
(like resource_name="people/c123") into user-friendly labels (like "jean dupond")
for HITL confirmation questions.

Architecture:
    - Generic: Works for all domains (contacts, emails, events)
    - Context-aware: Lookups names from LangGraph Store context
    - Fallback-safe: Returns original value if no match found
    - Type-safe: Preserves parameter types (string, array, object)

Example:
    >>> # Raw args from planner
    >>> tool_args = {"resource_name": "people/c8886916297043259303"}
    >>>
    >>> # After enrichment
    >>> enriched = await enrich_tool_parameters(
    ...     tool_name="get_contact_details_tool",
    ...     tool_args=tool_args,
    ...     user_id=user_id,
    ...     session_id=session_id,
    ...     store=store
    ... )
    >>> # enriched = {"resource_name": "people/c8886916297043259303", "_display_label": "jean dupond"}
"""

from typing import Any
from uuid import UUID

from langgraph.store.base import BaseStore

from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.context.registry import ContextTypeRegistry
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def enrich_tool_parameters(
    tool_name: str,
    tool_args: dict[str, Any],
    user_id: str | UUID,
    session_id: str,
    store: BaseStore,
) -> dict[str, Any]:
    """
    Enrich raw tool parameters with user-friendly labels for HITL questions.

    This function inspects tool_args for identifier fields (resource_name, email, etc.)
    and attempts to resolve them to human-readable labels by looking up context in
    the LangGraph Store.

    Args:
        tool_name: Name of the tool being called (e.g., "get_contact_details_tool").
        tool_args: Raw tool parameters from planner.
        user_id: User UUID for context lookup.
        session_id: Session UUID for context lookup.
        store: LangGraph BaseStore instance.

    Returns:
        Enriched tool_args with additional "_display_label" field if resolution succeeded.
        Original tool_args if no enrichment possible.

    Example - Single Contact:
        >>> # Input: {"resource_name": "people/c123"}
        >>> enriched = await enrich_tool_parameters(...)
        >>> # Output: {"resource_name": "people/c123", "_display_label": "jean dupond"}

    Example - Batch Contacts:
        >>> # Input: {"resource_names": ["people/c123", "people/c456"]}
        >>> enriched = await enrich_tool_parameters(...)
        >>> # Output: {"resource_names": [...], "_display_labels": ["jean dupond", "Marie Martin"]}

    Example - No Match:
        >>> # Input: {"resource_name": "people/c999"}  # Not in context
        >>> enriched = await enrich_tool_parameters(...)
        >>> # Output: {"resource_name": "people/c999"}  # Original args unchanged
    """
    # Step 1: Detect domain from tool_name
    # Convention: tool names like "get_contact_details_tool" → domain = "contacts"
    domain = _extract_domain_from_tool_name(tool_name)

    logger.info(
        "enrichment_started",
        tool_name=tool_name,
        tool_args_keys=list(tool_args.keys()),
        detected_domain=domain,
        session_id=session_id,
    )

    if not domain:
        logger.debug(
            "enrichment_skipped_unknown_domain",
            tool_name=tool_name,
        )
        return tool_args  # Can't enrich without domain

    # Step 2: Get context type definition for this domain
    try:
        context_def = ContextTypeRegistry.get_definition(domain)
    except ValueError:
        # Domain not registered in ContextTypeRegistry
        logger.debug(
            "enrichment_skipped_no_context_definition",
            domain=domain,
        )
        return tool_args  # No context definition registered

    # Step 3: Detect identifier parameter(s) in tool_args
    # Look for: resource_name, resource_names, email, event_id, etc.
    primary_id_field = context_def.primary_id_field  # e.g., "resource_name"
    display_field = context_def.display_name_field  # e.g., "name"

    # Check for single ID parameter (e.g., resource_name)
    if primary_id_field in tool_args:
        # Single mode: resolve one ID
        id_value = tool_args[primary_id_field]
        display_label = await _resolve_id_to_label(
            id_value=id_value,
            primary_id_field=primary_id_field,
            display_field=display_field,
            user_id=user_id,
            session_id=session_id,
            domain=domain,
            store=store,
        )

        if display_label:
            # Add enriched label to tool_args (non-intrusive: original args preserved)
            enriched_args = tool_args.copy()
            enriched_args["_display_label"] = display_label
            logger.info(
                "enrichment_single_success",
                tool_name=tool_name,
                domain=domain,
                id_field=primary_id_field,
                id_value=str(id_value)[:50],  # Truncate for logging
                display_label=display_label,
            )
            return enriched_args

    # Check for batch ID parameter (e.g., resource_names)
    batch_id_field = f"{primary_id_field}s"  # resource_name → resource_names
    if batch_id_field in tool_args:
        # Batch mode: resolve multiple IDs
        id_values = tool_args[batch_id_field]
        if isinstance(id_values, list):
            display_labels = []
            for id_value in id_values:
                label = await _resolve_id_to_label(
                    id_value=id_value,
                    primary_id_field=primary_id_field,
                    display_field=display_field,
                    user_id=user_id,
                    session_id=session_id,
                    domain=domain,
                    store=store,
                )
                display_labels.append(label or str(id_value))  # Fallback to ID if no label

            # Add enriched labels to tool_args
            enriched_args = tool_args.copy()
            enriched_args["_display_labels"] = display_labels

            # Count how many IDs were successfully resolved (label != original ID)
            resolved_count = sum(
                1 for i, label in enumerate(display_labels) if label != str(id_values[i])
            )

            logger.info(
                "enrichment_batch_success",
                tool_name=tool_name,
                domain=domain,
                id_field=batch_id_field,
                count=len(id_values),
                resolved_count=resolved_count,
            )
            return enriched_args

    # Step 4: No identifier parameter found - return original args
    logger.debug(
        "enrichment_skipped_no_identifier_param",
        tool_name=tool_name,
        domain=domain,
        expected_fields=[primary_id_field, batch_id_field],
    )
    return tool_args


async def _resolve_id_to_label(
    id_value: Any,
    primary_id_field: str,
    display_field: str,
    user_id: str | UUID,
    session_id: str,
    domain: str,
    store: BaseStore,
) -> str | None:
    """
    Resolve a single ID to its user-friendly display label.

    Looks up the ID in both "list" and "details" context keys and returns
    the display_name_field value if found.

    Args:
        id_value: ID to resolve (e.g., "people/c123") or full object dict.
        primary_id_field: Field name for ID matching (e.g., "resource_name").
        display_field: Field name for display label (e.g., "name").
        user_id: User UUID for context lookup.
        session_id: Session UUID for context lookup.
        domain: Domain identifier (e.g., "contacts").
        store: LangGraph BaseStore instance.

    Returns:
        Display label if found (e.g., "jean dupond"), None otherwise.
    """
    # FIX: Handle case where id_value is already a full object dict
    # (happens when get_context_list returns full contact objects)
    if isinstance(id_value, dict):
        # If object already has display field, return it directly
        if display_field in id_value:
            return id_value.get(display_field)
        # Otherwise extract the ID field for lookup
        id_value = id_value.get(primary_id_field)
        if not id_value:
            return None

    manager = ToolContextManager()

    logger.info(
        "enrichment_resolving_id",
        id_value=str(id_value)[:50],
        domain=domain,
        primary_id_field=primary_id_field,
        display_field=display_field,
        session_id=session_id,
    )

    # Step 1: Try "list" context (most common case - search results)
    context_list = await manager.get_list(
        user_id=user_id,
        session_id=session_id,
        domain=domain,
        store=store,
    )

    logger.info(
        "enrichment_list_context_retrieved",
        domain=domain,
        has_list=bool(context_list),
        items_count=len(context_list.items) if context_list and context_list.items else 0,
        session_id=session_id,
    )

    if context_list and context_list.items:
        for item in context_list.items:
            if item.get(primary_id_field) == id_value:
                display_label = item.get(display_field)
                if display_label:
                    logger.debug(
                        "enrichment_resolved_from_list",
                        id_value=str(id_value)[:50],
                        display_label=display_label,
                        domain=domain,
                    )
                    return display_label

    # Step 2: Try "details" context (fallback - previously fetched details)
    context_details = await manager.get_details(
        user_id=user_id,
        session_id=session_id,
        domain=domain,
        store=store,
    )

    if context_details and context_details.items:
        for item in context_details.items:
            if item.get(primary_id_field) == id_value:
                display_label = item.get(display_field)
                if display_label:
                    logger.debug(
                        "enrichment_resolved_from_details",
                        id_value=str(id_value)[:50],
                        display_label=display_label,
                        domain=domain,
                    )
                    return display_label

    # Step 3: No match found - return None (caller will use original ID)
    logger.debug(
        "enrichment_no_match",
        id_value=str(id_value)[:50],
        domain=domain,
    )
    return None


def _extract_domain_from_tool_name(tool_name: str) -> str | None:
    """
    Extract domain identifier from tool name using naming convention.

    Convention:
        - "search_contacts_tool" → "contacts"
        - "get_contact_details_tool" → "contacts"
        - "send_email_tool" → "emails"
        - "create_event_tool" → "events"

    Args:
        tool_name: Name of the tool.

    Returns:
        Domain identifier if detected, None otherwise.

    Example:
        >>> _extract_domain_from_tool_name("get_contact_details_tool")
        "contacts"
        >>> _extract_domain_from_tool_name("search_contacts_tool")
        "contacts"
        >>> _extract_domain_from_tool_name("unknown_tool")
        None
    """
    # Use centralized mapping from type_domain_mapping.py for consistency
    from src.domains.agents.utils.type_domain_mapping import get_domain_from_tool_name

    return get_domain_from_tool_name(tool_name)
