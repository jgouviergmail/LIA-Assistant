"""
Registry filtering utilities for response node.

This module provides functions for filtering the data registry to include
only items relevant to the current turn. Extracted from response_node.py
to improve maintainability.

Usage:
    from src.domains.agents.utils.registry_filtering import (
        filter_registry_by_current_turn,
        filter_registry_by_relevant_ids,
        build_registry_payload_index,
    )
"""

from typing import Any

from src.domains.agents.constants import TURN_TYPE_REFERENCE
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def build_registry_payload_index(data_registry: dict[str, Any]) -> dict[str, str]:
    """
    Build an index from payload identifiers to registry keys for O(1) lookup.

    This is a generic helper that works with ANY domain (contacts, emails, places, etc.)
    by mapping common identifier fields to their registry keys.

    BugFix 2026-01-04: Extended to include alias fields (file_id, resource_name, etc.)
    that may be returned by the LLM during intelligent filtering. The LLM sometimes
    extracts raw API IDs from various sources, so we need comprehensive indexing.

    Args:
        data_registry: Full merged registry with all items

    Returns:
        Dictionary mapping identifier values to registry keys.
        Supports: id, resourceName, resource_name, place_id, file_id, etc.

    Complexity: O(N) for build, enables O(1) lookup vs O(N*M) nested loops
    """
    index: dict[str, str] = {}

    # All identifier fields to index (covers all domains and their aliases)
    # BugFix 2026-01-04: Added file_id, resource_name, and other aliases
    id_fields = (
        # Primary identifiers
        "id",
        # Contacts: Google People API (both CamelCase and underscore)
        "resourceName",
        "resource_name",
        # Places: Google Places API
        "place_id",
        "placeId",
        # Drive: Google Drive API (alias added in build_files_output)
        "file_id",
        "fileId",
        # Emails: Gmail API
        "threadId",
        "thread_id",
        "messageId",
        "message_id",
        # Calendar: Google Calendar API
        "eventId",
        "event_id",
    )

    for reg_key, reg_item in data_registry.items():
        # Extract payload - handle both Pydantic RegistryItem and dict
        payload: dict[str, Any] | None = None
        if hasattr(reg_item, "payload"):
            payload = reg_item.payload if isinstance(reg_item.payload, dict) else None
        elif isinstance(reg_item, dict):
            payload = reg_item.get("payload", reg_item)

        if not payload or not isinstance(payload, dict):
            continue

        # Index by all identifier fields (generic for any domain)
        for id_field in id_fields:
            id_value = payload.get(id_field)
            if id_value and isinstance(id_value, str):
                index[id_value] = reg_key

    return index


