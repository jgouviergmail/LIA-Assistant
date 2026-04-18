"""
Google Calendar API client for Calendar operations.

Handles authentication, rate limiting, and calendar event management.

LOT 5.4: Write operations with HITL integration.

Inherits from BaseGoogleClient for common functionality.
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.i18n_api_messages import APIMessages
from src.core.time_utils import normalize_to_rfc3339
from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)


class GoogleCalendarClient(BaseGoogleClient):
    """
    Google Calendar API client with OAuth, rate limiting, and error handling.

    Inherits common functionality from BaseGoogleClient:
    - Automatic token refresh with Redis lock
    - Rate limiting (configurable, default 10 req/s)
    - HTTP client with connection pooling
    - Retry logic with exponential backoff

    LOT 5.4: Write operations with HITL integration.
    This client provides methods for creating calendar events
    after user confirmation via the Draft/Critique/Execute flow.

    Example:
        >>> client = GoogleCalendarClient(user_id, credentials, connector_service)
        >>> result = await client.create_event(
        ...     summary="Team Meeting",
        ...     start_datetime="2025-01-15T10:00:00",
        ...     end_datetime="2025-01-15T11:00:00",
        ...     timezone="Europe/Paris",
        ... )
    """

    # Required by BaseGoogleClient
    connector_type = ConnectorType.GOOGLE_CALENDAR
    api_base_url = "https://www.googleapis.com/calendar/v3"

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,  # ConnectorService
    ) -> None:
        """
        Initialize Google Calendar client.

        Args:
            user_id: User UUID.
            credentials: OAuth credentials (access_token, refresh_token).
            connector_service: ConnectorService instance for token refresh.
        """
        # Initialize base class with default rate limiting
        super().__init__(user_id, credentials, connector_service)

    # =========================================================================
    # WRITE OPERATIONS (LOT 5.4)
    # =========================================================================

    async def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        timezone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """
        Create a new calendar event in Google Calendar.

        LOT 5.4: Write operation with HITL integration.
        This method is called after user confirms the draft via HITL.

        Args:
            summary: Event title/summary (required)
            start_datetime: Start datetime in ISO format (required)
            end_datetime: End datetime in ISO format (required)
            timezone: IANA timezone (default: from settings or DEFAULT_TIMEZONE)
            description: Event description (optional)
            location: Event location (optional)
            attendees: List of attendee email addresses (optional)
            calendar_id: Target calendar ID (default: "primary" for user's main calendar)

        Returns:
            Created event data with event ID

        Example:
            >>> result = await client.create_event(
            ...     summary="Team Meeting",
            ...     start_datetime="2025-01-15T10:00:00",
            ...     end_datetime="2025-01-15T11:00:00",
            ...     description="Weekly sync",
            ...     attendees=["alice@example.com", "bob@example.com"],
            ...     calendar_id="family_calendar_id",
            ... )
            >>> print(result["id"])  # "event_123..."
        """
        # Use default timezone if not provided
        from src.core.constants import DEFAULT_TIMEZONE

        effective_timezone = timezone or DEFAULT_TIMEZONE

        # Build event body per Google Calendar API spec
        # https://developers.google.com/calendar/api/v3/reference/events/insert
        event_body: dict[str, Any] = {
            "summary": summary,
            "start": {
                "dateTime": start_datetime,
                "timeZone": effective_timezone,
            },
            "end": {
                "dateTime": end_datetime,
                "timeZone": effective_timezone,
            },
        }

        if description:
            event_body["description"] = description

        if location:
            event_body["location"] = location

        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]

        # Make API request to create event
        # POST /calendars/{calendarId}/events
        response = await self._make_request(
            "POST",
            f"/calendars/{calendar_id}/events",
            json_data=event_body,
        )

        logger.info(
            "calendar_event_created",
            user_id=str(self.user_id),
            event_id=response.get("id"),
            summary=summary,
        )

        return response

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    async def list_calendars(
        self,
        max_results: int = 100,
        show_hidden: bool = False,
    ) -> dict[str, Any]:
        """
        List all calendars accessible by the user.

        Used for preference resolution (name -> ID mapping).

        Args:
            max_results: Maximum number of calendars (default: 100, max: 250)
            show_hidden: Include hidden calendars (default: False)

        Returns:
            Dict with 'items' list of calendar metadata

        Example:
            >>> result = await client.list_calendars()
            >>> for cal in result.get("items", []):
            ...     print(f"{cal['summary']} ({cal['id']})")
        """
        max_results = min(max_results, 250)

        params: dict[str, Any] = {
            "maxResults": max_results,
            "showHidden": show_hidden,
        }

        response = await self._make_request(
            "GET",
            "/users/me/calendarList",
            params=params,
        )

        logger.info(
            "calendar_list_retrieved",
            user_id=str(self.user_id),
            count=len(response.get("items", [])),
        )

        return response

    async def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
        calendar_id: str = "primary",
        query: str | None = None,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        List calendar events with optional filters and field projection.

        Args:
            time_min: Start time filter (ISO format with timezone, e.g., '2025-01-15T00:00:00Z')
            time_max: End time filter (ISO format with timezone)
            max_results: Maximum number of events to return (default: 10, max: 2500)
            calendar_id: Calendar ID (default: primary)
            query: Free text search query (optional)
            fields: List of event fields to return (optional, for optimization).
                   If None, returns all fields.
                   Example: ["id", "summary", "start", "end", "location"]

        Returns:
            Dict with 'items' list of events

        Example:
            >>> result = await client.list_events(
            ...     time_min="2025-01-01T00:00:00Z",
            ...     time_max="2025-01-31T23:59:59Z",
            ...     query="meeting",
            ...     max_results=20,
            ...     fields=["id", "summary", "start", "end"],
            ... )
            >>> print(len(result["items"]))
        """
        params: dict[str, Any] = {
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if query:
            params["q"] = query

        # Field projection for optimization (reduces response size and latency)
        if fields:
            # Google Calendar API uses "fields" parameter with items(field1,field2) syntax
            fields_str = ",".join(fields)
            params["fields"] = f"items({fields_str}),nextPageToken"

        response = await self._make_request(
            "GET",
            f"/calendars/{calendar_id}/events",
            params=params,
        )

        logger.info(
            "calendar_events_listed",
            user_id=str(self.user_id),
            count=len(response.get("items", [])),
            query=query,
            fields_projected=bool(fields),
        )

        return response

    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get details of a specific calendar event.

        Args:
            event_id: Event ID to retrieve
            calendar_id: Calendar ID (default: primary)
            fields: List of event fields to return (optional, for optimization).
                   If None, returns all fields.

        Returns:
            Dict with event data

        Example:
            >>> event = await client.get_event("event_id_123")
            >>> print(event["summary"])
        """
        params: dict[str, Any] = {}

        # Field projection for optimization
        if fields:
            params["fields"] = ",".join(fields)

        response = await self._make_request(
            "GET",
            f"/calendars/{calendar_id}/events/{event_id}",
            params=params if params else None,
        )

        logger.info(
            "calendar_event_retrieved",
            user_id=str(self.user_id),
            event_id=event_id,
            summary=response.get("summary", ""),
            fields_projected=bool(fields),
        )

        return response

    async def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        timezone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """
        Update an existing calendar event.

        LOT 9: Write operation with HITL integration.
        This method is called after user confirms the update draft via HITL.

        Only provided fields are updated. Omitted fields keep their existing values.

        Args:
            event_id: Event ID to update
            summary: New event title/summary (optional)
            start_datetime: New start datetime in ISO format (optional)
            end_datetime: New end datetime in ISO format (optional)
            timezone: IANA timezone for datetime fields (default: from settings or DEFAULT_TIMEZONE)
            description: New event description (optional)
            location: New event location (optional)
            attendees: New list of attendee email addresses (optional)
            calendar_id: Calendar ID (default: primary)

        Returns:
            Updated event data with event ID

        Example:
            >>> result = await client.update_event(
            ...     event_id="event_123",
            ...     summary="Updated Meeting Title",
            ...     description="New description",
            ... )
            >>> print(result["summary"])
        """
        # Use default timezone if not provided
        from src.core.constants import DEFAULT_TIMEZONE

        effective_timezone = timezone or DEFAULT_TIMEZONE

        # First, get the existing event to preserve unchanged fields
        existing_event = await self.get_event(event_id, calendar_id)

        # Build update body, preserving existing values
        event_body: dict[str, Any] = {}

        # Update summary if provided, else keep existing
        if summary is not None:
            event_body["summary"] = summary
        elif "summary" in existing_event:
            event_body["summary"] = existing_event["summary"]

        # Update datetime fields
        # Google Calendar requires start and end to use the same format.
        # Detect from EXISTING event whether it's all-day or timed,
        # then force the same format regardless of what the LLM produced.
        is_all_day = "date" in existing_event.get(
            "start", {}
        ) and "dateTime" not in existing_event.get("start", {})

        if start_datetime is not None:
            if is_all_day:
                # All-day: strip any time part, keep YYYY-MM-DD only
                event_body["start"] = {"date": str(start_datetime).split("T")[0]}
            else:
                event_body["start"] = {
                    "dateTime": normalize_to_rfc3339(start_datetime) or start_datetime,
                    "timeZone": effective_timezone,
                }
        elif "start" in existing_event:
            event_body["start"] = existing_event["start"]

        if end_datetime is not None:
            if is_all_day:
                event_body["end"] = {"date": str(end_datetime).split("T")[0]}
            else:
                event_body["end"] = {
                    "dateTime": normalize_to_rfc3339(end_datetime) or end_datetime,
                    "timeZone": effective_timezone,
                }
        elif "end" in existing_event:
            event_body["end"] = existing_event["end"]

        # Update optional fields
        if description is not None:
            event_body["description"] = description
        elif "description" in existing_event:
            event_body["description"] = existing_event["description"]

        if location is not None:
            event_body["location"] = location
        elif "location" in existing_event:
            event_body["location"] = existing_event["location"]

        if attendees is not None:
            event_body["attendees"] = [{"email": email} for email in attendees]
        elif "attendees" in existing_event:
            event_body["attendees"] = existing_event["attendees"]

        # Make PATCH request to update event
        # Using PATCH for partial update (PUT would replace entirely)
        response = await self._make_request(
            "PATCH",
            f"/calendars/{calendar_id}/events/{event_id}",
            json_data=event_body,
        )

        logger.info(
            "calendar_event_updated",
            user_id=str(self.user_id),
            event_id=event_id,
            summary=event_body.get("summary", ""),
        )

        return response

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> dict[str, Any]:
        """
        Delete a calendar event.

        LOT 9: Write operation with HITL confirmation.
        This method is called after user confirms deletion via HITL.

        Args:
            event_id: Event ID to delete
            calendar_id: Calendar ID (default: primary)
            send_updates: How to send updates to attendees.
                - "all": Send updates to all attendees
                - "externalOnly": Send updates only to external attendees
                - "none": Don't send updates (default for privacy)

        Returns:
            Dict with deletion confirmation

        Example:
            >>> result = await client.delete_event("event_id_123")
            >>> print(result["success"])
        """
        params: dict[str, Any] = {
            "sendUpdates": send_updates,
        }

        # DELETE request returns empty body on success (204)
        await self._make_request(
            "DELETE",
            f"/calendars/{calendar_id}/events/{event_id}",
            params=params,
        )

        logger.info(
            "calendar_event_deleted",
            user_id=str(self.user_id),
            event_id=event_id,
            send_updates=send_updates,
        )

        return {
            "success": True,
            "event_id": event_id,
            "message": APIMessages.event_deleted_successfully(event_id),
        }
