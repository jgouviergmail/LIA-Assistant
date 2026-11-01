"""The context list's fallbacks: a past turn's results, then the registry.

Moved from ``context_resolution_service.py`` (file-size ratchet, 2026-10-31),
behaviour unchanged: when neither what the last answers SHOWED nor the context list
holds the items an ordinal names, the turn that last listed them is read back
from its agent results, then from the registry — filtered to that turn and its
domain, never the whole registry (cross-domain contamination, 2025-12-19).

Pure functions over the graph state; no I/O.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.core.field_names import FIELD_DISPLAY_ONLY, FIELD_REGISTRY_ID
from src.domains.agents.data_registry.card_payload import display_fields
from src.domains.agents.data_registry.mcp_metadata import authoritative_mcp_source
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.utils.type_domain_mapping import (
    get_domain_from_tool_name,
    get_result_key_from_type,
)

if TYPE_CHECKING:
    from src.domains.agents.models import MessagesState

logger = structlog.get_logger(__name__)

__all__ = [
    "DATA_KEY_TO_RESULT_KEY",
    "derive_domain_from_type",
    "detect_domain_from_agent_results",
    "extract_all_items",
    "extract_items_from_registry",
    "resolved_payload",
    "results_for_turn",
]


# Payload data-key -> canonical result_key of the domain that produced it.
# Used to detect the domain of a past turn from its result structure when no
# explicit meta.domain is present. Values MUST be canonical result_keys
# (plural): the detected value is compared against item.meta.domain /
# derive_domain_from_type (both result_keys) in STRATEGY 3, so a singular or
# legacy token (e.g. "drive", "weather") never matches and domain-based
# reference resolution silently degrades. Guarded by the domain-vocabulary
# parity test.
DATA_KEY_TO_RESULT_KEY: dict[str, str] = {
    "emails": "emails",
    "contacts": "contacts",
    "events": "events",
    "files": "files",
    "tasks": "tasks",
    "places": "places",
    "weather": "weathers",
    "forecasts": "weathers",
    "articles": "wikipedias",
    "results": "perplexitys",
}


def resolved_payload(item_id: str, payload: dict[str, Any], item: object) -> dict[str, Any]:
    """A registry payload as a resolved reference carries it.

    It keeps its registry id, and the display-only fields the card of a later
    turn draws, under ``FIELD_DISPLAY_ONLY`` — the model readers of a resolved
    item skip ``_`` keys (``payload_to_text``, ``ResolvedContext.to_llm_context``;
    ADR-287 amendment).

    Args:
        item_id: The registry id.
        payload: The item's payload (never mutated).
        item: The registry item (object or JSON dump), for its display fields.

    Returns:
        A new dict.
    """
    resolved = {**payload, FIELD_REGISTRY_ID: item_id}
    display = display_fields(item)
    if source := authoritative_mcp_source(item, display):
        display = {**display, "_mcp_source": source}
    if display:
        resolved[FIELD_DISPLAY_ONLY] = display
    return resolved


def results_for_turn(
    agent_results: dict[str, Any],
    turn_id: int,
) -> dict[str, Any]:
    """
    Filter agent results for a specific turn.

    Args:
        agent_results: All agent results (keyed by "turn_id:agent_name").
        turn_id: Turn ID to filter by.

    Returns:
        Dict of agent_name → result for the specified turn.
    """
    results: dict[str, Any] = {}
    prefix = f"{turn_id}:"

    for key, value in agent_results.items():
        if key.startswith(prefix):
            agent_name = key[len(prefix) :]
            results[agent_name] = value

    return results


def extract_all_items(agent_results: dict[str, Any]) -> list[Any]:
    """
    Extract all list items from agent results.

    Looks for common list fields in results (emails, contacts, events, etc.)
    and aggregates them into a single list.

    BugFix 2025-12-19: Also extract from registry_updates for registry-mode tools.

    Args:
        agent_results: Dict of agent_name → result.

    Returns:
        Flattened list of all items from all agents.
    """
    all_items: list[Any] = []

    # Common list field names across domains
    # NOTE: Order matters - more specific fields first, generic fields last
    list_fields = [
        "emails",
        "contacts",
        "events",
        "files",
        "tasks",
        "places",  # Google Places search/nearby results
        "items",
        "results",
        "list",
    ]

    for _agent_name, result in agent_results.items():
        if isinstance(result, dict):
            # BugFix 2025-12-19: Check registry_updates FIRST for registry-mode tools
            # Registry-mode tools store data in registry_updates, not in traditional fields
            registry_updates = result.get("registry_updates", {})
            if registry_updates and isinstance(registry_updates, dict):
                for _item_id, reg_item in registry_updates.items():
                    if isinstance(reg_item, RegistryItem):
                        # Enrich with metadata for domain detection
                        payload = resolved_payload(_item_id, reg_item.payload, reg_item)
                        payload["_item_type"] = reg_item.type.value
                        all_items.append(payload)
                    elif isinstance(reg_item, dict):
                        raw_payload = reg_item.get("payload", reg_item)
                        if isinstance(raw_payload, dict):
                            # Enrich with metadata for domain detection
                            payload = resolved_payload(_item_id, raw_payload, reg_item)
                            # Try to get type from dict if available
                            if "type" in reg_item:
                                payload["_item_type"] = reg_item["type"]
                            all_items.append(payload)
                if all_items:
                    logger.info(
                        "extract_all_items_from_registry_updates",
                        agent_name=_agent_name,
                        items_added=len(registry_updates),
                    )
                    continue  # Skip traditional field extraction

            # Check if result has "data" field (standard agent result structure)
            # Structure: {"agent_name": ..., "status": ..., "data": {"emails": [...]}}
            data_container = result.get("data", result)
            if isinstance(data_container, dict):
                # Look for list fields in data container
                found_field = None
                for field in list_fields:
                    if field in data_container and isinstance(data_container[field], list):
                        all_items.extend(data_container[field])
                        found_field = field
                        break
                if found_field:
                    logger.debug(
                        "extract_all_items_found_field",
                        agent_name=_agent_name,
                        field=found_field,
                        items_added=len(data_container[found_field]),
                    )
                else:
                    # No known list field found - check for any list value
                    if result.get("status") == "success":
                        for key, value in data_container.items():
                            if isinstance(value, list) and key not in [
                                "errors",
                                "warnings",
                            ]:
                                all_items.extend(value)
                                logger.debug(
                                    "extract_all_items_fallback_list",
                                    agent_name=_agent_name,
                                    key=key,
                                    items_added=len(value),
                                )
                                break
                    else:
                        logger.debug(
                            "extract_all_items_no_match",
                            agent_name=_agent_name,
                            data_keys=list(data_container.keys())[:5],
                            result_status=result.get("status"),
                        )
        elif isinstance(result, list):
            all_items.extend(result)
            logger.debug(
                "extract_all_items_raw_list",
                agent_name=_agent_name,
                items_added=len(result),
            )

    if not all_items:
        logger.debug(
            "extract_all_items_empty",
            agent_count=len(agent_results),
            agent_names=list(agent_results.keys()),
        )

    # Sort items by index field to preserve original order for ordinal resolution
    # (e.g., "the second one" should get the item with index=2)
    # Items without index field are placed at the end
    all_items.sort(key=lambda x: x.get("index", float("inf")))

    return all_items


def extract_items_from_registry(
    state: MessagesState,
    run_id: str,
    last_action_turn: int | None = None,
    agent_results: dict[str, Any] | None = None,
) -> list[Any]:
    """
    Extract items from data_registry for reference resolution.

    CRITICAL FIX 2025-12-19: Multi-level filtering strategy to prevent cross-domain
    contamination (e.g., returning contacts when user asked for "the second e-mail").

    Filtering Priority (stops at first successful filter):
    1. registry_updates from agent_results for last_action_turn
    2. turn_id in RegistryItem.meta (if populated)
    3. Domain-based filtering using detected domain from last action
    4. SAFE FALLBACK: Return empty list (never return ALL items)

    Args:
        state: Current conversation state with registry.
        run_id: Current run ID for logging.
        last_action_turn: Turn ID to filter items by.
        agent_results: Agent results to extract registry_updates from.

    Returns:
        List of item payloads from the registry, filtered to prevent cross-domain issues.
    """
    registry = state.get("registry", {})
    if not registry:
        logger.debug("no_registry_in_state", run_id=run_id)
        return []

    # =========================================================================
    # STRATEGY 1: Filter by registry_updates from agent_results
    # =========================================================================
    target_item_ids: set[str] | None = None
    filter_method = "none"

    if last_action_turn is not None and agent_results:
        target_item_ids = set()
        prefix = f"{last_action_turn}:"
        for key, result in agent_results.items():
            if key.startswith(prefix):
                updates = {}
                if isinstance(result, dict):
                    updates = result.get("registry_updates", {})
                elif hasattr(result, "registry_updates"):
                    updates = getattr(result, "registry_updates", {})
                if updates:
                    target_item_ids.update(updates.keys())

        if target_item_ids:
            filter_method = "registry_updates"
            logger.info(
                "registry_extraction_filtered_by_registry_updates",
                run_id=run_id,
                turn_id=last_action_turn,
                total_registry_count=len(registry),
                filtered_count=len(target_item_ids),
                filtered_ids=list(target_item_ids)[:10],
            )
        else:
            target_item_ids = None

    # =========================================================================
    # STRATEGY 2: Filter by turn_id in RegistryItem.meta
    # =========================================================================
    if target_item_ids is None and last_action_turn is not None:
        target_item_ids = set()
        for item_id, item in registry.items():
            if isinstance(item, RegistryItem):
                if item.meta.turn_id == last_action_turn:
                    target_item_ids.add(item_id)

        if target_item_ids:
            filter_method = "turn_id_meta"
            logger.info(
                "registry_extraction_filtered_by_turn_id_meta",
                run_id=run_id,
                turn_id=last_action_turn,
                filtered_count=len(target_item_ids),
            )
        else:
            target_item_ids = None

    # =========================================================================
    # STRATEGY 3: Filter by domain from last action turn
    # =========================================================================
    if target_item_ids is None and last_action_turn is not None and agent_results:
        # Detect domain from agent_results for last action turn
        detected_domain = detect_domain_from_agent_results(agent_results, last_action_turn, run_id)

        if detected_domain:
            target_item_ids = set()
            for item_id, item in registry.items():
                if isinstance(item, RegistryItem):
                    # Match by meta.domain or by item type prefix
                    item_domain = item.meta.domain
                    if item_domain is None:
                        # Fallback: derive domain from item type
                        item_domain = derive_domain_from_type(item.type.value)

                    if item_domain == detected_domain:
                        target_item_ids.add(item_id)

            if target_item_ids:
                filter_method = "domain"
                logger.info(
                    "registry_extraction_filtered_by_domain",
                    run_id=run_id,
                    detected_domain=detected_domain,
                    turn_id=last_action_turn,
                    filtered_count=len(target_item_ids),
                )
            else:
                target_item_ids = None

    # =========================================================================
    # STRATEGY 4: SAFE FALLBACK - Return empty rather than ALL items
    # =========================================================================
    if target_item_ids is None:
        logger.warning(
            "registry_extraction_no_valid_filter",
            run_id=run_id,
            turn_id=last_action_turn,
            total_registry_count=len(registry),
            reason="All filtering strategies failed - returning empty to prevent cross-domain contamination",
        )
        return []

    # =========================================================================
    # Extract payloads from filtered RegistryItems
    # =========================================================================
    items: list[Any] = []
    for item_id, item in registry.items():
        if item_id not in target_item_ids:
            continue

        if isinstance(item, RegistryItem):
            payload = resolved_payload(item_id, item.payload, item)
            payload["_item_type"] = item.type.value
            items.append(payload)
        elif isinstance(item, dict):
            payload = item.get("payload", item)
            if isinstance(payload, dict):
                payload = resolved_payload(item_id, payload, item)
            items.append(payload)
        else:
            logger.warning(
                "registry_item_unexpected_type",
                run_id=run_id,
                item_id=item_id,
                item_type=type(item).__name__,
            )

    if items:
        # Sort items by index field to preserve original order for ordinal resolution
        # (e.g., "the second one" should get the item with index=2)
        # Items without index field are placed at the end
        items.sort(key=lambda x: x.get("index", float("inf")))

        logger.info(
            "items_extracted_from_registry",
            run_id=run_id,
            items_count=len(items),
            filter_method=filter_method,
            turn_id=last_action_turn,
            item_types=[i.get("_item_type", "unknown") for i in items[:5]],
        )

    return items


def detect_domain_from_agent_results(
    agent_results: dict[str, Any],
    turn_id: int,
    run_id: str,
) -> str | None:
    """
    Detect domain from agent_results for a specific turn.

    Looks at the result structure to determine which domain the last action was for.
    This is used as a fallback when registry_updates is not available.

    Args:
        agent_results: All agent results.
        turn_id: Turn ID to look for.
        run_id: Run ID for logging.

    Returns:
        Domain name (e.g., "emails", "contacts") or None if not detected.
    """
    prefix = f"{turn_id}:"
    for key, result in agent_results.items():
        if not key.startswith(prefix):
            continue

        if not isinstance(result, dict):
            continue

        # Check for domain indicators in result structure
        # Priority: explicit 'domain' field > data keys > tool_name
        if "domain" in result:
            return str(result["domain"])

        # Check data keys
        data = result.get("data", result)
        if isinstance(data, dict):
            for key_name, domain in DATA_KEY_TO_RESULT_KEY.items():
                if key_name in data:
                    logger.debug(
                        "domain_detected_from_data_keys",
                        run_id=run_id,
                        turn_id=turn_id,
                        detected_key=key_name,
                        domain=domain,
                    )
                    return domain

        # Check tool_name - use centralized mapping from type_domain_mapping.py
        tool_name = result.get("tool_name", "")
        if tool_name:
            tool_domain = get_domain_from_tool_name(tool_name)
            if tool_domain:
                logger.debug(
                    "domain_detected_from_tool_name",
                    run_id=run_id,
                    turn_id=turn_id,
                    tool_name=tool_name,
                    domain=tool_domain,
                )
                return tool_domain

    return None


def derive_domain_from_type(item_type: str) -> str | None:
    """
    Derive result key (pluriel) from RegistryItemType value.

    Uses centralized TYPE_TO_DOMAIN_MAP from type_domain_mapping.py.
    Returns the pluriel form to match meta.domain convention.

    Args:
        item_type: Item type string (e.g., "EMAIL", "CONTACT").

    Returns:
        Result key (e.g., "emails", "contacts") or None.
    """
    return get_result_key_from_type(item_type)
