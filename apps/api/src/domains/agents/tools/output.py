"""
Tool Output Models.

Defines the contract that all tools must return.

Architecture Evolution (2025-12-29):
- StandardToolOutput: Original format for registry-compatible tools
- UnifiedToolOutput: New unified format for ALL tools (registry + actions)

UnifiedToolOutput addresses the following issues:
1. Missing `success` field in StandardToolOutput
2. Missing `error` handling in StandardToolOutput
3. Confusion between `summary_for_llm` (StandardToolOutput) and `message` (ToolResponse)
4. "Action without data" case not handled (reminders, confirmations)

Migration Path:
- New tools should use UnifiedToolOutput
- Existing tools using StandardToolOutput continue to work (compatible)
- StandardToolOutput.to_unified() converts to UnifiedToolOutput
- UnifiedToolOutput.to_standard() converts back for compatibility

Usage (New - UnifiedToolOutput):
    from src.domains.agents.tools.output import UnifiedToolOutput

    # Action confirmation (no registry data)
    async def create_reminder_tool(...) -> UnifiedToolOutput:
        reminder = await create_reminder(...)
        return UnifiedToolOutput.action_success(
            message=f"🔔 Rappel créé pour {formatted_time}",
            structured_data={"reminder_id": str(reminder.id)},
        )

    # Data query (with registry)
    async def search_contacts(...) -> UnifiedToolOutput:
        contacts = await search(...)
        return UnifiedToolOutput.data_success(
            message=f"Found {len(contacts)} contacts",
            registry_updates={...},
            structured_data={"contacts": contacts},
        )

    # Error
    async def failing_tool(...) -> UnifiedToolOutput:
        return UnifiedToolOutput.failure(
            message="Contact not found",
            error_code="NOT_FOUND",
        )

Usage (Legacy - StandardToolOutput):
    from src.domains.agents.tools.output import StandardToolOutput
    from src.domains.agents.data_registry import RegistryItem, RegistryItemType

    async def search_contacts(...) -> StandardToolOutput:
        contacts = await client.search_contacts(query)

        registry_updates = {}
        for contact in contacts:
            item_id = generate_registry_id(RegistryItemType.CONTACT, contact["resource_name"])
            registry_updates[item_id] = RegistryItem(
                id=item_id,
                type=RegistryItemType.CONTACT,
                payload=contact,
                meta=RegistryItemMeta(source="google_contacts"),
            )

        return StandardToolOutput(
            summary_for_llm=f"Found {len(contacts)} contacts",
            registry_updates=registry_updates,
            structured_data={"contacts": contacts, "count": len(contacts)},
        )
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType

# =============================================================================
# INTELLIPLANNER B+ - Registry Type to Key Mapping
# =============================================================================
# Unified naming convention (v3.2):
# - domain = singular entity name (contact, email, event, weather, etc.)
# - result_key = domain + "s" (contacts, emails, events, weathers, etc.)
# - All keys follow the same pattern for consistency

REGISTRY_TYPE_TO_KEY: dict[RegistryItemType, str] = {
    RegistryItemType.CONTACT: "contacts",
    RegistryItemType.EMAIL: "emails",
    RegistryItemType.EVENT: "events",
    RegistryItemType.CALENDAR: "calendars",
    RegistryItemType.TASK: "tasks",
    RegistryItemType.FILE: "files",
    RegistryItemType.PLACE: "places",
    RegistryItemType.LOCATION: "locations",  # GPS position (get_current_location_tool)
    RegistryItemType.ROUTE: "routes",  # Google Routes directions
    RegistryItemType.WEATHER: "weathers",  # domain + "s" pattern
    RegistryItemType.WIKIPEDIA_ARTICLE: "wikipedias",  # domain + "s" pattern
    RegistryItemType.SEARCH_RESULT: "perplexitys",  # domain + "s" pattern (perplexity search)
    RegistryItemType.WEB_SEARCH: "web_searchs",  # Unified triple source search
    RegistryItemType.REMINDER: "reminders",  # User reminders (internal)
    RegistryItemType.WEB_PAGE: "web_fetchs",  # domain + "s" pattern (evolution F1)
    RegistryItemType.MCP_RESULT: "mcps",  # domain + "s" pattern (evolution F2.3)
    RegistryItemType.MCP_APP: "mcp_apps",  # MCP interactive widgets (evolution F2.5)
    RegistryItemType.DRAFT: "drafts",
    RegistryItemType.CHART: "charts",
    RegistryItemType.NOTE: "notes",
    RegistryItemType.CALENDAR_SLOT: "slots",
}


class StandardToolOutput(BaseModel):
    """
    Standard output format for all registry-compatible tools.

    This model ensures consistent separation between:
    1. What the LLM sees (summary_for_llm) - compact, token-efficient
    2. What the frontend gets (registry_updates) - complete data via SSE
    3. What Jinja2 templates access (structured_data) - queryable data (INTELLIPLANNER B+)

    Attributes:
        summary_for_llm: Compact summary for LLM context
            - Should be concise (ideally < 200 tokens)
            - Contains IDs that LLM can reference
            - Example: "Found 3 contacts: John (contact_abc), Jane (contact_def), Bob (contact_ghi)"

        registry_updates: Dict mapping item IDs to RegistryItems
            - Keys are registry IDs (e.g., "contact_abc123")
            - Values are complete RegistryItem objects
            - Sent to frontend via SSE registry_update event
            - Frontend uses these to render rich components

        structured_data: Dict for Jinja2 template access (INTELLIPLANNER B+)
            - Contains queryable structured data for inter-step references
            - Example: {"calendars": [...], "count": 5, "primary_id": "cal_abc"}
            - Accessed via {{ steps.step_id.calendars[0].id }}

        tool_metadata: Optional metadata for debugging/metrics
            - Can include: execution_time_ms, api_calls_made, cache_hit, etc.
            - Not sent to LLM or frontend, only for observability

    Example:
        StandardToolOutput(
            summary_for_llm="Found 3 contacts matching 'john': contact_abc, contact_def, contact_ghi",
            registry_updates={
                "contact_abc": RegistryItem(...),
                "contact_def": RegistryItem(...),
                "contact_ghi": RegistryItem(...),
            },
            structured_data={
                "contacts": [{"name": "John Doe", "id": "contact_abc"}, ...],
                "count": 3,
            },
            tool_metadata={
                "execution_time_ms": 150,
                "api_calls_made": 1,
                "from_cache": True,
            },
        )
    """

    summary_for_llm: str = Field(
        ...,
        description="Compact summary for LLM context (should include IDs for references)",
    )
    registry_updates: dict[str, RegistryItem] = Field(
        default_factory=dict,
        description="Registry items keyed by ID (sent to frontend via SSE)",
    )
    structured_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured data for Jinja2 templates (e.g., {'calendars': [...], 'count': 5})",
    )
    tool_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata for debugging/observability",
    )

    def get_step_output(self) -> dict[str, Any]:
        """
        Get data structure for completed_steps (Jinja2 template access).

        INTELLIPLANNER B+: This method provides the data that will be stored in
        completed_steps[step_id] and accessible via Jinja2 templates like
        {{ steps.list_calendars.calendars[0].id }}.

        Priority:
        1. structured_data if populated (explicit, preferred)
        2. Fallback: extract payloads from registry_updates grouped by type
        3. Ultimate fallback: {"summary": summary_for_llm, "count": 0}

        Returns:
            Dict suitable for Jinja2 access like {{ steps.step_id.contacts[0].name }}
        """
        # Priority 1: Use explicit structured_data if populated
        if self.structured_data:
            return self.structured_data

        # Priority 2: Fallback - extract payloads from registry_updates grouped by type
        if self.registry_updates:
            result: dict[str, Any] = {}
            for item in self.registry_updates.values():
                # Use explicit mapping, fallback to lowercase+s for unknown types
                type_key = REGISTRY_TYPE_TO_KEY.get(item.type, item.type.value.lower() + "s")
                if type_key not in result:
                    result[type_key] = []
                result[type_key].append(item.payload)

            # Add count for convenience (total items across all types)
            result["count"] = sum(len(v) for v in result.values() if isinstance(v, list))
            return result

        # Priority 3: Ultimate fallback - just the summary
        return {"summary": self.summary_for_llm, "count": 0}

    def to_llm_message(self) -> str:
        """
        Convert to the string that will be added to LLM messages.

        Returns just the summary, as registry_updates go via SSE.
        """
        return self.summary_for_llm

    def get_registry_ids(self) -> list[str]:
        """
        Get list of all registry item IDs in this output.

        Useful for tracking which items were produced by a tool call.
        """
        return list(self.registry_updates.keys())

    def merge(self, other: "StandardToolOutput") -> "StandardToolOutput":
        """
        Merge another StandardToolOutput into this one.

        Useful for combining results from multiple tool calls.

        Args:
            other: Another StandardToolOutput to merge

        Returns:
            New StandardToolOutput with merged data
        """
        merged_registry = {**self.registry_updates, **other.registry_updates}
        merged_summary = f"{self.summary_for_llm}\n{other.summary_for_llm}"
        merged_metadata = {**self.tool_metadata, **other.tool_metadata}

        # INTELLIPLANNER B+: Merge structured_data
        merged_structured: dict[str, Any] = {}
        for key, value in self.structured_data.items():
            if isinstance(value, list) and key in other.structured_data:
                # Merge lists
                other_value = other.structured_data[key]
                if isinstance(other_value, list):
                    merged_structured[key] = value + other_value
                else:
                    merged_structured[key] = value
            else:
                merged_structured[key] = value

        for key, value in other.structured_data.items():
            if key not in merged_structured:
                merged_structured[key] = value

        # Update count if present
        if (
            "count" in merged_structured
            or "count" in self.structured_data
            or "count" in other.structured_data
        ):
            total_count = sum(len(v) for v in merged_structured.values() if isinstance(v, list))
            merged_structured["count"] = total_count

        return StandardToolOutput(
            summary_for_llm=merged_summary,
            registry_updates=merged_registry,
            structured_data=merged_structured,
            tool_metadata=merged_metadata,
        )

    def __str__(self) -> str:
        """
        String representation for LangChain tool result conversion.

        LangChain converts tool results to string for ToolMessage content.
        This ensures only the summary (not full registry) goes to LLM context.

        Returns:
            summary_for_llm (compact text for LLM)
        """
        return self.summary_for_llm

    def __repr__(self) -> str:
        """
        Debug representation with registry info.

        Returns:
            Debug string with registry item count
        """
        return (
            f"StandardToolOutput(summary={self.summary_for_llm[:50]}..., "
            f"registry_items={len(self.registry_updates)}, "
            f"metadata={list(self.tool_metadata.keys())})"
        )

    def to_unified(self) -> "UnifiedToolOutput":
        """
        Convert to UnifiedToolOutput format.

        Enables gradual migration from StandardToolOutput to UnifiedToolOutput.

        Returns:
            UnifiedToolOutput with equivalent data
        """
        return UnifiedToolOutput(
            success=True,
            message=self.summary_for_llm,
            registry_updates=self.registry_updates,
            structured_data=self.structured_data,
            metadata=self.tool_metadata,
        )


# =============================================================================
# UnifiedToolOutput - New unified format for ALL tools (2025-12-29)
# =============================================================================


class UnifiedToolOutput(BaseModel):
    """
    Unified output format for ALL tools.

    This class unifies ToolResponse (schemas.py) and StandardToolOutput into a single
    format that handles all use cases:
    - Data queries with registry (contacts, emails, calendar, etc.)
    - Action confirmations without registry (reminders, send email, etc.)
    - Error responses

    Key improvements over StandardToolOutput:
    1. Explicit `success` field (was implicit in StandardToolOutput)
    2. Explicit `error` and `error_code` fields for error handling
    3. `message` field (clearer name than `summary_for_llm`)
    4. Factory methods for common patterns

    Attributes:
        success: Whether the tool execution succeeded (default True)
        message: Human-readable message for the LLM (required)
        registry_updates: Dict of RegistryItems for frontend rendering (optional)
        structured_data: Dict for Jinja2 templates (optional)
        error: Error message if success=False (optional)
        error_code: Error code for programmatic handling (optional)
        metadata: Debug/metrics information (optional)

    Examples:
        # Action confirmation (reminders, etc.)
        >>> output = UnifiedToolOutput.action_success(
        ...     message="🔔 Rappel créé pour demain à 10h",
        ...     structured_data={"reminder_id": "abc123"},
        ... )

        # Data query (contacts, emails, etc.)
        >>> output = UnifiedToolOutput.data_success(
        ...     message="Found 3 contacts",
        ...     registry_updates={"contact_1": RegistryItem(...)},
        ...     structured_data={"contacts": [...], "count": 3},
        ... )

        # Error (use failure() factory method)
        >>> output = UnifiedToolOutput.failure(
        ...     message="Contact not found",
        ...     error_code="NOT_FOUND",
        ... )
    """

    success: bool = Field(
        default=True,
        description="Whether the tool execution succeeded",
    )
    message: str = Field(
        ...,
        description="Human-readable message for the LLM (always required)",
    )
    registry_updates: dict[str, RegistryItem] = Field(
        default_factory=dict,
        description="Registry items keyed by ID (sent to frontend via SSE)",
    )
    structured_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured data for Jinja2 templates",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if success=False",
    )
    error_code: str | None = Field(
        default=None,
        description="Error code for programmatic handling (e.g., 'NOT_FOUND', 'VALIDATION_ERROR')",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata for debugging/observability",
    )

    # =========================================================================
    # Pydantic Validation
    # =========================================================================

    @model_validator(mode="after")
    def validate_error_code_required_on_failure(self) -> "UnifiedToolOutput":
        """Ensure error_code is provided when success=False."""
        if not self.success and not self.error_code:
            raise ValueError("error_code is required when success=False")
        return self

    # =========================================================================
    # Compatibility Properties (for parallel_executor and other code)
    # =========================================================================

    @property
    def summary_for_llm(self) -> str:
        """Alias for message - compatibility with StandardToolOutput."""
        return self.message

    @property
    def tool_metadata(self) -> dict[str, Any]:
        """Alias for metadata - compatibility with StandardToolOutput."""
        return self.metadata

    @property
    def error(self) -> str | None:
        """Alias for error_code - backward compatibility with tests using result.error."""
        return self.error_code

    # =========================================================================
    # Factory Methods
    # =========================================================================

    @classmethod
    def action_success(
        cls,
        message: str,
        structured_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "UnifiedToolOutput":
        """
        Create a success response for an action (no registry data).

        Use this for tools that perform actions but don't return queryable data:
        - Creating reminders
        - Sending emails (confirmation)
        - Deleting items (confirmation)

        Args:
            message: Success message for the user/LLM
            structured_data: Optional structured data (e.g., {"reminder_id": "abc123"})
            metadata: Optional debug metadata

        Returns:
            UnifiedToolOutput with success=True, empty registry

        Example:
            >>> output = UnifiedToolOutput.action_success(
            ...     message="🔔 Rappel créé pour demain à 10h",
            ...     structured_data={"reminder_id": "abc123", "trigger_at": "2025-12-30T10:00:00"},
            ... )
        """
        return cls(
            success=True,
            message=message,
            registry_updates={},
            structured_data=structured_data or {},
            metadata=metadata or {},
        )

    @classmethod
    def data_success(
        cls,
        message: str,
        registry_updates: dict[str, RegistryItem] | None = None,
        structured_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "UnifiedToolOutput":
        """
        Create a success response with registry data.

        Use this for tools that return queryable data:
        - Searching contacts
        - Listing emails
        - Fetching calendar events

        Args:
            message: Summary message for the LLM
            registry_updates: Dict of RegistryItems for frontend
            structured_data: Dict for Jinja2 templates
            metadata: Optional debug metadata

        Returns:
            UnifiedToolOutput with success=True and registry data

        Example:
            >>> output = UnifiedToolOutput.data_success(
            ...     message="Found 3 contacts: John, Jane, Bob",
            ...     registry_updates={"contact_1": RegistryItem(...)},
            ...     structured_data={"contacts": [...], "count": 3},
            ... )
        """
        return cls(
            success=True,
            message=message,
            registry_updates=registry_updates or {},
            structured_data=structured_data or {},
            metadata=metadata or {},
        )

    @classmethod
    def failure(
        cls,
        message: str,
        error_code: str,
        metadata: dict[str, Any] | None = None,
    ) -> "UnifiedToolOutput":
        """
        Create an error response.

        Use this when tool execution fails.

        Args:
            message: Human-readable error message
            error_code: Programmatic error code (required, e.g., 'NOT_FOUND', 'VALIDATION_ERROR')
            metadata: Optional debug metadata

        Returns:
            UnifiedToolOutput with success=False

        Example:
            >>> output = UnifiedToolOutput.failure(
            ...     message="Contact 'Jean' not found",
            ...     error_code="NOT_FOUND",
            ... )
        """
        return cls(
            success=False,
            message=message,
            error_message=message,
            error_code=error_code,
            metadata=metadata or {},
        )

    # =========================================================================
    # Conversion Methods
    # =========================================================================

    def to_standard(self) -> StandardToolOutput:
        """
        Convert to StandardToolOutput format.

        Enables backward compatibility with code expecting StandardToolOutput.

        Returns:
            StandardToolOutput with equivalent data

        Note:
            Error information is lost in conversion (StandardToolOutput has no error field).
            Use UnifiedToolOutput directly for proper error handling.
        """
        return StandardToolOutput(
            summary_for_llm=self.message,
            registry_updates=self.registry_updates,
            structured_data=self.structured_data,
            tool_metadata=self.metadata,
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_step_output(self) -> dict[str, Any]:
        """
        Get data structure for completed_steps (Jinja2 template access).

        Same logic as StandardToolOutput.get_step_output().

        Returns:
            Dict suitable for Jinja2 access
        """
        # Priority 1: Use explicit structured_data if populated
        if self.structured_data:
            return self.structured_data

        # Priority 2: Fallback - extract payloads from registry_updates grouped by type
        if self.registry_updates:
            result: dict[str, Any] = {}
            for item in self.registry_updates.values():
                type_key = REGISTRY_TYPE_TO_KEY.get(item.type, item.type.value.lower() + "s")
                if type_key not in result:
                    result[type_key] = []
                result[type_key].append(item.payload)

            result["count"] = sum(len(v) for v in result.values() if isinstance(v, list))
            return result

        # Priority 3: Ultimate fallback - just the message
        return {"message": self.message, "success": self.success, "count": 0}

    def to_llm_message(self) -> str:
        """
        Convert to the string that will be added to LLM messages.

        Returns:
            message field (human-readable text for LLM)
        """
        return self.message

    def get_registry_ids(self) -> list[str]:
        """
        Get list of all registry item IDs in this output.

        Returns:
            List of registry item IDs
        """
        return list(self.registry_updates.keys())

    def __str__(self) -> str:
        """
        String representation for LangChain tool result conversion.

        LangChain converts tool results to string for ToolMessage content.
        This ensures only the message (not full registry) goes to LLM context.

        Returns:
            message field (human-readable text for LLM)
        """
        return self.message

    def __repr__(self) -> str:
        """
        Debug representation.

        Returns:
            Debug string with key info
        """
        status = "✓" if self.success else "✗"
        return (
            f"UnifiedToolOutput({status} {self.message[:50]}..., "
            f"registry={len(self.registry_updates)}, "
            f"error_code={self.error_code})"
        )
