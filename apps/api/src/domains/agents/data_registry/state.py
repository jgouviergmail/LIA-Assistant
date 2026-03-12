"""
Data Registry State Management.

Provides LangGraph-compatible reducers and utilities for managing the data registry
within the agent state. Follows LangGraph v1.0 best practices for state mutations.

Architecture:
- merge_registry: Reducer that properly merges registry updates (last-write-wins)
- RegistryField: Type alias with reducer annotation for MessagesState
- Utilities for filtering, expiration, and SSE serialization

LangGraph v1.0 Compliance:
- Reducers are pure functions: (current, update) -> merged
- No side effects in reducers
- Proper handling of None values
- Compatible with PostgresCheckpointer persistence

Usage:
    from src.domains.agents.data_registry import RegistryField, merge_registry

    class MyAgentState(TypedDict):
        registry: RegistryField
        # other fields...

    # In node:
    return {"registry": {"contact_abc": new_item}}
    # Will be merged with existing registry via merge_registry reducer

Created: 2025-11-27
"""

from typing import Annotated, Any

from src.domains.agents.data_registry.models import RegistryItem

# Epoch used as sort fallback when timestamp is missing or unreadable
_EPOCH_TIMESTAMP = "1970-01-01T00:00:00Z"


def _get_item_timestamp(item: RegistryItem | dict) -> Any:
    """Extract timestamp from a RegistryItem or its serialized dict form.

    Items in the registry may be Pydantic ``RegistryItem`` objects (when stored
    directly by a node) **or** plain dicts (after ``model_dump(mode="json")`` in
    ``_execute_tool``).  The LRU eviction sort needs to handle both.
    """
    if hasattr(item, "meta"):
        # Pydantic RegistryItem → .meta.timestamp (datetime)
        return item.meta.timestamp
    if isinstance(item, dict):
        meta = item.get("meta")
        if isinstance(meta, dict):
            return meta.get("timestamp", _EPOCH_TIMESTAMP)
    return _EPOCH_TIMESTAMP


def merge_registry(
    current: dict[str, RegistryItem] | None,
    updates: dict[str, RegistryItem] | None,
) -> dict[str, RegistryItem]:
    """
    LangGraph reducer for merging registry updates with LRU eviction.

    Implements last-write-wins semantics: new items with existing IDs
    overwrite previous items. This is intentional for update scenarios.

    LRU Eviction (Sprint 17.3):
    When registry exceeds REGISTRY_MAX_ITEMS, oldest items (by meta.timestamp)
    are evicted to prevent unbounded memory growth. This is critical for
    long-running conversations with many tool results.

    LangGraph Reducer Contract:
    - Takes (current_value, new_value) as arguments
    - Returns merged result
    - Must be pure (no side effects)
    - Must handle None values gracefully

    Args:
        current: Current registry state (may be None on first call)
        updates: New registry items to add/update (may be None)

    Returns:
        Merged registry dict with all items (capped at REGISTRY_MAX_ITEMS)

    Example:
        # In state definition
        class MyState(TypedDict):
            registry: Annotated[dict[str, RegistryItem], merge_registry]

        # In node
        return {"registry": {"contact_abc": new_item}}
        # Result: existing items + new_item (overwrites if same ID)
        # If over limit, oldest items by timestamp are evicted
    """
    from src.core.config import get_settings

    if current is None:
        current = {}
    if updates is None:
        return current

    # Get registry max items from settings (configurable via REGISTRY_MAX_ITEMS env var)
    registry_max_items = get_settings().registry_max_items

    # Merge updates into current (updates overwrite existing keys)
    merged = {**current, **updates}

    # LRU eviction: if over limit, keep only most recent items
    if len(merged) > registry_max_items:
        # Sort by timestamp (most recent first) and keep newest items.
        # Items may be RegistryItem objects (.meta.timestamp) or serialized
        # dicts (["meta"]["timestamp"]) depending on the pipeline stage.
        sorted_items = sorted(
            merged.items(),
            key=lambda x: _get_item_timestamp(x[1]),
            reverse=True,
        )
        # Keep only registry_max_items most recent items
        merged = dict(sorted_items[:registry_max_items])

    return merged