def filter_registry_by_current_turn(
    agent_results: dict[str, Any],
    current_turn_id: int | None,
    data_registry: dict[str, Any],
    resolved_context: dict[str, Any] | None = None,
    turn_type: str | None = None,
) -> dict[str, Any]:
    """
    Filter registry to include only items from the current turn.

    This function extracts registry_updates from agent_results for the current turn
    and filters the full (merged) registry to include only those items.

    **Why this is needed:**
    The state["registry"] is merged across all turns (merge_registry reducer).
    For display purposes (LLM response, photo injection, SSE updates), we need
    only the items from the current turn to avoid showing stale data.

    **Security (2025-12-19):**
    - REFERENCE turns return empty dict if no match (prevents data leak)
    - IDs are NOT logged to comply with GDPR (only counts are logged)
    - O(1) indexed lookup instead of O(N*M) nested loops for performance

    Args:
        agent_results: Dictionary of composite_key → AgentResult
                      Keys are formatted as "{turn_id}:{agent_name}"
        current_turn_id: Current turn ID (e.g., 3)
        data_registry: Full merged registry with all items from all turns
        resolved_context: Optional resolved context for REFERENCE turns.
                         Used as fallback when no registry_updates exist.
        turn_type: Turn type (ACTION, REFERENCE, CONVERSATIONAL).
                  Used for strict filtering on REFERENCE turns.

    Returns:
        Filtered registry containing only items from the current turn.
        Returns original registry for ACTION/CONVERSATIONAL if no filtering possible.
        Returns empty dict for REFERENCE if no match (security: prevents data leak).

    Example:
        Turn 1: search → 2 restaurants (place_a, place_b)
        Turn 2: details of first → place_a (enriched)
        Turn 3: details of second → place_b (enriched)

        For turn 3:
        - agent_results["3:plan_executor"]["registry_updates"] = {"place_b": ...}
        - data_registry = {"place_a": ..., "place_b": ...}  (merged)
        - Returns: {"place_b": ...}  (only turn 3 items)
    """
    if current_turn_id is None or not data_registry:
        return data_registry

    current_turn_item_ids: set[str] = set()

    # Find registry_updates for current turn
    prefix = f"{current_turn_id}:"
    for key, result in agent_results.items():
        if key.startswith(prefix):
            # Extract registry updates from result (handle dict or object)
            updates = {}
            if isinstance(result, dict):
                updates = result.get("registry_updates", {})
            elif hasattr(result, "registry_updates"):
                updates = getattr(result, "registry_updates", {})

            if updates:
                current_turn_item_ids.update(updates.keys())

    # If we found items for this turn, filter the registry
    if current_turn_item_ids:
        # GDPR: Log counts only, NOT actual IDs
        logger.info(
            "filtering_registry_by_turn",
            turn_id=current_turn_id,
            total_items=len(data_registry),
            filtered_items=len(current_turn_item_ids),
            source="registry_updates",
        )
        return {k: v for k, v in data_registry.items() if k in current_turn_item_ids}

    # BugFix 2025-12-19: For REFERENCE turns without registry_updates,
    # use resolved_context items to filter the registry.
    # This handles cases like "detail du premier" where the item already exists
    # in the registry from a previous turn and no new registry_updates are created.
    if resolved_context and resolved_context.get("items"):
        resolved_item_ids: set[str] = set()
        source_turn_id = resolved_context.get("source_turn_id")

        # Debug: Log resolved_context structure (no IDs for GDPR)
        logger.debug(
            "filtering_registry_resolved_context_debug",
            turn_id=current_turn_id,
            resolved_items_count=len(resolved_context.get("items", [])),
            registry_count=len(data_registry),
        )

        # Build index for O(1) lookup (instead of O(N*M) nested loops)
        payload_index = build_registry_payload_index(data_registry)

        # Find registry IDs for resolved items using indexed lookup
        for resolved_item in resolved_context["items"]:
            if not isinstance(resolved_item, dict):
                continue

            # Check common ID fields (generic for all domains)
            item_id = resolved_item.get("id") or resolved_item.get("resourceName")

            if item_id:
                # O(1) lookup instead of O(N) iteration
                reg_key = payload_index.get(item_id)
                if reg_key:
                    resolved_item_ids.add(reg_key)
                else:
                    logger.debug(
                        "filtering_registry_no_match_for_item",
                        turn_id=current_turn_id,
                        registry_count=len(data_registry),
                    )

        if resolved_item_ids:
            # GDPR: Log counts only, NOT actual IDs
            logger.info(
                "filtering_registry_by_turn",
                turn_id=current_turn_id,
                total_items=len(data_registry),
                filtered_items=len(resolved_item_ids),
                source="resolved_context",
                source_turn_id=source_turn_id,
            )
            return {k: v for k, v in data_registry.items() if k in resolved_item_ids}

        # resolved_context had items but no match found
        logger.info(
            "filtering_registry_resolved_context_no_match",
            turn_id=current_turn_id,
            total_items=len(data_registry),
            resolved_items_count=len(resolved_context.get("items", [])),
            source_turn_id=source_turn_id,
        )

    # Security: REFERENCE turns must NOT leak data from other turns
    if turn_type == TURN_TYPE_REFERENCE:
        logger.warning(
            "filtering_registry_reference_turn_no_match",
            turn_id=current_turn_id,
            total_items=len(data_registry),
            resolved_items_count=len(resolved_context.get("items", [])) if resolved_context else 0,
        )
        return {}  # Fail-safe: prevent data leak

    # ==========================================================================
    # FIX 2025-12-26: Return empty dict for ACTION turns without registry_updates
    # ==========================================================================
    # PROBLEM: Returning full registry caused cross-turn contamination:
    #   - Weather query fails → no registry_updates
    #   - Old Places items from previous turn leaked into current_turn_registry
    #   - Photo injection detected "places" domain → injected OLD photo
    #   - Result: weather response with unrelated Places photo
    #
    # SOLUTION: If no registry_updates for current turn, return empty dict.
    # This prevents old registry data from contaminating current turn.
    #
    # SAFE because:
    #   - agent_results text is NOT affected (still contains tool output)
    #   - Tools producing registry data ALWAYS have registry_updates
    #   - Only structured registry data is filtered (not text responses)
    #
    # EFFECTS:
    #   - Weather/Wikipedia/utility tools: empty registry (correct)
    #   - Places/Contacts/Files with results: filtered registry (unchanged)
    # ==========================================================================
    logger.info(
        "filtering_registry_no_updates_empty",
        turn_id=current_turn_id,
        total_items_in_full_registry=len(data_registry),
        turn_type=turn_type,
        reason="no_registry_updates_for_current_turn",
    )
    return {}  # Return empty to prevent cross-turn contamination


