"""
Pydantic schemas for Tool Context Management.

Defines type-safe data structures for storing and retrieving tool results
in LangGraph BaseStore.

Architecture:
    - ToolContextList: Liste d'items pour un domaine (stored under key "list")
    - ToolContextDetails: Item details for a domain (stored under key "details")
    - ToolContextCurrentItem: Item courant pour un domaine (stored under key "current")
    - ResolutionResult: Result of reference resolution
    - ContextMetadata: Additional metadata for context items
    - ContextSaveMode: Classification enum for save routing (list vs details vs current)

These schemas ensure type safety across the entire context management system.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ContextSaveMode(str, Enum):
    """
    Classification modes for context save routing.

    Determines which Store key to use when auto-saving tool results.

    Modes:
        LIST: Search/list results → Store key "list" (overwrite behavior)
        DETAILS: Item details → Store key "details" (LRU merge, max 10 items)
        CURRENT: Selected item → Store key "current" (manual set only)
        NONE: No auto-save (tool doesn't produce context-worthy results)

    Usage:
        >>> mode = classify_save_mode(tool_name="search_contacts_tool", result_count=10)
        >>> # Returns ContextSaveMode.LIST

        >>> mode = classify_save_mode(tool_name="get_contact_details_tool", result_count=2)
        >>> # Returns ContextSaveMode.DETAILS

    Convention-based Classification Rules:
        1. Tool name contains "search", "list", "find" → LIST
        2. Tool name contains "get", "show", "detail" → DETAILS
        3. Result count > 10 → LIST
        4. Result count <= 10 → DETAILS
        5. Explicit manifest.context_save_mode → Use explicit mode
    """

    LIST = "list"
    DETAILS = "details"
    CURRENT = "current"
    NONE = "none"


class ContextMetadata(BaseModel):
    """
    Metadata associated with a tool context.

    Attributes:
        turn_id: LangGraph turn identifier when context was created.
        total_count: Total number of items in original tool result.
        query: Original user query that generated this context.
        tool_name: Name of the tool that generated the results.
        timestamp: ISO 8601 timestamp when context was saved.

    Example:
        >>> metadata = ContextMetadata(
        ...     turn_id=5,
        ...     total_count=10,
        ...     query="liste mes contacts travail",
        ...     tool_name="search_contacts_tool",
        ...     timestamp="2025-01-26T14:30:00Z"
        ... )
    """

    turn_id: int = Field(description="LangGraph turn ID")
    total_count: int = Field(description="Total items count")
    query: str | None = Field(default=None, description="Original user query")
    tool_name: str | None = Field(default=None, description="Tool that generated results")
    timestamp: str = Field(description="ISO 8601 timestamp")


class ToolContextList(BaseModel):
    """
    Liste d'items pour un domaine spécifique.

    Stored in LangGraph BaseStore under:
        Namespace: (user_id, "context", domain)
        Key: "list"

    Attributes:
        domain: Domain identifier ("contacts", "emails", "events").
        items: List of indexed items (1-based) with enriched data.
        metadata: Additional metadata (turn_id, query, etc.).

    Example:
        >>> context_list = ToolContextList(
        ...     domain="contacts",
        ...     items=[
        ...         {
        ...             "index": 1,
        ...             "resource_name": "people/c123",
        ...             "name": "Jean Dupond",
        ...             "emails": ["jean@example.com"]
        ...         },
        ...         {
        ...             "index": 2,
        ...             "resource_name": "people/c456",
        ...             "name": "Marie Martin",
        ...             "emails": ["marie@example.com"]
        ...         }
        ...     ],
        ...     metadata=ContextMetadata(
        ...         turn_id=5,
        ...         total_count=2,
        ...         query="liste mes contacts",
        ...         tool_name="search_contacts_tool",
        ...         timestamp="2025-01-26T14:30:00Z"
        ...     )
        ... )

    Store Pattern:
        >>> namespace = (user_id, "context", "contacts")
        >>> key = "list"
        >>> await store.aput(namespace, key, context_list.model_dump())
    """

    domain: str = Field(description="Domain identifier (contacts, emails, events)")
    items: list[dict[str, Any]] = Field(
        description="Indexed items with enriched data (includes 'index' field)"
    )
    metadata: ContextMetadata = Field(description="Context metadata")

    def get_item_by_index(self, index: int) -> dict[str, Any] | None:
        """
        Get item by positional index (1-based).

        Args:
            index: 1-based index (e.g., 1 for "first", 2 for "second").

        Returns:
            Item dict if found, None otherwise.

        Example:
            >>> item = context_list.get_item_by_index(2)
            >>> # Returns {"index": 2, "name": "Marie Martin", ...}
        """
        for item in self.items:
            if item.get("index") == index:
                return item
        return None

    def get_item_by_field(self, field_name: str, field_value: Any) -> dict[str, Any] | None:
        """
        Get item by field exact match.

        Args:
            field_name: Field to search.
            field_value: Value to match.

        Returns:
            First matching item, or None.

        Example:
            >>> item = context_list.get_item_by_field("resource_name", "people/c123")
        """
        for item in self.items:
            if item.get(field_name) == field_value:
                return item
        return None


class ToolContextDetails(BaseModel):
    """
    Item details for a specific domain (LRU cache pattern).

    Stored in LangGraph BaseStore under:
        Namespace: (user_id, "context", domain)
        Key: "details"

    This schema implements an LRU (Least Recently Used) cache for detailed item views.
    Unlike ToolContextList (which overwrites), ToolContextDetails MERGES new items
    and evicts oldest when max_items is reached.

    Attributes:
        domain: Domain identifier ("contacts", "emails", "events").
        items: List of detailed items (max 10 by default).
        metadata: Metadata for the details cache.

    Example:
        >>> # Initial state: Empty details
        >>> details = ToolContextDetails(domain="contacts", items=[], metadata=...)

        >>> # After get_contact_details("people/c123")
        >>> details.items = [{"index": 1, "resource_name": "people/c123", ...}]

        >>> # After get_contact_details("people/c456", "people/c789")
        >>> details.items = [
        ...     {"index": 1, "resource_name": "people/c123", ...},  # Existing
        ...     {"index": 2, "resource_name": "people/c456", ...},  # New
        ...     {"index": 3, "resource_name": "people/c789", ...},  # New
        ... ]

    Merge Logic (LRU):
        1. Fetch existing ToolContextDetails from Store key "details"
        2. Merge new items (deduplicate by primary_id_field)
        3. Reindex items (1-based sequential)
        4. Evict oldest items if count > max_items (default 10)
        5. Update metadata.total_count and timestamp
        6. Save back to Store key "details"

    Store Pattern:
        >>> namespace = (user_id, "context", "contacts")
        >>> key = "details"
        >>> await store.aput(namespace, key, details.model_dump())

    Difference from ToolContextList:
        - ToolContextList: Overwrites on save (for search results)
        - ToolContextDetails: Merges on save (accumulates detail views)
    """

    domain: str = Field(description="Domain identifier (contacts, emails, events)")
    items: list[dict[str, Any]] = Field(
        description="Detailed items with enriched data (includes 'index' field)"
    )
    metadata: ContextMetadata = Field(description="Details cache metadata")

    def get_item_by_index(self, index: int) -> dict[str, Any] | None:
        """Get item by 1-based index."""
        for item in self.items:
            if item.get("index") == index:
                return item
        return None

    def get_item_by_field(self, field_name: str, field_value: Any) -> dict[str, Any] | None:
        """Get item by field exact match."""
        for item in self.items:
            if item.get(field_name) == field_value:
                return item
        return None


class ToolContextCurrentItem(BaseModel):
    """
    Item courant pour un domaine spécifique.

    Stored in LangGraph BaseStore under:
        Namespace: (user_id, "context", domain)
        Key: "current"

    Attributes:
        domain: Domain identifier ("contacts", "emails", "events").
        item: Complete item dict (includes all fields from original search).
        set_at: ISO 8601 timestamp when item was set as current.
        set_by: How the item was set ("auto" = 1 result, "explicit" = user choice).
        turn_id: Turn ID when item was set as current.

    Example:
        >>> current_item = ToolContextCurrentItem(
        ...     domain="contacts",
        ...     item={
        ...         "index": 2,
        ...         "resource_name": "people/c456",
        ...         "name": "Marie Martin",
        ...         "emails": ["marie@example.com"]
        ...     },
        ...     set_at="2025-01-26T14:30:00Z",
        ...     set_by="auto",
        ...     turn_id=5
        ... )

    Store Pattern:
        >>> namespace = (user_id, "context", "contacts")
        >>> key = "current"
        >>> await store.aput(namespace, key, current_item.model_dump())

    Rules:
        - set_by="auto": Item was auto-set because search returned 1 result
        - set_by="explicit": User explicitly selected this item (e.g., "le 2ème")
    """

    domain: str = Field(description="Domain identifier (contacts, emails, events)")
    item: dict[str, Any] = Field(description="Complete item dict (with 'index' field)")
    set_at: str = Field(description="ISO 8601 timestamp when set as current")
    set_by: Literal["auto", "explicit"] = Field(
        description="auto=1 result auto-set, explicit=user selected"
    )
    turn_id: int = Field(description="Turn ID when set as current")


class ResolutionResult(BaseModel):
    """
    Result of reference resolution.

    Returned by ReferenceResolver.resolve() and resolve_reference tool.

    Attributes:
        success: Whether resolution succeeded.
        item: Resolved item data (if success=True).
        confidence: Confidence score (0.0-1.0) for fuzzy matches.
        match_type: How reference was resolved ("index", "keyword", "fuzzy").
        error: Error code if success=False ("not_found", "ambiguous").
        message: Human-readable error message.
        candidates: List of possible matches if ambiguous.

    Examples:
        >>> # Success: Index match
        >>> result = ResolutionResult(
        ...     success=True,
        ...     item={"index": 2, "name": "Marie Martin", ...},
        ...     confidence=1.0,
        ...     match_type="index"
        ... )

        >>> # Success: Fuzzy match
        >>> result = ResolutionResult(
        ...     success=True,
        ...     item={"index": 1, "name": "Jean Dupond", ...},
        ...     confidence=0.85,
        ...     match_type="fuzzy"
        ... )

        >>> # Error: Not found
        >>> result = ResolutionResult(
        ...     success=False,
        ...     error="not_found",
        ...     message="'Pierre' non trouvé dans la liste."
        ... )

        >>> # Error: Ambiguous
        >>> result = ResolutionResult(
        ...     success=False,
        ...     error="ambiguous",
        ...     message="Plusieurs correspondances trouvées.",
        ...     candidates=[
        ...         {"index": 1, "name": "Jean Dupond", "confidence": 0.8},
        ...         {"index": 3, "name": "Jean-Marie Durand", "confidence": 0.75}
        ...     ]
        ... )
    """

    success: bool = Field(description="Whether resolution succeeded")
    item: dict[str, Any] | None = Field(default=None, description="Resolved item data")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Match confidence")
    match_type: Literal["index", "keyword", "fuzzy", "exact"] | None = Field(
        default=None, description="Resolution method"
    )
    error: Literal["not_found", "ambiguous", "no_context", "invalid_reference"] | None = Field(
        default=None, description="Error code"
    )
    message: str | None = Field(default=None, description="Human-readable message")
    candidates: list[dict[str, Any]] | None = Field(
        default=None, description="Ambiguous match candidates"
    )

    @classmethod
    def success_result(
        cls, item: dict[str, Any], confidence: float, match_type: str
    ) -> "ResolutionResult":
        """
        Create success resolution result.

        Args:
            item: Resolved item data.
            confidence: Match confidence (0.0-1.0).
            match_type: Resolution method ("index", "fuzzy", etc.).

        Returns:
            ResolutionResult with success=True.
        """
        return cls(success=True, item=item, confidence=confidence, match_type=match_type)

    @classmethod
    def error_result(
        cls,
        error: Literal["not_found", "ambiguous", "no_context", "invalid_reference"],
        message: str,
        candidates: list[dict[str, Any]] | None = None,
    ) -> "ResolutionResult":
        """
        Create error resolution result.

        Args:
            error: Error code.
            message: Human-readable error message.
            candidates: Optional list of ambiguous matches.

        Returns:
            ResolutionResult with success=False.
        """
        return cls(success=False, error=error, message=message, candidates=candidates)
