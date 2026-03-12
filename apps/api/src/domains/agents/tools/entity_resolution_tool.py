"""
Entity Resolution Tool - Automatic entity resolution with HITL disambiguation.

This tool resolves entity references (names, identifiers) to specific data values
needed for actions (email addresses, phone numbers, etc.).

Use Cases:
    1. "envoie un email à Jean" → resolve_entity("Jean", "send_email") → email address
    2. "appelle Marie" → resolve_entity("Marie", "call") → phone number
    3. Multiple matches → triggers HITL for user disambiguation

Architecture:
    Planner creates resolve_entity step → Tool executes search
    → EntityResolutionService analyzes results:
        - 1 result with unique field → returns value directly
        - Ambiguity → returns UnifiedToolOutput with metadata.requires_confirmation=True
        → HITL triggered for disambiguation

Integration:
    - Uses EntityResolutionService for resolution logic
    - Uses UnifiedToolOutput for consistent output format
    - HITL fields preserved in metadata for future implementation
    - Compatible with Data Registry LOT 4 patterns

Migration (2025-12-30):
    Migrated from StandardToolOutput to UnifiedToolOutput.
    - `data=` → `structured_data=`
    - `requires_confirmation`, `draft_*` fields → preserved in `metadata`
    - Return type unified to UnifiedToolOutput (removed `| str`)

Created: 2025-12-07
Updated: 2025-12-30
"""

from typing import Annotated, Any

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.core.i18n_api_messages import APIMessages
from src.domains.agents.context.entity_resolution import (
    ResolutionStatus,
    get_entity_resolution_service,
)
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@tool
async def resolve_entity_for_action(
    query: str,
    action: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    domain: str = "contacts",
    target_field: str | None = None,
) -> UnifiedToolOutput:
    """
    Resolve an entity reference (name, identifier) to a specific value for an action.

    This tool searches for entities matching the query and extracts the appropriate
    field value based on the intended action. It handles disambiguation automatically:
    - Single match with single value: Returns the value directly
    - Multiple matches or multiple values: Triggers HITL for user choice

    Args:
        query: Entity reference to resolve (e.g., "Jean Dupont", "Marie")
        action: Intended action type (send_email, call, create_event, etc.)
        runtime: Injected tool runtime for context access
        domain: Entity domain to search (contacts, emails, events). Default: contacts
        target_field: Optional override for the field to extract

    Returns:
        UnifiedToolOutput with:
        - structured_data.resolved_value: The extracted value (email, phone, etc.)
        - metadata.requires_confirmation: True if disambiguation needed
        - registry_updates: Candidate items for HITL display

    Examples:
        >>> # Single match with single email
        >>> result = await resolve_entity_for_action("Jean Dupont", "send_email", runtime)
        >>> # Returns: {"resolved_value": "jean@example.com", "entity_name": "Jean Dupont"}

        >>> # Multiple matches - triggers HITL
        >>> result = await resolve_entity_for_action("Jean", "send_email", runtime)
        >>> # Returns: StandardToolOutput with requires_confirmation=True and candidates

    Tool Manifest:
        name: resolve_entity_for_action
        agent: context_agent
        category: resolution
        requires_confirmation: conditional (based on ambiguity)
    """
    user_id = runtime.config.get("metadata", {}).get("user_id", "")

    logger.info(
        "resolve_entity_started",
        query=query,
        action=action,
        domain=domain,
        user_id=user_id,
    )

    # Step 1: Search for entities
    items = await _search_entities(query, domain, runtime)

    if not items:
        logger.info(
            "resolve_entity_not_found",
            query=query,
            domain=domain,
        )
        return _create_not_found_output(query, domain)

    # Step 2: Resolve using EntityResolutionService
    service = get_entity_resolution_service()
    result = service.resolve_for_action(
        items=items,
        domain=domain,
        original_query=query,
        intended_action=action,
        target_field_override=target_field,
    )

    # Step 3: Handle resolution result
    if result.status == ResolutionStatus.RESOLVED:
        logger.info(
            "resolve_entity_success",
            query=query,
            resolved_value=result.resolved_value,
            confidence=result.confidence,
        )
        return _create_success_output(
            resolved_value=result.resolved_value,
            resolved_item=result.resolved_item,
            query=query,
            domain=domain,
        )

    elif result.status == ResolutionStatus.DISAMBIGUATION_NEEDED:
        logger.info(
            "resolve_entity_disambiguation_needed",
            query=query,
            domain=domain,
            context=result.disambiguation_context,
        )
        return _create_disambiguation_output(
            disambiguation_context=result.disambiguation_context,
            items=items,
            domain=domain,
        )

    elif result.status == ResolutionStatus.NO_TARGET_FIELD:
        logger.warning(
            "resolve_entity_no_target_field",
            query=query,
            domain=domain,
            error=result.error_message,
        )
        return _create_no_field_output(
            query=query,
            domain=domain,
            item=result.resolved_item,
            error_message=result.error_message,
        )

    else:
        # Error or unexpected status
        logger.error(
            "resolve_entity_error",
            query=query,
            domain=domain,
            status=result.status,
            error=result.error_message,
        )
        return UnifiedToolOutput.failure(
            message=APIMessages.resolution_error(result.error_message or ""),
            error_code="resolution_error",
            metadata={"query": query, "domain": domain, "status": str(result.status)},
        )


