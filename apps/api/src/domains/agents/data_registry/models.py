"""
Data Registry Models.

Defines the data structures for items stored in the Data Registry.
These items are sent via SSE (registry_update event) before LLM response,
enabling the frontend to render rich components.

Architecture:
- RegistryItem: A single item in the registry (contact, email, event, etc.)
- RegistryItemMeta: Metadata about the item (source, timestamp, domain)
- Registry is keyed by item ID (e.g., "contact_abc123")

Best Practices:
- Items are immutable once created (Pydantic frozen=False for serialization flexibility)
- IDs are deterministic based on source system identifiers
- Metadata tracks provenance for debugging and cache management
- TTL support for automatic expiration

Usage:
    item = RegistryItem(
        id="contact_abc123",
        type=RegistryItemType.CONTACT,
        payload={"name": "John Doe", "email": "john@example.com"},
        meta=RegistryItemMeta(source="google_contacts", domain="contacts"),
    )

Created: 2025-11-27
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RegistryItemType(str, Enum):
    """
    Types of items that can be stored in the Data Registry.

    Each type corresponds to a frontend component for rendering.
    Extensible for future domain integrations.

    Naming Convention:
    - Use singular form (CONTACT, not CONTACTS)
    - Use SCREAMING_SNAKE_CASE
    - Group by domain/category
    """

    # Google Workspace domain types
    CONTACT = "CONTACT"
    EMAIL = "EMAIL"
    EVENT = "EVENT"
    TASK = "TASK"
    FILE = "FILE"  # Google Drive files
    CALENDAR = "CALENDAR"  # Google Calendar (calendar list item)

    # External API domain types
    PLACE = "PLACE"  # Google Places
    LOCATION = "LOCATION"  # Reverse geocoding result (current position)
    ROUTE = "ROUTE"  # Google Routes (directions/itinerary)
    WEATHER = "WEATHER"  # OpenWeatherMap
    WIKIPEDIA_ARTICLE = "WIKIPEDIA_ARTICLE"  # Wikipedia
    SEARCH_RESULT = "SEARCH_RESULT"  # Perplexity search
    WEB_SEARCH = "WEB_SEARCH"  # Unified web search (Perplexity + Brave + Wikipedia)

    # HITL/Draft types (confirmation flow)
    DRAFT = "DRAFT"

    # Visualization types
    CHART = "CHART"

    # Internal domain types (no OAuth)
    REMINDER = "REMINDER"  # User reminders (internal)
    WEB_PAGE = "WEB_PAGE"  # Fetched web page content (evolution F1)
    MCP_RESULT = "MCP_RESULT"  # MCP tool result (evolution F2.3)
    MCP_APP = "MCP_APP"  # MCP Apps interactive widget (evolution F2.5)

    # Generic/utility types
    NOTE = "NOTE"
    CALENDAR_SLOT = "CALENDAR_SLOT"


class RegistryItemMeta(BaseModel):
    """
    Metadata for a registry item.

    Contains information about the item's origin, lifecycle, and caching.
    Essential for debugging, metrics, and cache invalidation.

    Attributes:
        source: Source system identifier (e.g., 'google_contacts', 'gmail')
        domain: Domain context for routing (e.g., 'contacts', 'emails', 'calendar')
        timestamp: UTC timestamp when added to registry
        tool_name: Tool that created this item (for tracing)
        step_id: Execution plan step ID (for correlation)
        ttl_seconds: Time-to-live for cache expiration (None = no expiry)
    """

    source: str = Field(
        ...,
        description="Source system (e.g., 'google_contacts', 'gmail', 'google_calendar')",
    )
    domain: str | None = Field(
        default=None,
        description="Domain context (e.g., 'contacts', 'emails', 'calendar')",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the item was added to registry (UTC)",
    )
    tool_name: str | None = Field(
        default=None,
        description="Tool that created this item (e.g., 'search_contacts_tool')",
    )
    step_id: str | None = Field(
        default=None,
        description="Execution plan step ID that produced this item",
    )
    ttl_seconds: int | None = Field(
        default=None,
        description="Time-to-live in seconds (None = no expiry)",
    )
    turn_id: int | None = Field(
        default=None,
        description="Turn ID when this item was created (for context resolution filtering)",
    )
    correlated_to: str | None = Field(
        default=None,
        description="Registry ID of parent item for correlated display (e.g., Route correlated to Event)",
    )


class RegistryItem(BaseModel):
    """
    A single item in the Data Registry.

    Represents any data entity that can be rendered as a rich component
    in the frontend. The LLM references items by ID in responses.

    Attributes:
        id: Unique identifier (e.g., "contact_abc123", "email_xyz789")
        type: Type of item (determines frontend component)
        payload: Complete data for the item (domain-specific structure)
        meta: Metadata about the item's origin and lifecycle

    Example - Contact:
        RegistryItem(
            id="contact_abc123",
            type=RegistryItemType.CONTACT,
            payload={
                "resourceName": "people/c123",
                "names": [{"displayName": "John Doe"}],
                "emailAddresses": [{"value": "john@example.com"}],
                "phoneNumbers": [{"value": "+1234567890"}],
            },
            meta=RegistryItemMeta(source="google_contacts", domain="contacts"),
        )

    Example - Email:
        RegistryItem(
            id="email_xyz789",
            type=RegistryItemType.EMAIL,
            payload={
                "id": "msg123",
                "threadId": "thread456",
                "subject": "Meeting tomorrow",
                "from": "jane@example.com",
                "snippet": "Hi, let's meet tomorrow...",
            },
            meta=RegistryItemMeta(source="gmail", domain="emails"),
        )
    """

    id: str = Field(
        ...,
        description="Unique identifier for this item (e.g., 'contact_abc123')",
    )
    type: RegistryItemType = Field(
        ...,
        description="Type of item (determines frontend component)",
    )
    payload: dict[str, Any] = Field(
        ...,
        description="Complete data for the item (domain-specific structure)",
    )
    meta: RegistryItemMeta = Field(
        ...,
        description="Metadata about the item's origin and lifecycle",
    )

    model_config = {}  # datetime serializes to ISO format by default in Pydantic v2


def generate_registry_id(item_type: RegistryItemType, unique_key: str) -> str:
    """
    Generate a deterministic registry ID from type and unique key.

    The ID format is: "{type_lowercase}_{hash_suffix}"

    Uses SHA-256 for collision resistance while keeping IDs short.
    The same unique_key always produces the same ID (deterministic).

    Args:
        item_type: Type of the item (determines prefix)
        unique_key: Unique identifier from the source system
            (e.g., resourceName for contacts, message_id for emails)

    Returns:
        Registry ID string (e.g., "contact_7f8a9b")

    Example:
        >>> generate_registry_id(RegistryItemType.CONTACT, "people/c123456789")
        "contact_7f8a9b"
        >>> generate_registry_id(RegistryItemType.EMAIL, "msg_abc123")
        "email_a1b2c3"
    """
    import hashlib

    # Create a short hash from the unique key
    hash_bytes = hashlib.sha256(unique_key.encode()).digest()
    hash_suffix = hash_bytes[:6].hex()[:6]  # 6 hex chars = 16M+ unique IDs

    type_prefix = item_type.value.lower()
    return f"{type_prefix}_{hash_suffix}"