def filter_registry_by_relevant_ids(
    registry: dict[str, Any],
    relevant_ids: list[str],
) -> dict[str, Any]:
    """
    Filter registry to include only items with IDs in relevant_ids list.

    This function is called after the LLM has analyzed the data and returned
    the IDs of items that match the user's filter criteria.

    BugFix 2026-01-02: LLM sometimes returns raw API IDs (e.g., Google Calendar event ID)
    instead of registry keys (e.g., event_7f0bc4). Now matches on both registry key AND
    payload.id for robustness using build_registry_payload_index.

    BugFix 2026-01-04: LLM sometimes returns hash suffix only (e.g., "600dc4") instead
    of full registry key (e.g., "event_600dc4"). This happens inconsistently, especially
    with longer result lists. Now also matches by hash suffix using suffix index.

    Args:
        registry: Full registry dict with all items
        relevant_ids: List of item IDs to keep (can be registry keys OR payload IDs OR hash suffixes)

    Returns:
        Filtered registry containing only relevant items
    """
    if not relevant_ids:
        # Empty list means no items match - return empty registry
        logger.info(
            "intelligent_filtering_no_matches",
            original_count=len(registry),
        )
        return {}

    if not registry:
        return {}

    # Convert to set for O(1) lookup
    ids_set = set(relevant_ids)

    # BugFix 2026-01-02: Build payload index for fallback matching
    # LLM may return raw API IDs (e.g., Google Calendar ID) instead of registry keys
    payload_index = build_registry_payload_index(registry)

    # BugFix 2026-01-04: Build suffix index for hash-only matching
    # LLM sometimes returns "600dc4" instead of "event_600dc4"
    # Registry keys are formatted as "{type}_{hash}" so we extract the suffix after "_"
    suffix_index: dict[str, str] = {}
    for reg_key in registry.keys():
        if "_" in reg_key:
            # Extract suffix after last underscore (e.g., "event_600dc4" -> "600dc4")
            suffix = reg_key.rsplit("_", 1)[-1]
            suffix_index[suffix] = reg_key

    # Expand ids_set to include registry keys for payload IDs
    # This converts raw API IDs to their registry keys for O(1) matching
    expanded_ids = set(ids_set)
    prefix_matched = 0
    suffix_matched = 0

    for rel_id in relevant_ids:
        # 1. Exact match on registry key (already in ids_set via expanded_ids)
        if rel_id in registry:
            continue

        # 2. Exact match on payload ID
        reg_key = payload_index.get(rel_id)
        if reg_key:
            expanded_ids.add(reg_key)
            continue

        # 3. BugFix 2026-01-04: Suffix matching for hash-only IDs
        # LLM returns "600dc4" instead of "event_600dc4" for longer result lists
        # Hash suffix is 6 hex chars (from generate_registry_id)
        reg_key = suffix_index.get(rel_id)
        if reg_key:
            expanded_ids.add(reg_key)
            suffix_matched += 1
            continue

        # 4. BugFix 2026-01-02 v2: Prefix matching for truncated IDs
        # LLM truncates long Google Calendar IDs - match by prefix (min 20 chars)
        if len(rel_id) >= 20:
            for payload_id, reg_key in payload_index.items():
                if payload_id.startswith(rel_id):
                    expanded_ids.add(reg_key)
                    prefix_matched += 1
                    break  # Only match first (avoid duplicates)

    # Filter registry with expanded ID set (O(N) lookup)
    filtered = {k: v for k, v in registry.items() if k in expanded_ids}

    logger.info(
        "intelligent_filtering_applied",
        original_count=len(registry),
        filtered_count=len(filtered),
        removed_count=len(registry) - len(filtered),
        prefix_matched=prefix_matched,
        suffix_matched=suffix_matched,
    )

    return filtered


def parse_relevant_ids_from_response(content: str) -> tuple[list[str], str]:
    """
    Parse <relevant_ids> tag from LLM response for intelligent filtering.

    The LLM returns relevant item IDs in a tag at the beginning of the response:
    <relevant_ids>item_id_1,item_id_2,item_id_3</relevant_ids>

    This function extracts the IDs and returns the cleaned content without the tag.

    Args:
        content: Full LLM response content

    Returns:
        Tuple of (list of relevant item IDs, content without the tag)
        If no tag found, returns (empty list, original content)
    """
    import re

    if not content:
        return [], content

    # Pattern to match <relevant_ids>...</relevant_ids> anywhere in content
    pattern = r"<relevant_ids>(.*?)</relevant_ids>"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

    if not match:
        # No filtering tag found - return original content, no filtering needed
        return [], content

    # Extract IDs (comma-separated, possibly with whitespace)
    ids_str = match.group(1).strip()
    if ids_str:
        # Split by comma and clean each ID
        relevant_ids = [id.strip() for id in ids_str.split(",") if id.strip()]
    else:
        # Empty tag means no items match the filter
        relevant_ids = []

    # Remove the tag from content
    cleaned_content = re.sub(pattern, "", content, flags=re.DOTALL | re.IGNORECASE).strip()

    # Log the filtering action
    logger.info(
        "intelligent_filtering_parsed",
        relevant_ids_count=len(relevant_ids),
        relevant_ids=relevant_ids[:10],  # Log first 10 for debugging
        content_cleaned=len(cleaned_content) < len(content),
    )

    return relevant_ids, cleaned_content