async def _search_entities(
    query: str,
    domain: str,
    runtime: ToolRuntime,
) -> list[dict[str, Any]]:
    """
    Search for entities matching the query.

    Uses the appropriate search tool based on domain.

    Args:
        query: Search query
        domain: Entity domain
        runtime: Tool runtime for context

    Returns:
        List of matching items
    """
    # Import here to avoid circular imports
    from src.domains.agents.orchestration.parallel_executor import ToolRegistry

    tool_registry = ToolRegistry.get_instance()

    # Map domain to search tool
    search_tools = {
        "contacts": "search_contacts_tool",
        "emails": "search_emails_tool",
        "events": "search_events_tool",
        "tasks": "search_tasks_tool",
        "files": "search_files_tool",
    }

    tool_name = search_tools.get(domain)
    if not tool_name or not tool_registry.has_tool(tool_name):
        logger.warning(
            "resolve_entity_no_search_tool",
            domain=domain,
            tool_name=tool_name,
        )
        return []

    try:
        tool = tool_registry.get_tool(tool_name)

        # Build search args
        search_args = {"query": query}
        if domain == "contacts":
            search_args["fields"] = "names,emailAddresses,phoneNumbers"
            search_args["limit"] = 10

        # Execute search
        result = await tool.ainvoke(search_args, config=runtime.config)

        # Parse result
        if isinstance(result, UnifiedToolOutput):
            # Extract items from registry_updates
            items = []
            for _item_id, item in result.registry_updates.items():
                if isinstance(item, dict):
                    payload = item.get("payload", item)
                    items.append(payload)
            return items
        elif isinstance(result, str):
            # Legacy string output - try to parse
            import json

            try:
                data = json.loads(result)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    # Extract items from known keys
                    for key in ("contacts", "emails", "events", "items", "results"):
                        if key in data:
                            return data[key]
            except json.JSONDecodeError:
                pass

        return []

    except Exception as e:
        logger.error(
            "resolve_entity_search_error",
            domain=domain,
            error=str(e),
        )
        return []


def _create_success_output(
    resolved_value: str | None,
    resolved_item: dict[str, Any] | None,
    query: str,
    domain: str,
) -> UnifiedToolOutput:
    """Create success output with resolved value."""
    # Build registry item for the resolved entity
    registry_updates = {}
    if resolved_item:
        item_id = (
            resolved_item.get("resource_name") or resolved_item.get("id") or f"resolved_{query}"
        )
        registry_updates[item_id] = RegistryItem(
            id=item_id,
            type=_domain_to_registry_type(domain),
            payload=resolved_item,
            display_label=resolved_item.get("name", query),
        )

    return UnifiedToolOutput.data_success(
        message=f"Résolu: {resolved_value}",
        registry_updates=registry_updates,
        structured_data={
            "resolved_value": resolved_value,
            "entity_name": resolved_item.get("name", query) if resolved_item else query,
            "domain": domain,
            "status": "resolved",
        },
        metadata={"requires_confirmation": False},
    )