def clear_registry_expired(
    registry: dict[str, RegistryItem],
    max_age_seconds: int = 3600,
) -> dict[str, RegistryItem]:
    """
    Remove expired items from registry based on TTL.

    This is NOT a reducer - it's a utility function to be called
    periodically or at conversation boundaries for cache cleanup.

    Expiration logic:
    1. If item has explicit ttl_seconds, use that
    2. Otherwise, use max_age_seconds as default TTL
    3. Items without timestamp are kept (defensive)

    Args:
        registry: Current registry dict
        max_age_seconds: Maximum age for items without explicit TTL (default: 1 hour)

    Returns:
        Registry with expired items removed

    Usage:
        # At conversation end or periodically
        cleaned = clear_registry_expired(state["registry"], max_age_seconds=1800)
    """
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    result = {}

    for item_id, item in registry.items():
        # Items may be RegistryItem objects or serialized dicts
        if hasattr(item, "meta"):
            meta = item.meta
            timestamp = meta.timestamp
            ttl = meta.ttl_seconds
        elif isinstance(item, dict) and isinstance(item.get("meta"), dict):
            meta_dict = item["meta"]
            ts_raw = meta_dict.get("timestamp")
            # Parse ISO string to datetime for comparison
            if isinstance(ts_raw, str):
                try:
                    from datetime import datetime as dt_cls

                    timestamp = dt_cls.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    result[item_id] = item
                    continue
            else:
                timestamp = ts_raw
            ttl = meta_dict.get("ttl_seconds")
        else:
            # Defensive: keep items with unreadable meta
            result[item_id] = item
            continue

        # Check explicit TTL first
        if ttl is not None:
            age = (now - timestamp).total_seconds()
            if age < ttl:
                result[item_id] = item
        # Check max age for items without TTL
        else:
            age = (now - timestamp).total_seconds()
            if age < max_age_seconds:
                result[item_id] = item

    return result


def get_registry_items_by_type(
    registry: dict[str, RegistryItem],
    item_type: str,
) -> list[RegistryItem]:
    """
    Filter registry items by type.

    Useful for extracting all items of a specific domain
    (e.g., all contacts, all emails).

    Args:
        registry: Current registry dict
        item_type: Type to filter by (e.g., "CONTACT", "EMAIL", "EVENT")

    Returns:
        List of matching RegistryItems (preserves order)

    Example:
        contacts = get_registry_items_by_type(registry, "CONTACT")
        emails = get_registry_items_by_type(registry, "EMAIL")
    """
    result = []
    for item in registry.values():
        if hasattr(item, "type") and hasattr(item.type, "value"):
            if item.type.value == item_type:
                result.append(item)
        elif isinstance(item, dict) and item.get("type") == item_type:
            result.append(item)
    return result


def serialize_registry_for_sse(
    registry_updates: dict[str, RegistryItem],
) -> list[dict[str, Any]]:
    """
    Serialize registry updates for SSE transmission.

    Converts RegistryItem objects to dicts suitable for JSON serialization
    in SSE events. Uses Pydantic's mode="json" for proper datetime handling.

    Args:
        registry_updates: Dict of registry items to serialize

    Returns:
        List of serialized item dicts ready for SSE transmission

    Output format:
        [
            {
                "id": "contact_abc123",
                "type": "CONTACT",
                "payload": {...},
                "meta": {
                    "source": "google_contacts",
                    "domain": "contacts",
                    "timestamp": "2025-11-27T10:30:00Z",
                    ...
                }
            }
        ]

    Note:
        Uses mode="json" to ensure datetime objects are serialized as ISO strings,
        avoiding "Object of type datetime is not JSON serializable" errors.
    """
    return [item.model_dump(mode="json") for item in registry_updates.values()]


# Type alias for the registry field with its reducer
# Use this in MessagesState definition for proper LangGraph integration
RegistryField = Annotated[dict[str, RegistryItem], merge_registry]
