"""
LangChain v1 tools for Google Calendar operations.

LOT 9: Complete Calendar tools migration to Data Registry architecture.

Pattern:
    @connector_tool
    async def search_events_tool(
        query: str,
        runtime: ToolRuntime,
    ) -> UnifiedToolOutput:
        # Returns registry items for frontend rendering

    @connector_tool
    async def create_event_tool(
        summary: str,
        start_datetime: str,
        end_datetime: str,
        runtime: ToolRuntime,
    ) -> UnifiedToolOutput:
        # Creates draft → user confirms → event created

Data Registry Mode:
    - Read tools return UnifiedToolOutput with registry items
    - Write tools return UnifiedToolOutput with draft (HITL confirmation via drafts module)
    - Draft registry item contains event data
    - LIAToolNode routes to draft_critique node for HITL
    - User confirms/edits/cancels via HITL
    - On confirm, action is executed via GoogleCalendarClient

Migration (2025-12-30):
    Migrated from StandardToolOutput to UnifiedToolOutput.
    - All tool functions now return UnifiedToolOutput
    - Draft functions delegated to drafts module (to be migrated separately)
"""

import time
from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel

from src.core.config import get_settings, settings
from src.core.i18n_api_messages import APIMessages
from src.core.time_utils import normalize_to_rfc3339
from src.domains.agents.constants import (
    AGENT_EVENT,
    CONTEXT_DOMAIN_CALENDARS,
    CONTEXT_DOMAIN_EVENTS,
)
from src.domains.agents.context import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.context.decorators import auto_save_context
from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.exceptions import ToolValidationError
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import StandardToolOutput, UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    get_user_preferences,
    parse_user_id,
    resolve_recipients_to_emails,
    validate_runtime_config,
)
from src.domains.agents.tools.validation_helpers import (
    require_field,
    validate_positive_int_or_default,
)
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.resolver import resolve_calendar_name

logger = structlog.get_logger(__name__)

# ============================================================================
# GENERIC QUERY TERMS - DEFENSIVE FILTER
# ============================================================================
# These terms are CATEGORY words, not search filters.
# When the LLM generates query="appointment", it means "find my next events",
# NOT "filter events where title contains 'appointment'".
# This defensive filter catches cases where the LLM misinterprets generic queries.
GENERIC_CALENDAR_QUERY_TERMS = frozenset(
    {
        # English generic terms
        "appointment",
        "appointments",
        "meeting",
        "meetings",
        "event",
        "events",
        "calendar",
        "calendars",
        "schedule",
        "schedules",
        "upcoming",
        "next",
    }
)


# ============================================================================
# CONTEXT REGISTRATION
# ============================================================================


class EventItem(BaseModel):
    """
    Standardized event item schema for context manager.

    Used for reference resolution (e.g., "the 2nd event", "the meeting tomorrow").
    """

    id: str  # Google Calendar event ID
    summary: str  # Event title
    start_datetime: str = ""  # Start datetime
    end_datetime: str = ""  # End datetime
    location: str = ""  # Event location


# Register event context types for context manager
# This enables contextual references like "the 2nd event", "the meeting"
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_EVENTS,
        agent_name=AGENT_EVENT,
        item_schema=EventItem,
        primary_id_field="id",
        display_name_field="summary",
        reference_fields=[
            "summary",
            "location",
            "start_datetime",
        ],
        icon="📅",
    )
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================


class SearchEventsInput(BaseModel):
    """Input schema for search_events_tool."""

    query: str | None = None
    time_min: str | None = None
    time_max: str | None = None
    max_results: int = 10


class GetEventDetailsInput(BaseModel):
    """Input schema for get_event_details_tool."""

    event_id: str


class CreateEventInput(BaseModel):
    """Input schema for create_event_tool."""

    summary: str
    start_datetime: str
    end_datetime: str
    timezone: str | None = None  # If None, uses user's configured timezone
    description: str | None = None
    location: str | None = None
    attendees: list[str] | None = None


class UpdateEventInput(BaseModel):
    """Input schema for update_event_tool."""

    event_id: str
    summary: str | None = None
    start_datetime: str | None = None
    end_datetime: str | None = None
    timezone: str | None = None  # If None, uses user's configured timezone
    description: str | None = None
    location: str | None = None
    attendees: list[str] | None = None


class DeleteEventInput(BaseModel):
    """Input schema for delete_event_tool."""

    event_id: str
    send_updates: str = "all"


# ============================================================================
# TOOL 1: SEARCH EVENTS (Read Operation - Data Registry LOT 9)
# ============================================================================


class SearchEventsTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    """
    Search calendar events tool with Data Registry support.

    LOT 9: Read operations with registry items for frontend rendering.

    Benefits:
    - Returns rich event data for frontend cards
    - Supports time range filtering
    - Supports free text search query
    - Results cached and stored in context
    """

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"

    # Data Registry mode enabled - returns StandardToolOutput with registry items
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize search events tool with Data Registry support."""
        super().__init__(tool_name="get_events_tool", operation="search")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute search events API call - business logic only."""
        from src.core.constants import (
            GOOGLE_CALENDAR_DETAILS_FIELDS,
            GOOGLE_CALENDAR_REQUIRED_FIELDS,
        )
        from src.domains.connectors.preferences.service import ConnectorPreferencesService
        from src.domains.connectors.repository import ConnectorRepository

        query: str | None = kwargs.get("query")

        # =========================================================================
        # DEFENSIVE FILTER: Ignore generic category terms
        # =========================================================================
        # If LLM generates query="appointment" or "rdv", it means "find my next events"
        # NOT "filter events where title contains 'appointment'"
        # This catches cases where smart_planner misinterprets generic queries
        if query and query.strip().lower() in GENERIC_CALENDAR_QUERY_TERMS:
            logger.info(
                "calendar_search_generic_query_ignored",
                original_query=query,
                reason="generic_category_term_not_filter",
            )
            query = None

        # =========================================================================
        # PERSON NAME RESOLUTION: Resolve person names to email for attendee search
        # =========================================================================
        # If query looks like a person name (not an email), resolve to email via contacts.
        # Google Calendar API searches attendees by email, so "John Smith" won't match
        # unless we convert it to "matheo@example.com" first.
        if query and "@" not in query:
            from src.core.validators import validate_email

            # Check if it's NOT already an email
            # validate_email returns bool, doesn't raise exception
            is_email = validate_email(query.strip())

            if not is_email:
                resolved = await resolve_recipients_to_emails(
                    self.runtime, query, "calendar_search"
                )
                if resolved and resolved != query:
                    # Extract email from RFC 5322 format "Name <email>" if present
                    import re

                    email_match = re.search(r"<([^>]+)>", resolved)
                    resolved_email = email_match.group(1) if email_match else resolved
                    logger.info(
                        "calendar_search_person_resolved_to_email",
                        original_query=query,
                        resolved_email=resolved_email,
                    )
                    query = resolved_email

        time_min: str | None = kwargs.get("time_min")
        time_max: str | None = kwargs.get("time_max")
        fields: list[str] | None = kwargs.get("fields")
        settings = get_settings()
        raw_max_results = kwargs.get("max_results")
        default_max_results = settings.calendar_tool_default_max_results
        max_results = validate_positive_int_or_default(raw_max_results, default=default_max_results)
        # Cap at domain-specific limit (CALENDAR_TOOL_DEFAULT_MAX_RESULTS)
        security_cap = settings.calendar_tool_default_max_results
        if max_results > security_cap:
            logger.warning(
                "calendar_search_limit_capped",
                requested_max_results=raw_max_results,
                capped_max_results=security_cap,
                default_max_results=default_max_results,
            )
            max_results = security_cap
        calendar_id_input: str | None = kwargs.get("calendar_id")

        # Apply default fields and ensure required fields are always included
        # Architecture v2.0: Always return full details (unified tool)
        fields_to_use = fields if fields else GOOGLE_CALENDAR_DETAILS_FIELDS
        for required_field in GOOGLE_CALENDAR_REQUIRED_FIELDS:
            if required_field not in fields_to_use:
                fields_to_use = [required_field] + list(fields_to_use)

        # CRITICAL FIX: Always default time_min to NOW if not specified
        # This prevents returning past events from 2017!
        # The Google Calendar API returns ALL events if no timeMin is set.
        if not time_min:
            now = datetime.utcnow()
            time_min = now.isoformat() + "Z"
            logger.debug(
                "calendar_search_defaulting_time_min",
                time_min=time_min,
                reason="no_time_min_specified",
            )
        else:
            # Normalize time_min to ensure it has timezone suffix (RFC3339)
            # LLM may output bare ISO datetime without timezone
            time_min = normalize_to_rfc3339(time_min)

        # Default time_max to 30 days from now if searching future events
        if not time_max:
            now = datetime.utcnow()
            time_max = (now + timedelta(days=30)).isoformat() + "Z"
        else:
            # Normalize time_max to ensure it has timezone suffix (RFC3339)
            time_max = normalize_to_rfc3339(time_max)

        # Resolve default calendar from user preferences if not explicitly specified
        if not calendar_id_input or calendar_id_input == "primary":
            try:
                repo = ConnectorRepository(client.connector_service.db)
                connector = await repo.get_by_user_and_type(user_id, client.connector_type)
                if connector and connector.preferences_encrypted:
                    default_name = ConnectorPreferencesService.get_preference_value(
                        client.connector_type.value,
                        connector.preferences_encrypted,
                        "default_calendar_name",
                    )
                    if default_name:
                        calendar_id_input = default_name
                        logger.debug(
                            "calendar_search_using_default_preference",
                            default_calendar_name=default_name,
                            user_id=str(user_id),
                        )
            except (ValueError, KeyError, AttributeError, TypeError) as e:
                logger.warning("calendar_preference_resolution_failed", error=str(e))

        # Resolve calendar name to ID (case-insensitive)
        # "famille" -> ID of "Famille" calendar
        # "primary" stays "primary"
        calendar_id = await resolve_calendar_name(
            client=client,
            name=calendar_id_input or "primary",
            fallback="primary",
        )

        logger.debug(
            "calendar_id_resolved",
            input=calendar_id_input,
            resolved=calendar_id,
        )

        # Execute API call with field projection
        result = await client.list_events(
            query=query,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            calendar_id=calendar_id,
            fields=fields_to_use,
        )

        events = result.get("items", [])

        logger.info(
            "search_events_success",
            user_id=str(user_id),
            query=query,
            time_min=time_min,
            time_max=time_max,
            calendar_id=calendar_id,
            total_results=len(events),
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "events": events,
            "query": query,
            "time_min": time_min,
            "time_max": time_max,
            "calendar_id": calendar_id,
            "from_cache": False,
            "user_timezone": user_timezone,
            "locale": locale,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with registry items.

        Uses ToolOutputMixin.build_events_output() to create:
        - message: Compact text with event titles and times
        - registry_updates: Full event data for frontend rendering
        - metadata: Query info, time range, etc.

        TIMEZONE: Dates are converted to user's timezone before storage.
        CALENDAR_ID: Added to each event for update/delete operations.
        """
        events = result.get("events", [])
        query = result.get("query")
        time_min = result.get("time_min")
        time_max = result.get("time_max")
        from_cache = result.get("from_cache", False)
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)
        calendar_id = result.get("calendar_id")  # Pass calendar_id for update/delete

        return self.build_events_output(
            events=events,
            query=query,
            time_min=time_min,
            time_max=time_max,
            from_cache=from_cache,
            user_timezone=user_timezone,
            locale=locale,
            calendar_id=calendar_id,
        )


# Create tool instance (singleton)
_search_events_tool_instance = SearchEventsTool()


@connector_tool(
    name="search_events",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    category="read",
)
@auto_save_context("events")
async def search_events_tool(
    query: Annotated[
        str | None, "Free text search query for event titles/descriptions (optional)"
    ] = None,
    time_min: Annotated[
        str | None,
        "Start of time range in ISO format with timezone, e.g. '2025-01-15T00:00:00Z' (optional, defaults to NOW)",
    ] = None,
    time_max: Annotated[
        str | None,
        "End of time range in ISO format with timezone, e.g. '2025-01-31T23:59:59Z' (optional, defaults to +30 days)",
    ] = None,
    max_results: Annotated[
        int | None, "Maximum number of events to return (defaults to settings, max 100)"
    ] = None,
    calendar_id: Annotated[
        str,
        "Calendar ID to search. Use 'primary' for main calendar, or calendar ID/name for specific calendars (e.g., 'famille', 'work')",
    ] = "primary",
    fields: Annotated[
        list[str] | None,
        "List of event fields to return for optimization (optional). Example: ['summary', 'start', 'end', 'location']. If omitted, returns default search fields.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Search calendar events in Google Calendar.

    IMPORTANT: By default, only returns FUTURE events (from now onwards).
    Past events are never returned unless explicitly requesting a past time range.

    Supports filtering by:
    - Free text query (matches event title, description)
    - Time range (time_min, time_max)
    - Specific calendar (calendar_id)

    **Time Format:** ISO 8601 with timezone (e.g., '2025-01-15T10:00:00Z' or '2025-01-15T10:00:00+01:00')

    **Calendar Selection:**
    - "primary" = User's main calendar (default)
    - Calendar name (e.g., "famille", "work") = Specific calendar by name
    - Full calendar ID (e.g., "abc123@group.calendar.google.com")

    **Field Projection (optimization):**
    - If fields is specified, only those fields are returned (reduces latency and tokens)
    - "summary" is always included to ensure event titles are displayed
    - Available fields: id, summary, start, end, location, attendees, organizer, description, etc.

    **Examples:**
    - Next 3 events: max_results=3 (time_min defaults to NOW)
    - Search by text: query="meeting"
    - Specific calendar: calendar_id="famille", max_results=3
    - Search by date range: time_min="2025-01-01T00:00:00Z", time_max="2025-01-31T23:59:59Z"
    - Optimized search: fields=["summary", "start", "end"]

    Args:
        query: Free text search query (optional)
        time_min: Start of time range in ISO format (optional, defaults to NOW)
        time_max: End of time range in ISO format (optional, defaults to +30 days)
        max_results: Maximum number of events (default 10, max 100)
        calendar_id: Calendar ID or name (default: "primary")
        fields: List of fields to return (optional, for optimization)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with EVENT registry items for frontend rendering
    """
    # Delegate to tool instance
    result = await _search_events_tool_instance.execute(
        runtime=runtime,
        query=query,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        calendar_id=calendar_id,
        fields=fields,
    )

    # Save to context for reference resolution
    if runtime.store:
        try:
            user_id_raw = runtime.config.get("configurable", {}).get("user_id")
            thread_id = runtime.config.get("configurable", {}).get("thread_id")

            if user_id_raw and thread_id:
                user_id = parse_user_id(user_id_raw)
                thread_id_str = str(thread_id)

                # Extract events from registry
                events = []
                if isinstance(result, StandardToolOutput | UnifiedToolOutput):
                    for item in result.registry_updates.values():
                        events.append(item.payload)

                await runtime.store.aput(
                    (str(user_id), thread_id_str, "context", "events"),
                    "list_current_search",
                    {
                        "events": events,
                        "query": query,
                        "time_min": time_min,
                        "time_max": time_max,
                        "timestamp": time.time(),
                    },
                )
        except (RuntimeError, ValueError, OSError):
            pass  # Context save is non-critical

    return result


# ============================================================================
# TOOL 2: GET EVENT DETAILS (Read Operation - Data Registry LOT 9)
# ============================================================================


class GetEventDetailsTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    """
    Get event details tool with Data Registry support.

    LOT 9: Read operation returning full event data for frontend rendering.

    MULTI-ORDINAL FIX (2026-01-01): Supports batch mode for multi-reference queries.
    - Single mode: event_id="abc123" → fetch one event
    - Batch mode: event_ids=["abc123", "def456"] → fetch multiple events in parallel
    """

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"

    # Data Registry mode enabled
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize get event details tool with Data Registry support."""
        super().__init__(tool_name="get_events_tool", operation="details")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute get event details API call.

        MULTI-ORDINAL FIX (2026-01-01): Routes to single or batch mode based on parameters.
        - If event_ids is provided (non-empty list) → batch mode
        - If event_id is provided → single mode
        - Both provided → batch mode takes precedence
        """
        event_id: str | None = kwargs.get("event_id")
        event_ids: list[str] | None = kwargs.get("event_ids")
        fields: list[str] | None = kwargs.get("fields")

        # Determine mode: batch takes precedence
        if event_ids and len(event_ids) > 0:
            return await self._execute_batch(client, user_id, event_ids, fields)
        elif event_id:
            return await self._execute_single(client, user_id, event_id, fields)
        else:
            raise ValueError("Either event_id or event_ids must be provided")

    async def _execute_single(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        event_id: str,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """Execute single event details fetch."""
        from src.core.constants import (
            GOOGLE_CALENDAR_DETAILS_FIELDS,
            GOOGLE_CALENDAR_REQUIRED_FIELDS,
        )
        from src.domains.connectors.preferences.resolver import resolve_calendar_name
        from src.domains.connectors.preferences.service import ConnectorPreferencesService
        from src.domains.connectors.repository import ConnectorRepository

        # Apply default fields and ensure required fields are always included
        # IMPORTANT: Always include "summary" to ensure event titles are displayed
        fields_to_use = fields if fields else GOOGLE_CALENDAR_DETAILS_FIELDS
        for required_field in GOOGLE_CALENDAR_REQUIRED_FIELDS:
            if required_field not in fields_to_use:
                fields_to_use = [required_field] + list(fields_to_use)

        # Resolve default calendar from user preferences
        calendar_id = "primary"
        try:
            repo = ConnectorRepository(client.connector_service.db)
            connector = await repo.get_by_user_and_type(user_id, client.connector_type)
            if connector and connector.preferences_encrypted:
                default_name = ConnectorPreferencesService.get_preference_value(
                    client.connector_type.value,
                    connector.preferences_encrypted,
                    "default_calendar_name",
                )
                if default_name:
                    calendar_id = await resolve_calendar_name(
                        client, default_name, fallback="primary"
                    )
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            logger.warning("calendar_preference_resolution_failed", error=str(e))

        result = await client.get_event(
            event_id=event_id, calendar_id=calendar_id, fields=fields_to_use
        )

        logger.info(
            "get_event_details_success",
            user_id=str(user_id),
            event_id=event_id,
            calendar_id=calendar_id,
            summary=result.get("summary", ""),
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "event": result,
            "event_id": event_id,
            "from_cache": False,
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "single",
        }

    async def _execute_batch(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        event_ids: list[str],
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """Execute batch event details fetch using asyncio.gather for parallelism.

        MULTI-ORDINAL FIX (2026-01-01): Added for multi-reference queries.
        """
        import asyncio

        from src.core.constants import (
            GOOGLE_CALENDAR_DETAILS_FIELDS,
            GOOGLE_CALENDAR_REQUIRED_FIELDS,
        )
        from src.domains.connectors.preferences.resolver import resolve_calendar_name
        from src.domains.connectors.preferences.service import ConnectorPreferencesService
        from src.domains.connectors.repository import ConnectorRepository

        # Apply default fields
        fields_to_use = fields if fields else GOOGLE_CALENDAR_DETAILS_FIELDS
        for required_field in GOOGLE_CALENDAR_REQUIRED_FIELDS:
            if required_field not in fields_to_use:
                fields_to_use = [required_field] + list(fields_to_use)

        # Resolve default calendar from user preferences
        calendar_id = "primary"
        try:
            repo = ConnectorRepository(client.connector_service.db)
            connector = await repo.get_by_user_and_type(user_id, client.connector_type)
            if connector and connector.preferences_encrypted:
                default_name = ConnectorPreferencesService.get_preference_value(
                    client.connector_type.value,
                    connector.preferences_encrypted,
                    "default_calendar_name",
                )
                if default_name:
                    calendar_id = await resolve_calendar_name(
                        client, default_name, fallback="primary"
                    )
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            logger.warning("calendar_preference_resolution_failed", error=str(e))

        # Fetch all events in parallel
        async def fetch_single(eid: str) -> tuple[str, dict[str, Any] | None, str | None]:
            """Fetch single event, return (event_id, event_data, error)."""
            try:
                result = await client.get_event(
                    event_id=eid, calendar_id=calendar_id, fields=fields_to_use
                )
                return (eid, result, None)
            except (ValueError, KeyError, RuntimeError, OSError) as e:
                logger.warning("get_event_details_batch_item_failed", event_id=eid, error=str(e))
                return (eid, None, str(e))

        results = await asyncio.gather(*[fetch_single(eid) for eid in event_ids])

        # Collect successful events and errors
        events: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for eid, event_data, error in results:
            if event_data:
                events.append(event_data)
            if error:
                errors.append({"event_id": eid, "error": error})

        logger.info(
            "get_event_details_batch_success",
            user_id=str(user_id),
            requested_count=len(event_ids),
            success_count=len(events),
            error_count=len(errors),
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "events": events,
            "event_ids": event_ids,
            "from_cache": False,
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "batch",
            "errors": errors if errors else None,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format as Data Registry UnifiedToolOutput with event registry items.

        TIMEZONE: Dates are converted to user's timezone before storage.

        MULTI-ORDINAL FIX (2026-01-01): Handles both single and batch modes.
        - Single mode: One event in registry with full details
        - Batch mode: Multiple events in registry, errors in metadata
        """
        mode = result.get("mode", "single")
        from_cache = result.get("from_cache", False)
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)

        # Handle single vs batch mode
        errors = None
        if mode == "batch":
            events = result.get("events", [])
            event_ids = result.get("event_ids", [])
            errors = result.get("errors")
        else:
            event = result.get("event", {})
            events = [event] if event else []
            event_ids = [result.get("event_id", "")]

        output = self.build_events_output(
            events=events,
            query=None,
            from_cache=from_cache,
            user_timezone=user_timezone,
            locale=locale,
        )

        # Build enhanced message based on mode
        if mode == "batch" and events:
            # Batch summary
            summary_lines = [f"Event details retrieved: {len(events)} event(s)"]
            for i, evt in enumerate(events[:5], 1):  # Limit to 5 for summary
                summary = evt.get("summary", "Sans titre")
                start = evt.get("start", {})
                start_dt = start.get("dateTime") or start.get("date", "")
                summary_lines.append(f'{i}. "{summary}" - {start_dt}')
            if len(events) > 5:
                summary_lines.append(f"... and {len(events) - 5} more")
            enhanced_message = "\n".join(summary_lines)

            # Add batch metadata
            output.metadata["event_ids"] = event_ids
            output.metadata["mode"] = "batch"
            if errors:
                output.metadata["errors"] = errors
        elif events:
            # Single event summary
            event = events[0]
            summary = event.get("summary", "Sans titre")
            start = event.get("start", {})
            start_dt = start.get("dateTime") or start.get("date", "")
            location = event.get("location", "")
            description = event.get("description", "")

            detail_parts = [f'Event details: "{summary}"']
            if start_dt:
                detail_parts.append(f"Start: {start_dt}")
            if location:
                detail_parts.append(f"Location: {location}")
            if description:
                detail_parts.append(f"Description: {description[:100]}...")

            enhanced_message = "\n".join(detail_parts)
            output.metadata["event_id"] = result.get("event_id")
            output.metadata["mode"] = "single"
        else:
            enhanced_message = output.message

        # Return new output with enhanced message
        return UnifiedToolOutput.data_success(
            message=enhanced_message,
            registry_updates=output.registry_updates,
            structured_data=output.structured_data,
            metadata=output.metadata,
        )


# Create tool instance (singleton)
_get_event_details_tool_instance = GetEventDetailsTool()


@connector_tool(
    name="get_event_details",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    category="read",
)
@auto_save_context("events")
async def get_event_details_tool(
    event_id: Annotated[str | None, "Google Calendar event ID to retrieve (single mode)"] = None,
    event_ids: Annotated[
        list[str] | None,
        "List of Google Calendar event IDs to retrieve (batch mode for multi-ordinal queries)",
    ] = None,
    fields: Annotated[
        list[str] | None,
        "List of event fields to return for optimization (optional). If omitted, returns all detail fields.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get detailed information for one or more calendar events.

    Supports both single and batch modes:
    - Single: event_id="abc123" → fetch one event
    - Batch: event_ids=["abc123", "def456"] → fetch multiple events in parallel

    MULTI-ORDINAL FIX (2026-01-01): Added batch mode for multi-reference queries.
    Example: "detail du 1 et du 2" → event_ids=["id1", "id2"]

    Returns complete event data including:
    - Title (summary)
    - Start/End datetime
    - Description
    - Location
    - Attendees
    - Organizer
    - Conference link (if any)

    **Field Projection (optimization):**
    - If fields is specified, only those fields are returned (reduces latency and tokens)
    - "summary" is always included to ensure event title is displayed

    Use this after search_events_tool to get full details of specific events.

    Args:
        event_id: Google Calendar event ID for single mode (from search_events_tool results)
        event_ids: List of Google Calendar event IDs for batch mode
        fields: List of fields to return (optional, for optimization)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with EVENT registry items containing full event data
    """
    result = await _get_event_details_tool_instance.execute(
        runtime=runtime,
        event_id=event_id,
        event_ids=event_ids,
        fields=fields,
    )

    # Save to context
    # MULTI-ORDINAL FIX (2026-01-01): Support batch mode context saving
    if runtime.store:
        try:
            user_id_raw = runtime.config.get("configurable", {}).get("user_id")
            thread_id = runtime.config.get("configurable", {}).get("thread_id")

            if user_id_raw and thread_id:
                user_id = parse_user_id(user_id_raw)
                thread_id_str = str(thread_id)

                # Determine mode and extract events
                is_batch_mode = event_ids is not None and len(event_ids) > 0
                events_to_save: list[tuple[str, dict]] = []  # List of (evt_id, event_data)

                if isinstance(result, StandardToolOutput | UnifiedToolOutput):
                    for item in result.registry_updates.values():
                        event_data = item.payload
                        evt_id = event_data.get("id", "")
                        if evt_id:
                            events_to_save.append((evt_id, event_data))
                        if not is_batch_mode:
                            break  # Single mode: only one event

                # Save each event to context
                for evt_id, event_data in events_to_save:
                    await runtime.store.aput(
                        (str(user_id), thread_id_str, "context", "events"),
                        f"item_{evt_id}",
                        {
                            "id": evt_id,
                            # Keep lightweight fields for quick lookups
                            "summary": event_data.get("summary", ""),
                            "start": event_data.get("start", {}),
                            "end": event_data.get("end", {}),
                            # Store full payload to align with contacts-style context (redis + pg sync)
                            "event": event_data,
                            "timestamp": time.time(),
                        },
                    )
        except (RuntimeError, ValueError, OSError):
            pass  # Context save is non-critical

    return result


# ============================================================================
# TOOL 3: CREATE EVENT (Write Operation - Draft/HITL - LOT 9)
# ============================================================================


class CreateEventDraftTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    """
    Create calendar event tool with Draft/HITL integration.

    LOT 9: Write operations with confirmation flow.

    This tool creates a DRAFT that requires user confirmation before creating.
    The event is NOT created until the user confirms via HITL.

    Flow:
    1. Tool creates draft → StandardToolOutput with requires_confirmation=True
    2. LIAToolNode detects requires_confirmation → sets pending_draft_critique
    3. Graph routes to draft_critique node
    4. User confirms/edits/cancels via HITL
    5. On confirm: execute_fn creates the event

    Benefits:
    - User can review event data before creating
    - User can edit title/time/attendees before confirming
    - Prevents accidental event creation
    - Audit trail of drafts and confirmations
    """

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"

    # Data Registry mode enabled - creates draft for HITL confirmation
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize create event draft tool."""
        super().__init__(tool_name="create_event_tool", operation="create_draft")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare event draft data (no API call yet).

        The actual creation happens after user confirms via HITL.
        This method only validates and prepares the data.
        """
        summary: str = require_field(kwargs, "summary")
        start_datetime: str = require_field(kwargs, "start_datetime")
        end_datetime: str = require_field(kwargs, "end_datetime")
        timezone: str | None = kwargs.get("timezone")
        calendar_id: str | None = kwargs.get("calendar_id")
        description: str | None = kwargs.get("description")
        location: str | None = kwargs.get("location")
        attendees_raw: list[str] | None = kwargs.get("attendees")

        # Resolve attendee names to email addresses via centralized helper
        # "Jane Smith" → "jane.smith@example.com" via Google People API
        attendees = await resolve_recipients_to_emails(self.runtime, attendees_raw, "attendees")
        # Ensure we have a list (helper returns list for list input, or None if empty)
        attendees = attendees if isinstance(attendees, list) else []

        # If no timezone specified, use user's configured timezone
        if not timezone:
            try:
                user_timezone, _, _ = await get_user_preferences(self.runtime)
                timezone = user_timezone
            except (ValueError, KeyError, AttributeError):
                timezone = "UTC"

        logger.info(
            "create_event_draft_prepared",
            user_id=str(user_id),
            summary=summary,
            start_datetime=start_datetime,
            timezone=timezone,
            calendar_id=calendar_id,
            has_attendees=attendees is not None and len(attendees) > 0,
        )

        return {
            "summary": summary,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "timezone": timezone,
            "calendar_id": calendar_id,
            "description": description,
            "location": location,
            "attendees": attendees or [],
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Create event draft via DraftService."""
        from src.domains.agents.drafts import create_event_draft

        return create_event_draft(
            summary=result["summary"],
            start_datetime=result["start_datetime"],
            end_datetime=result["end_datetime"],
            timezone=result.get("timezone", "Europe/Paris"),
            calendar_id=result.get("calendar_id"),
            description=result.get("description"),
            location=result.get("location"),
            attendees=result.get("attendees", []),
            source_tool="create_event_tool",
            user_language=self.get_user_language(),
        )


# Create tool instance (singleton)
_create_event_draft_tool_instance = CreateEventDraftTool()


@connector_tool(
    name="create_event",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    category="write",
)
async def create_event_tool(
    summary: Annotated[str, "Event title/summary (required)"],
    start_datetime: Annotated[
        str, "Start datetime in ISO format, e.g. '2025-01-15T10:00:00' (required)"
    ],
    end_datetime: Annotated[
        str, "End datetime in ISO format, e.g. '2025-01-15T11:00:00' (required)"
    ],
    timezone: Annotated[
        str | None, "Timezone (optional, uses user's configured timezone if not specified)"
    ] = None,
    calendar_id: Annotated[
        str | None,
        "Calendar where the event will be created. If None or 'primary', uses user's default calendar preference.",
    ] = None,
    description: Annotated[str | None, "Event description (optional)"] = None,
    location: Annotated[str | None, "Event location (optional)"] = None,
    attendees: Annotated[list[str] | None, "List of attendee emails (optional)"] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Create a calendar event in Google Calendar (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The event is NOT created until the user confirms via HITL.

    Flow:
    1. Tool creates draft with event data
    2. User sees preview and can confirm/edit/cancel
    3. On confirm, event is actually created

    Args:
        summary: Event title/summary (required)
        start_datetime: Start datetime in ISO format (required)
        end_datetime: End datetime in ISO format (required)
        timezone: Timezone (default: Europe/Paris)
        calendar_id: Calendar ID. If None or 'primary', uses user's default calendar preference.
        description: Event description (optional)
        location: Event location (optional)
        attendees: List of attendee email addresses (optional)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item (requires user confirmation)

    Example response summary:
        "Brouillon créé: Événement 'Team Meeting' le 15/01/2025 [draft_abc123]
         Action requise: confirmez, modifiez ou annulez."
    """
    return await _create_event_draft_tool_instance.execute(
        runtime=runtime,
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        timezone=timezone,
        calendar_id=calendar_id,
        description=description,
        location=location,
        attendees=attendees,
    )


# ============================================================================
# TOOL 4: UPDATE EVENT (Write Operation - Draft/HITL - LOT 9)
# ============================================================================


class UpdateEventDraftTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    """
    Update calendar event tool with Draft/HITL integration.

    LOT 9: Write operations with confirmation flow.

    This tool creates an UPDATE DRAFT that requires user confirmation.
    The event is NOT updated until the user confirms via HITL.
    """

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"

    # Data Registry mode enabled - creates draft for HITL confirmation
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize update event draft tool."""
        super().__init__(tool_name="update_event_tool", operation="update_draft")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare event update draft data.

        Fetches current event to show comparison in draft.
        The actual update happens after user confirms via HITL.
        """
        event_id: str = require_field(kwargs, "event_id")
        summary: str | None = kwargs.get("summary")
        start_datetime: str | None = kwargs.get("start_datetime")
        end_datetime: str | None = kwargs.get("end_datetime")
        timezone: str | None = kwargs.get("timezone")
        calendar_id: str | None = kwargs.get("calendar_id")
        description: str | None = kwargs.get("description")
        location: str | None = kwargs.get("location")
        attendees_raw: list[str] | None = kwargs.get("attendees")

        # Resolve attendee names to email addresses via centralized helper
        # "Jane Smith" → "jane.smith@example.com" via Google People API
        attendees = (
            await resolve_recipients_to_emails(self.runtime, attendees_raw, "attendees")
            if attendees_raw
            else None
        )

        # If no timezone specified, use user's configured timezone
        if not timezone:
            try:
                user_timezone, _, _ = await get_user_preferences(self.runtime)
                timezone = user_timezone
            except (ValueError, KeyError, AttributeError):
                timezone = "UTC"

        # If no calendar_id provided, try to look it up from context store
        # This handles cases where the planner forgets to pass calendar_id
        if not calendar_id and self.runtime:
            config = validate_runtime_config(self.runtime, "update_event_tool")
            if not isinstance(config, UnifiedToolOutput):
                manager = ToolContextManager()
                context_list = await manager.get_list(
                    user_id=config.user_id,
                    session_id=config.session_id,
                    domain=CONTEXT_DOMAIN_EVENTS,
                    store=config.store,
                )
                if context_list and context_list.items:
                    # Search for the event by ID in context
                    for item in context_list.items:
                        item_id = item.get("id") or item.get("event_id")
                        if item_id == event_id:
                            calendar_id = item.get("calendar_id")
                            logger.info(
                                "calendar_id_resolved_from_context",
                                event_id=event_id,
                                calendar_id=calendar_id,
                            )
                            break

        # Fetch current event for comparison (use resolved calendar_id or default to "primary")
        current_event = await client.get_event(
            event_id=event_id,
            calendar_id=calendar_id or "primary",
        )

        logger.info(
            "update_event_draft_prepared",
            user_id=str(user_id),
            event_id=event_id,
            timezone=timezone,
            calendar_id=calendar_id,
            summary=summary or current_event.get("summary"),
        )

        return {
            "event_id": event_id,
            "summary": summary,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "timezone": timezone,
            "calendar_id": calendar_id,
            "description": description,
            "location": location,
            "attendees": attendees,
            "current_event": current_event,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Create update event draft via DraftService."""
        from src.domains.agents.drafts import create_update_event_draft

        return create_update_event_draft(
            event_id=result["event_id"],
            summary=result.get("summary"),
            start_datetime=result.get("start_datetime"),
            end_datetime=result.get("end_datetime"),
            timezone=result.get("timezone", "Europe/Paris"),
            calendar_id=result.get("calendar_id"),
            description=result.get("description"),
            location=result.get("location"),
            attendees=result.get("attendees"),
            current_event=result.get("current_event", {}),
            source_tool="update_event_tool",
            user_language=self.get_user_language(),
        )


# Create tool instance (singleton)
_update_event_draft_tool_instance = UpdateEventDraftTool()


@connector_tool(
    name="update_event",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    category="write",
)
async def update_event_tool(
    event_id: Annotated[str, "Google Calendar event ID to update (required)"],
    summary: Annotated[str | None, "New event title/summary (optional)"] = None,
    start_datetime: Annotated[str | None, "New start datetime in ISO format (optional)"] = None,
    end_datetime: Annotated[str | None, "New end datetime in ISO format (optional)"] = None,
    timezone: Annotated[
        str | None, "Timezone (optional, uses user's configured timezone if not specified)"
    ] = None,
    calendar_id: Annotated[
        str | None,
        "Calendar where the event is located. If None or 'primary', uses user's default calendar preference.",
    ] = None,
    description: Annotated[str | None, "New event description (optional)"] = None,
    location: Annotated[str | None, "New event location (optional)"] = None,
    attendees: Annotated[list[str] | None, "New list of attendee emails (optional)"] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Update an existing calendar event in Google Calendar (with user confirmation).

    IMPORTANT: This tool creates an UPDATE DRAFT that requires user confirmation.
    The event is NOT updated until the user confirms via HITL.

    Only provided fields are updated. Omitted fields keep their existing values.

    Flow:
    1. Tool creates update draft with changes
    2. User sees current vs new comparison and can confirm/edit/cancel
    3. On confirm, event is actually updated

    Args:
        event_id: Google Calendar event ID to update (required)
        summary: New event title/summary (optional)
        start_datetime: New start datetime in ISO format (optional)
        end_datetime: New end datetime in ISO format (optional)
        timezone: Timezone for datetime fields (default: Europe/Paris)
        calendar_id: Calendar ID. If None or 'primary', uses user's default calendar preference.
        description: New event description (optional)
        location: New event location (optional)
        attendees: New list of attendee email addresses (optional)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with UPDATE_DRAFT registry item (requires user confirmation)
    """
    return await _update_event_draft_tool_instance.execute(
        runtime=runtime,
        event_id=event_id,
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        timezone=timezone,
        calendar_id=calendar_id,
        description=description,
        location=location,
        attendees=attendees,
    )


# ============================================================================
# TOOL 5: DELETE EVENT (Write Operation - HITL Confirmation - LOT 9)
# ============================================================================


class DeleteEventDraftTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    """
    Delete calendar event tool with HITL confirmation.

    LOT 9: Destructive operations require explicit user confirmation.

    This tool creates a DELETE DRAFT that requires user confirmation.
    The event is NOT deleted until the user confirms via HITL.
    """

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"

    # Data Registry mode enabled - creates draft for HITL confirmation
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize delete event draft tool."""
        super().__init__(tool_name="delete_event_tool", operation="delete_draft")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare event deletion draft.

        Fetches event details to show what will be deleted.
        The actual deletion happens after user confirms via HITL.
        """
        event_id: str = require_field(kwargs, "event_id")
        send_updates: str = kwargs.get("send_updates", "all")
        calendar_id: str | None = kwargs.get("calendar_id")

        # If no calendar_id provided, try to look it up from context store
        # This handles cases where the planner forgets to pass calendar_id
        if not calendar_id and self.runtime:
            config = validate_runtime_config(self.runtime, "delete_event_tool")
            if not isinstance(config, UnifiedToolOutput):
                manager = ToolContextManager()
                context_list = await manager.get_list(
                    user_id=config.user_id,
                    session_id=config.session_id,
                    domain=CONTEXT_DOMAIN_EVENTS,
                    store=config.store,
                )
                if context_list and context_list.items:
                    # Search for the event by ID in context
                    for item in context_list.items:
                        item_id = item.get("id") or item.get("event_id")
                        if item_id == event_id:
                            calendar_id = item.get("calendar_id")
                            logger.info(
                                "calendar_id_resolved_from_context",
                                event_id=event_id,
                                calendar_id=calendar_id,
                            )
                            break

        # Fetch event details for confirmation display (use resolved calendar_id or default to "primary")
        event = await client.get_event(
            event_id=event_id,
            calendar_id=calendar_id or "primary",
        )

        logger.info(
            "delete_event_draft_prepared",
            user_id=str(user_id),
            event_id=event_id,
            calendar_id=calendar_id,
            summary=event.get("summary"),
        )

        return {
            "event_id": event_id,
            "event": event,
            "send_updates": send_updates,
            "calendar_id": calendar_id,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Create delete event draft via DraftService."""
        from src.domains.agents.drafts import create_delete_event_draft

        return create_delete_event_draft(
            event_id=result["event_id"],
            event=result["event"],
            send_updates=result.get("send_updates", "all"),
            calendar_id=result.get("calendar_id"),
            source_tool="delete_event_tool",
            user_language=self.get_user_language(),
        )


# Create tool instance (singleton)
_delete_event_draft_tool_instance = DeleteEventDraftTool()


@connector_tool(
    name="delete_event",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    category="write",
)
async def delete_event_tool(
    event_id: Annotated[str, "Google Calendar event ID to delete (required)"],
    send_updates: Annotated[
        str,
        "How to notify attendees: 'all' (default), 'externalOnly', or 'none'",
    ] = "all",
    calendar_id: Annotated[
        str | None,
        "Calendar where the event is located. If None or 'primary', uses user's default calendar preference.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Delete a calendar event from Google Calendar (with user confirmation).

    IMPORTANT: This tool creates a DELETE DRAFT that requires user confirmation.
    The event is NOT deleted until the user confirms via HITL.

    This is a DESTRUCTIVE operation - the event will be permanently deleted.

    Flow:
    1. Tool creates delete draft showing event to be deleted
    2. User sees event details and can confirm/cancel
    3. On confirm, event is actually deleted

    Args:
        event_id: Google Calendar event ID to delete (required)
        send_updates: How to notify attendees about cancellation:
            - "all": Notify all attendees (default)
            - "externalOnly": Only notify external attendees
            - "none": Don't send notifications
        calendar_id: Calendar ID. If None or 'primary', uses user's default calendar preference.
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DELETE_DRAFT registry item (requires user confirmation)
    """
    return await _delete_event_draft_tool_instance.execute(
        runtime=runtime,
        event_id=event_id,
        send_updates=send_updates,
        calendar_id=calendar_id,
    )


# ============================================================================
# DRAFT EXECUTION HELPERS (LOT 9)
# ============================================================================


def _is_calendar_id(value: str) -> bool:
    """
    Check if a value is already a resolved Google Calendar ID vs a calendar name.

    Calendar IDs can be:
    - Email-like: "family08256430369052556985@group.calendar.google.com"
    - Primary alias: "primary"
    - Compact IDs: "c_xxxx" (sometimes used by Google)

    Calendar names are human-readable strings like "Famille", "Work", etc.

    Args:
        value: The string to check

    Returns:
        True if it looks like a calendar ID, False if it's a calendar name
    """
    if not value:
        return False
    # Email-like IDs (group calendars, personal calendars)
    if "@" in value:
        return True
    # Some Google calendar IDs start with c_
    if value.startswith("c_"):
        return True
    # Primary is a special alias
    if value == "primary":
        return True
    return False


async def _resolve_calendar_id(
    draft_content: dict[str, Any],
    client: Any,
    user_id: UUID,
    resolved_type: ConnectorType,
    deps: Any,
) -> str:
    """
    Resolve calendar ID from draft content or user preferences.

    Shared logic for all calendar HITL execute functions.

    Args:
        draft_content: Draft dict (may contain calendar_id).
        client: Calendar client (Google or Apple).
        user_id: User UUID.
        resolved_type: Resolved ConnectorType (GOOGLE_CALENDAR or APPLE_CALENDAR).
        deps: ToolDependencies.

    Returns:
        Resolved calendar ID string (default "primary").
    """
    from src.domains.connectors.preferences.resolver import resolve_calendar_name
    from src.domains.connectors.preferences.service import ConnectorPreferencesService
    from src.domains.connectors.repository import ConnectorRepository

    draft_calendar_id = draft_content.get("calendar_id")
    calendar_id = "primary"

    if draft_calendar_id and draft_calendar_id != "primary":
        if _is_calendar_id(draft_calendar_id):
            calendar_id = draft_calendar_id
            logger.debug("using_calendar_id_from_draft", calendar_id=calendar_id)
        else:
            calendar_id = await resolve_calendar_name(client, draft_calendar_id, fallback="primary")
    else:
        try:
            connector_service = await deps.get_connector_service()
            repo = ConnectorRepository(connector_service.db)
            connector = await repo.get_by_user_and_type(user_id, resolved_type)
            if connector and connector.preferences_encrypted:
                default_name = ConnectorPreferencesService.get_preference_value(
                    resolved_type.value,
                    connector.preferences_encrypted,
                    "default_calendar_name",
                )
                if default_name:
                    calendar_id = await resolve_calendar_name(
                        client, default_name, fallback="primary"
                    )
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            logger.warning("calendar_preference_resolution_failed", error=str(e))

    return calendar_id


async def execute_event_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an event draft: actually create the calendar event.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    Args:
        draft_content: Dict with event content from draft
        user_id: User UUID
        deps: ToolDependencies for getting Google Calendar client

    Returns:
        Dict with create result

    Raises:
        Exception: If event creation fails
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, resolved_type = await resolve_client_for_category("calendar", user_id, deps)
    calendar_id = await _resolve_calendar_id(draft_content, client, user_id, resolved_type, deps)

    result = await client.create_event(
        summary=draft_content["summary"],
        start_datetime=draft_content["start_datetime"],
        end_datetime=draft_content["end_datetime"],
        timezone=draft_content.get("timezone", "Europe/Paris"),
        description=draft_content.get("description"),
        location=draft_content.get("location"),
        attendees=draft_content.get("attendees"),
        calendar_id=calendar_id,
    )

    logger.info(
        "event_draft_executed",
        user_id=str(user_id),
        event_id=result.get("id"),
        summary=draft_content["summary"],
        calendar_id=calendar_id,
    )

    return {
        "success": True,
        "event_id": result.get("id"),
        "html_link": result.get("htmlLink"),
        "summary": draft_content["summary"],
        "start": draft_content["start_datetime"],
        "end": draft_content["end_datetime"],
        "message": APIMessages.event_created_successfully(draft_content["summary"]),
    }


async def execute_event_update_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an event update draft: actually update the calendar event.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    Args:
        draft_content: Dict with update content from draft
        user_id: User UUID
        deps: ToolDependencies for getting Google Calendar client

    Returns:
        Dict with update result

    Raises:
        Exception: If event update fails
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, resolved_type = await resolve_client_for_category("calendar", user_id, deps)
    calendar_id = await _resolve_calendar_id(draft_content, client, user_id, resolved_type, deps)

    result = await client.update_event(
        event_id=draft_content["event_id"],
        summary=draft_content.get("summary"),
        start_datetime=draft_content.get("start_datetime"),
        end_datetime=draft_content.get("end_datetime"),
        timezone=draft_content.get("timezone", "Europe/Paris"),
        description=draft_content.get("description"),
        location=draft_content.get("location"),
        attendees=draft_content.get("attendees"),
        calendar_id=calendar_id,
    )

    logger.info(
        "event_update_draft_executed",
        user_id=str(user_id),
        event_id=draft_content["event_id"],
        summary=result.get("summary"),
        calendar_id=calendar_id,
    )

    return {
        "success": True,
        "event_id": result.get("id"),
        "html_link": result.get("htmlLink"),
        "summary": result.get("summary"),
        "message": APIMessages.event_updated_successfully(result.get("summary", "")),
    }


async def execute_event_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an event delete draft: actually delete the calendar event.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    Args:
        draft_content: Dict with delete content from draft
        user_id: User UUID
        deps: ToolDependencies for getting Google Calendar client

    Returns:
        Dict with delete result

    Raises:
        Exception: If event deletion fails
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, resolved_type = await resolve_client_for_category("calendar", user_id, deps)
    calendar_id = await _resolve_calendar_id(draft_content, client, user_id, resolved_type, deps)

    await client.delete_event(
        event_id=draft_content["event_id"],
        send_updates=draft_content.get("send_updates", "all"),
        calendar_id=calendar_id,
    )

    # Extract summary from event data for message
    event_data = draft_content.get("event", {})
    summary = event_data.get("summary", "")

    logger.info(
        "event_delete_draft_executed",
        user_id=str(user_id),
        event_id=draft_content["event_id"],
        calendar_id=calendar_id,
        summary=summary,
    )

    return {
        "success": True,
        "event_id": draft_content["event_id"],
        "summary": summary,
        "message": APIMessages.event_deleted_successfully(draft_content["event_id"]),
    }


# ============================================================================
# LEGACY: Direct Tools (for backward compatibility and draft execution)
# ============================================================================


class CreateEventDirectTool(ConnectorTool[GoogleCalendarClient]):
    """
    Create event tool that executes immediately (no HITL).

    WARNING: This tool creates events WITHOUT user confirmation.
    Used for execute_fn in DraftCritiqueInteraction.
    """

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"

    def __init__(self) -> None:
        """Initialize direct create event tool."""
        super().__init__(tool_name="create_event_direct_tool", operation="create")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute create event API call - business logic only."""
        summary: str = kwargs["summary"]
        start_datetime: str = kwargs["start_datetime"]
        end_datetime: str = kwargs["end_datetime"]
        timezone: str = kwargs.get("timezone", "Europe/Paris")
        description: str | None = kwargs.get("description")
        location: str | None = kwargs.get("location")
        attendees: list[str] | None = kwargs.get("attendees")

        if not summary or not start_datetime or not end_datetime:
            raise ToolValidationError(
                APIMessages.fields_required(["summary", "start_datetime", "end_datetime"])
            )

        result = await client.create_event(
            summary=summary,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            timezone=timezone,
            description=description,
            location=location,
            attendees=attendees,
        )

        logger.info(
            "calendar_event_created_via_tool",
            user_id=str(user_id),
            event_id=result.get("id"),
            summary=summary,
        )

        return {
            "success": True,
            "event_id": result.get("id"),
            "html_link": result.get("htmlLink"),
            "summary": summary,
            "start": start_datetime,
            "end": end_datetime,
            "message": APIMessages.event_created_successfully(summary),
        }


# ============================================================================
# TOOL 6: LIST CALENDARS (Read Operation - Data Registry LOT 9)
# ============================================================================


class ListCalendarsTool(ToolOutputMixin, ConnectorTool[GoogleCalendarClient]):
    """
    List user's available calendars tool with Data Registry support.

    LOT 9: Read operation returning calendar list for frontend rendering.

    Benefits:
    - Shows all calendars available to the user
    - Helps user select which calendar to use
    - Returns calendar ID, name, color, access role
    """

    connector_type = ConnectorType.GOOGLE_CALENDAR
    client_class = GoogleCalendarClient
    functional_category = "calendar"

    # Data Registry mode enabled
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize list calendars tool with Data Registry support."""
        super().__init__(tool_name="list_calendars_tool", operation="list")

    async def execute_api_call(
        self,
        client: GoogleCalendarClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute list calendars API call."""
        show_hidden: bool = kwargs.get("show_hidden", False)
        max_results: int = kwargs.get("max_results", 100)

        result = await client.list_calendars(
            max_results=max_results,
            show_hidden=show_hidden,
        )

        calendars = result.get("items", [])

        logger.info(
            "list_calendars_success",
            user_id=str(user_id),
            total_calendars=len(calendars),
            show_hidden=show_hidden,
        )

        # Get user preferences for locale
        locale = settings.default_language
        try:
            _, _, locale = await get_user_preferences(self.runtime)
        except (ValueError, KeyError, AttributeError):
            pass  # Use default locale

        return {
            "calendars": calendars,
            "total": len(calendars),
            "show_hidden": show_hidden,
            "locale": locale,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format as Data Registry UnifiedToolOutput with calendar registry items."""
        from src.domains.agents.data_registry.models import (
            RegistryItem,
            RegistryItemMeta,
            RegistryItemType,
            generate_registry_id,
        )

        calendars = result.get("calendars", [])
        total = result.get("total", 0)

        # Build registry items for each calendar
        registry_updates: dict[str, RegistryItem] = {}
        summary_parts = []

        for cal in calendars:
            cal_id = cal.get("id", "")
            summary = cal.get("summary", "Sans nom")
            access_role = cal.get("accessRole", "reader")
            primary = cal.get("primary", False)
            background_color = cal.get("backgroundColor", "#4285f4")

            # Generate deterministic ID for registry
            registry_id = generate_registry_id(RegistryItemType.CALENDAR, cal_id)

            # Create registry item
            registry_updates[registry_id] = RegistryItem(
                id=registry_id,
                type=RegistryItemType.CALENDAR,
                payload={
                    "id": cal_id,
                    "summary": summary,
                    "access_role": access_role,
                    "primary": primary,
                    "background_color": background_color,
                    "description": cal.get("description", ""),
                    "time_zone": cal.get("timeZone", ""),
                },
                meta=RegistryItemMeta(
                    source="google_calendar",
                    domain=CONTEXT_DOMAIN_CALENDARS,
                    tool_name="list_calendars_tool",
                ),
            )

            # Build summary line
            primary_marker = " (principal)" if primary else ""
            summary_parts.append(f"- {summary}{primary_marker} [{registry_id}]")

        # Build LLM message
        if calendars:
            message = f"[calendars] {total} calendrier(s) disponible(s):\n" + "\n".join(
                summary_parts[:10]
            )
            if total > 10:
                message += f"\n... et {total - 10} autre(s)"
        else:
            message = "[calendars] Aucun calendrier trouvé"

        return UnifiedToolOutput.data_success(
            message=message,
            registry_updates=registry_updates,
            metadata={
                "tool_name": "list_calendars_tool",
                "total": total,
                "show_hidden": result.get("show_hidden", False),
            },
        )


# Create tool instance (singleton)
_list_calendars_tool_instance = ListCalendarsTool()


@connector_tool(
    name="list_calendars",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    category="read",
)
async def list_calendars_tool(
    show_hidden: Annotated[
        bool,
        "Include hidden calendars in the list (default: False)",
    ] = False,
    max_results: Annotated[
        int,
        "Maximum number of calendars to return (default: 100, max: 250)",
    ] = 100,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    List all calendars available to the user.

    Returns a list of all calendars the user has access to, including:
    - Primary calendar
    - Secondary calendars (created by user)
    - Shared calendars (shared by others)
    - Subscribed calendars (public calendars)

    **Use Cases:**
    - User asks "quels sont mes calendriers ?"
    - User wants to know available calendars before creating/searching events
    - User needs calendar ID for specific calendar operations

    **Output includes for each calendar:**
    - id: Calendar ID (use this for calendar_id parameter in other tools)
    - summary: Calendar name/title
    - access_role: User's access level (owner, writer, reader)
    - primary: Whether this is the user's primary calendar
    - background_color: Calendar color in UI

    Args:
        show_hidden: Include hidden calendars (default: False)
        max_results: Maximum calendars to return (default: 100, max: 250)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with CALENDAR registry items for frontend rendering

    Example:
        User: "Quels sont mes calendriers disponibles ?"
        -> Returns list of all calendars with their IDs and properties
    """
    return await _list_calendars_tool_instance.execute(
        runtime=runtime,
        show_hidden=show_hidden,
        max_results=max_results,
    )


# ============================================================================
# UNIFIED TOOL: GET EVENTS (v2.0 - replaces search + details)
# ============================================================================


@connector_tool(
    name="get_events",
    agent_name=AGENT_EVENT,
    context_domain=CONTEXT_DOMAIN_EVENTS,
    category="read",
)
async def get_events_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    query: str | None = None,
    event_id: str | None = None,
    event_ids: list[str] | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    days_ahead: int | None = None,
    max_results: int | None = None,
    calendar_id: str | None = None,
    force_refresh: bool = False,
) -> UnifiedToolOutput:
    """
    Get calendar events with full details - unified search and retrieval.

    Architecture Simplification (2026-01):
    - Replaces search_events_tool + get_event_details_tool
    - Always returns FULL event details (summary, location, attendees, etc.)
    - Supports query mode (search) OR ID mode (direct fetch)

    Modes:
    - Query mode: get_events_tool(query="meeting") → search + return full details
    - ID mode: get_events_tool(event_id="abc123") → fetch specific event
    - Batch mode: get_events_tool(event_ids=["abc", "def"]) → fetch multiple
    - Time range: get_events_tool(time_min="...", time_max="...") → range search
    - Relative range: get_events_tool(days_ahead=2) → today + next N days
    - List mode: get_events_tool() → return upcoming events (default: next 30 days)

    Args:
        runtime: Runtime dependencies injected automatically.
        query: Search term - triggers search mode.
        event_id: Single event ID for direct fetch.
        event_ids: Multiple event IDs for batch fetch.
        time_min: Start of time range (ISO 8601).
        time_max: End of time range (ISO 8601).
        days_ahead: Relative time window from now in days (e.g. 2 = today + tomorrow).
                    Takes precedence over time_max if both are provided.
        max_results: Maximum results (default 10, max 50).
        calendar_id: Target calendar (default: primary).
        force_refresh: Bypass cache (default False).

    Returns:
        UnifiedToolOutput with registry items containing event data.
    """
    # Compute time_max from days_ahead (relative window, useful for plan_template)
    if days_ahead is not None:
        time_max = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"

    # Route to appropriate implementation based on parameters
    if event_id or event_ids:
        # ID mode: direct fetch with full details
        return await _get_event_details_tool_instance.execute(
            runtime=runtime,
            event_id=event_id,
            event_ids=event_ids,
            calendar_id=calendar_id,
            force_refresh=force_refresh,
        )
    else:
        # Query/Time mode: search + full details
        return await _search_events_tool_instance.execute(
            runtime=runtime,
            query=query,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            calendar_id=calendar_id,
            force_refresh=force_refresh,
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Unified tool (v2.0 - replaces search + details)
    "get_events_tool",
    # Action tools
    "create_event_tool",
    "update_event_tool",
    "delete_event_tool",
    # Metadata tools (list containers)
    "list_calendars_tool",
    # Tool classes
    "SearchEventsTool",
    "GetEventDetailsTool",
    "CreateEventDraftTool",
    "UpdateEventDraftTool",
    "DeleteEventDraftTool",
    "CreateEventDirectTool",
    "ListCalendarsTool",
    # Draft execution helpers
    "execute_event_draft",
    "execute_event_update_draft",
    "execute_event_delete_draft",
]