def _create_not_found_output(query: str, domain: str) -> UnifiedToolOutput:
    """Create output for no matches found."""
    return UnifiedToolOutput.failure(
        message=APIMessages.entity_not_found(domain, query),
        error_code="not_found",
        metadata={
            "query": query,
            "domain": domain,
            "requires_confirmation": False,
        },
    )


def _create_no_field_output(
    query: str,
    domain: str,
    item: dict[str, Any] | None,
    error_message: str | None,
) -> UnifiedToolOutput:
    """Create output when entity found but target field missing."""
    registry_updates = {}
    if item:
        item_id = item.get("resource_name") or item.get("id") or f"found_{query}"
        registry_updates[item_id] = RegistryItem(
            id=item_id,
            type=_domain_to_registry_type(domain),
            payload=item,
            display_label=item.get("name", query),
        )

    return UnifiedToolOutput.failure(
        message=error_message or APIMessages.entity_no_target_field(domain, query),
        error_code="no_target_field",
        metadata={
            "query": query,
            "domain": domain,
            "entity_found": True,
            "error": error_message,
            "requires_confirmation": False,
            "registry_updates": registry_updates,  # Preserve for potential HITL display
        },
    )


def _create_disambiguation_output(
    disambiguation_context: dict[str, Any] | None,
    items: list[dict[str, Any]],
    domain: str,
) -> UnifiedToolOutput:
    """
    Create output for disambiguation scenario.

    Sets requires_confirmation=True in metadata to trigger HITL flow.

    NOTE (2025-12-30): The HITL fields (requires_confirmation, draft_*) are
    preserved in metadata. A proper HITL implementation should check these
    fields and trigger user disambiguation flow.
    """
    if not disambiguation_context:
        disambiguation_context = {}

    candidates = disambiguation_context.get("candidates", [])
    disambiguation_type = disambiguation_context.get("disambiguation_type", "multiple_entities")

    # Build registry items for all candidates
    registry_updates = {}
    for i, item in enumerate(items[:10]):  # Limit to 10 items
        item_id = item.get("resource_name") or item.get("id") or f"candidate_{i}"
        registry_updates[item_id] = RegistryItem(
            id=item_id,
            type=_domain_to_registry_type(domain),
            payload=item,
            display_label=item.get("name", f"Item {i + 1}"),
        )

    # Build summary for LLM
    if disambiguation_type == "multiple_fields":
        summary = APIMessages.multiple_options_available(len(candidates))
    else:
        summary = APIMessages.multiple_matches_found(len(candidates))

    return UnifiedToolOutput.data_success(
        message=summary,
        registry_updates=registry_updates,
        structured_data={
            "status": "disambiguation_needed",
            "disambiguation_type": disambiguation_type,
            "candidates_count": len(candidates),
            **disambiguation_context,
        },
        metadata={
            # HITL fields - preserved for future HITL implementation
            "requires_confirmation": True,
            "draft_id": f"disambiguation_{domain}",
            "draft_type": "entity_disambiguation",
            "draft_content": disambiguation_context,
            "draft_summary": summary,
        },
    )


def _domain_to_registry_type(domain: str) -> RegistryItemType:
    """Map domain (items_key) to registry item type using centralized config."""
    from src.domains.agents.utils.type_domain_mapping import get_registry_config_for_items_key

    config = get_registry_config_for_items_key(domain)
    if config:
        registry_type_name, _ = config
        return RegistryItemType(registry_type_name)
    return RegistryItemType.UNKNOWN
