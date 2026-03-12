"""
Microsoft Calendar (Graph API) client for calendar operations.

Provides calendar and event management via Microsoft Graph API v1.0.
Implements the same interface as GoogleCalendarClient for transparent
provider switching.

API Reference:
- https://learn.microsoft.com/en-us/graph/api/resources/calendar

Scopes required:
- Calendars.Read, Calendars.ReadWrite
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.i18n_api_messages import APIMessages
from src.domains.connectors.clients.base_microsoft_client import BaseMicrosoftClient
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_calendar,
    normalize_graph_event,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)

# Default fields for event queries (performance optimization)
_EVENT_SELECT_FIELDS = (
    "id,subject,bodyPreview,body,start,end,location,attendees,organizer,"
    "recurrence,isAllDay,isCancelled,showAs,webLink,createdDateTime,"
    "lastModifiedDateTime,iCalUId"
)

_CALENDAR_SELECT_FIELDS = "id,name,color,isDefaultCalendar,canEdit"


class MicrosoftCalendarClient(BaseMicrosoftClient):
    """
    Microsoft Calendar client via Graph API.

    Implements CalendarClientProtocol (structural typing) for transparent
    provider switching with GoogleCalendarClient and AppleCalendarClient.

    Uses /me/calendarView for time range queries (expands recurrences)
    and /me/events for other operations.

    Example:
        >>> client = MicrosoftCalendarClient(user_id, credentials, connector_service)
        >>> events = await client.list_events(
        ...     time_min="2025-01-01T00:00:00Z",
        ...     time_max="2025-01-31T23:59:59Z",
        ... )
    """

    connector_type = ConnectorType.MICROSOFT_CALENDAR

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,
    ) -> None:
        """Initialize Microsoft Calendar client."""
        super().__init__(user_id, credentials, connector_service)

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

        Args:
            max_results: Maximum number of calendars.
            show_hidden: Include hidden calendars (no-op for Microsoft).

        Returns:
            Dict with 'items' list of calendar metadata in Google format.
        """
        max_results = min(max_results, 250)

        params: dict[str, Any] = {
            "$top": max_results,
            "$select": _CALENDAR_SELECT_FIELDS,
        }

        response = await self._make_request("GET", "/me/calendars", params)

        items = [normalize_graph_calendar(cal) for cal in response.get("value", [])]

        logger.info(
            "microsoft_calendar_list_retrieved",
            user_id=str(self.user_id),
            count=len(items),
        )

        return {"items": items}

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
        List calendar events with optional filters.

        Uses /me/calendarView when time range is provided (expands recurrences).
        Falls back to /me/events otherwise.

        Args:
            time_min: Start time filter (ISO format).
            time_max: End time filter (ISO format).
            max_results: Maximum events to return.
            calendar_id: Calendar ID ("primary" → default calendar).
            query: Free text search query.
            fields: Field projection (unused, kept for interface compatibility).

        Returns:
            Dict with 'items' list of events in Google Calendar format.
        """
        params: dict[str, Any] = {
            "$top": max_results,
            "$select": _EVENT_SELECT_FIELDS,
            "$orderby": "start/dateTime",
        }

        if query:
            params["$filter"] = f"contains(subject, '{query}')"

        # Use calendarView for time range queries (expands recurrences)
        if time_min and time_max:
            params["startDateTime"] = time_min
            params["endDateTime"] = time_max

            if calendar_id == "primary":
                endpoint = "/me/calendarView"
            else:
                endpoint = f"/me/calendars/{calendar_id}/calendarView"
            # calendarView doesn't support $orderby, remove it
            params.pop("$orderby", None)
        else:
            if calendar_id == "primary":
                endpoint = "/me/calendar/events"
            else:
                endpoint = f"/me/calendars/{calendar_id}/events"

        response = await self._make_request("GET", endpoint, params)

        items = [normalize_graph_event(evt) for evt in response.get("value", [])]

        logger.info(
            "microsoft_calendar_events_listed",
            user_id=str(self.user_id),
            count=len(items),
            query=query,
        )

        return {"items": items}

    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get details of a specific calendar event.

        Args:
            event_id: Event ID.
            calendar_id: Calendar ID (unused, events have global IDs in Graph).
            fields: Field projection (unused, kept for interface compatibility).

        Returns:
            Dict in Google Calendar event format.
        """
        params: dict[str, Any] = {"$select": _EVENT_SELECT_FIELDS}

        response = await self._make_request("GET", f"/me/events/{event_id}", params)

        logger.info(
            "microsoft_calendar_event_retrieved",
            user_id=str(self.user_id),
            event_id=event_id,
        )

        return normalize_graph_event(response)

    # =========================================================================
    # WRITE OPERATIONS
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
        Create a new calendar event.

        Args:
            summary: Event title/summary.
            start_datetime: Start datetime in ISO format.
            end_datetime: End datetime in ISO format.
            timezone: IANA timezone.
            description: Event description.
            location: Event location.
            attendees: List of attendee email addresses.
            calendar_id: Target calendar ID.

        Returns:
            Created event in Google Calendar format.
        """
        from src.core.constants import DEFAULT_TIMEZONE

        effective_timezone = timezone or DEFAULT_TIMEZONE

        event_body: dict[str, Any] = {
            "subject": summary,
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
            event_body["body"] = {"contentType": "text", "content": description}
        if location:
            event_body["location"] = {"displayName": location}
        if attendees:
            event_body["attendees"] = [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in attendees
            ]

        if calendar_id == "primary":
            endpoint = "/me/calendar/events"
        else:
            endpoint = f"/me/calendars/{calendar_id}/events"

        response = await self._make_request("POST", endpoint, json_data=event_body)

        logger.info(
            "microsoft_calendar_event_created",
            user_id=str(self.user_id),
            event_id=response.get("id"),
            summary=summary,
        )

        return normalize_graph_event(response)

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

        Only provided fields are updated (PATCH semantics).

        Args:
            event_id: Event ID to update.
            summary: New title.
            start_datetime: New start datetime.
            end_datetime: New end datetime.
            timezone: IANA timezone.
            description: New description.
            location: New location.
            attendees: New attendee list.
            calendar_id: Calendar ID (unused for updates).

        Returns:
            Updated event in Google Calendar format.
        """
        event_body: dict[str, Any] = {}

        if summary is not None:
            event_body["subject"] = summary
        if start_datetime is not None:
            # Microsoft Graph preserves the existing event timezone if timeZone
            # is not included in the PATCH body. Only set timeZone when the caller
            # explicitly provides one; otherwise let Graph keep the original.
            start_obj: dict[str, str] = {"dateTime": start_datetime}
            if timezone is not None:
                start_obj["timeZone"] = timezone
            event_body["start"] = start_obj
        if end_datetime is not None:
            end_obj: dict[str, str] = {"dateTime": end_datetime}
            if timezone is not None:
                end_obj["timeZone"] = timezone
            event_body["end"] = end_obj
        if description is not None:
            event_body["body"] = {"contentType": "text", "content": description}
        if location is not None:
            event_body["location"] = {"displayName": location}
        if attendees is not None:
            event_body["attendees"] = [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in attendees
            ]

        response = await self._make_request("PATCH", f"/me/events/{event_id}", json_data=event_body)

        logger.info(
            "microsoft_calendar_event_updated",
            user_id=str(self.user_id),
            event_id=event_id,
        )

        return normalize_graph_event(response)

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> dict[str, Any]:
        """
        Delete a calendar event.

        Args:
            event_id: Event ID to delete.
            calendar_id: Calendar ID (unused for deletes).
            send_updates: How to notify attendees (unused, Graph sends by default).

        Returns:
            Dict with deletion confirmation.
        """
        await self._make_request("DELETE", f"/me/events/{event_id}")

        logger.info(
            "microsoft_calendar_event_deleted",
            user_id=str(self.user_id),
            event_id=event_id,
        )

        return {
            "success": True,
            "event_id": event_id,
            "message": APIMessages.event_deleted_successfully(event_id),
        }
