"""
Data Registry Package.

Provides infrastructure for storing and managing rich data items (contacts, emails, events)
that are streamed to the frontend via SSE for rich component rendering.

Architecture:
- RegistryItem: A single data item with type, payload, and metadata
- RegistryItemType: Enum of supported item types (CONTACT, EMAIL, EVENT, DRAFT, etc.)
- merge_registry: LangGraph reducer for state management
- serialize_registry_for_sse: Helper for SSE transmission

The data registry enables separation between:
1. LLM context (compact summaries via StandardToolOutput.summary_for_llm)
2. Frontend rendering (complete data via SSE registry_update events)

This architecture optimizes token usage while providing rich UI components.

Usage:
    from src.domains.agents.data_registry import (
        RegistryItem,
        RegistryItemType,
        RegistryItemMeta,
        generate_registry_id,
        merge_registry,
        serialize_registry_for_sse,
    )

    # Create a registry item
    item = RegistryItem(
        id=generate_registry_id(RegistryItemType.CONTACT, "people/c123"),
        type=RegistryItemType.CONTACT,
        payload={"resourceName": "people/c123", "names": [...]},
        meta=RegistryItemMeta(source="google_contacts", domain="contacts"),
    )

Created: 2025-11-27
"""

from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.data_registry.state import (
    RegistryField,
    clear_registry_expired,
    get_registry_items_by_type,
    merge_registry,
    serialize_registry_for_sse,
)

# Legacy formatters - kept for backward compatibility but no longer used
# INTELLIA v10: Data is formatted as JSON for LLM few-shot processing
# See response_node.py::_format_registry_mode_results() for the new architecture

__all__ = [
    # Models
    "RegistryItem",
    "RegistryItemMeta",
    "RegistryItemType",
    "generate_registry_id",
    # State management
    "RegistryField",
    "merge_registry",
    "clear_registry_expired",
    "get_registry_items_by_type",
    "serialize_registry_for_sse",
]
