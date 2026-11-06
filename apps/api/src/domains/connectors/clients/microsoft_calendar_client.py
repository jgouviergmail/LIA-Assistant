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

from typing import Any, Final
from uuid import UUID, uuid4

import structlog
from fastapi import status

from src.core.constants import DEFAULT_TIMEZONE
from src.core.exceptions import ConnectorAPIError
from src.core.i18n_api_messages import APIMessages
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.base_microsoft_client import BaseMicrosoftClient
from src.domains.connectors.clients.calendar_answers import GRAPH_ACTS, EventAnswer
from src.domains.connectors.clients.calendar_management import (
    EventLeftBehindError,
    EventNotMovableError,
)
from src.domains.connectors.clients.calendar_options import EventOptions, graph_options
from src.domains.connectors.clients.normalizers.all_day import all_day_dates
from src.domains.connectors.clients.normalizers.graph_paging import (
    graph_page_params,
    graph_page_token,
)
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_calendar,
    normalize_graph_event,
)
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.clients.retry_policy import provider_idempotency_id
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)


def _segment(provider_id: str) -> str:
    """A calendar or event id as ONE segment of a Graph URL path (``path_segments``)."""
    return path_segment(provider_id, connector_type=ConnectorType.MICROSOFT_CALENDAR)


# Default fields for event queries (performance optimization)
_EVENT_SELECT_FIELDS = (
    "id,subject,bodyPreview,body,start,end,location,attendees,organizer,"
    "recurrence,isAllDay,isCancelled,showAs,webLink,createdDateTime,"
    "lastModifiedDateTime,iCalUId,seriesMasterId,type,originalStart,originalStartTimeZone,"
    "responseStatus,isOrganizer,isReminderOn,reminderMinutesBeforeStart,sensitivity"
)

_CALENDAR_SELECT_FIELDS = "id,name,color,isDefaultCalendar,canEdit,isRemovable"

#: What a move copies. Graph writes the rest itself, or the event has none (see the refusals).
_COPIED_FIELDS: Final = (
    "subject",
    "body",
    "start",
    "end",
    "location",
    "isAllDay",
    "showAs",
    "sensitivity",
    "isReminderOn",
    "reminderMinutesBeforeStart",
    "categories",
    "importance",
)
_MOVE_SELECT_FIELDS: Final = ",".join(
    (*_COPIED_FIELDS, "attendees", "hasAttachments", "type", "seriesMasterId")
)

# Graph attaches the Teams join link asynchronously; the event's onlineMeeting is
# surfaced by normalize_graph_event.
_ONLINE_MEETING = {"isOnlineMeeting": True, "onlineMeetingProvider": "teamsForBusiness"}


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
        # Enforce the global per-request volumetry ceiling (centralized cap).
        max_results = apply_max_items_limit(max_results)

        params: dict[str, Any] = {
            "$top": max_results,
            "$select": _EVENT_SELECT_FIELDS,
            "$orderby": "start/dateTime",
        }

        if query:
            # OData string literals escape single quotes by doubling them;
            # unescaped apostrophes make the Graph API reject the filter (400).
            escaped_query = query.replace("'", "''")
            params["$filter"] = f"contains(subject, '{escaped_query}')"

        # Use calendarView for time range queries (expands recurrences)
        if time_min and time_max:
            params["startDateTime"] = time_min
            params["endDateTime"] = time_max

            if calendar_id == "primary":
                endpoint = "/me/calendarView"
            else:
                endpoint = f"/me/calendars/{_segment(calendar_id)}/calendarView"
            # calendarView doesn't support $orderby, remove it
            params.pop("$orderby", None)
        else:
            if calendar_id == "primary":
                endpoint = "/me/calendar/events"
            else:
                endpoint = f"/me/calendars/{_segment(calendar_id)}/events"

        response = await self._make_request("GET", endpoint, params)

        items = [normalize_graph_event(evt) for evt in response.get("value", [])]

        logger.info(
            "microsoft_calendar_events_listed",
            user_id=str(self.user_id),
            count=len(items),
            # A query is a name, a subject or an address: content, never INFO.
            has_query=bool(query),
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

        response = await self._make_request("GET", f"/me/events/{_segment(event_id)}", params)

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
        add_conference: bool = False,
        idempotency_key: str | None = None,
        all_day: bool = False,
        options: EventOptions | None = None,
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
            add_conference: When True, ask Graph to attach a Teams meeting
                (isOnlineMeeting + onlineMeetingProvider). Parity with the
                Google client's Meet creation.
            idempotency_key: The effect's key (ADR-263); the event's
                ``transactionId`` is derived from it, so a create whose answer was
                lost is sent again and Graph keeps one event (S1). None: a key
                minted for this call.
            all_day: The bounds are DATES, the end exclusive (``normalizers.all_day``):
                Graph stores it as ``isAllDay`` with midnight bounds (ADR-369).

        Returns:
            Created event in Google Calendar format.
        """
        effective_timezone = timezone or DEFAULT_TIMEZONE

        event_body: dict[str, Any] = {
            "transactionId": provider_idempotency_id(idempotency_key or uuid4().hex, "microsoft"),
            "subject": summary,
            **_graph_bounds(start_datetime, end_datetime, effective_timezone, all_day=all_day),
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

        event_body.update(graph_options(options or EventOptions()))
        if add_conference:
            event_body.update(_ONLINE_MEETING)

        if calendar_id == "primary":
            endpoint = "/me/calendar/events"
        else:
            endpoint = f"/me/calendars/{_segment(calendar_id)}/events"

        # Graph keeps one event per transactionId, so a lost answer may be resent.
        response = await self._make_request("POST", endpoint, json_data=event_body, idempotent=True)

        logger.info(
            "microsoft_calendar_event_created",
            user_id=str(self.user_id),
            event_id=response.get("id"),
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
        all_day: bool | None = None,
        send_updates: str | None = None,
        add_conference: bool = False,
        options: EventOptions | None = None,
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
            send_updates: Unused: Graph tells the attendees of a meeting its
                organiser changes, and has no way to keep quiet (ADR-369).

        Returns:
            Updated event in Google Calendar format.
        """
        event_body: dict[str, Any] = {}

        if summary is not None:
            event_body["subject"] = summary
        if all_day is not None:
            # A switch of shape carries both bounds and the flag (ADR-369).
            if start_datetime is None or end_datetime is None:
                raise ValueError("Turning an event all-day or timed needs its new start and end.")
            event_body.update(
                _graph_bounds(
                    start_datetime, end_datetime, timezone or DEFAULT_TIMEZONE, all_day=all_day
                )
            )
            # Stated both ways: an all-day event stays all-day unless told otherwise.
            event_body["isAllDay"] = all_day
            start_datetime = end_datetime = None
        event_body.update(_changed_bounds(start_datetime, end_datetime, timezone))
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

        event_body.update(graph_options(options or EventOptions()))
        if add_conference:
            event_body.update(_ONLINE_MEETING)

        response = await self._make_request(
            "PATCH", f"/me/events/{_segment(event_id)}", json_data=event_body
        )

        logger.info(
            "microsoft_calendar_event_updated",
            user_id=str(self.user_id),
            event_id=event_id,
        )

        return normalize_graph_event(response)

    async def list_events_window(
        self, calendar_id: str, time_min: str, time_max: str, *, bound: int
    ) -> dict[str, Any]:
        """Every event of a window — occurrences expanded — up to ``bound`` (ADR-369).

        ``calendarView`` expands recurrences. A next page is asked on the
        client's OWN host with its own parameters, the link's skip value alone
        carried over (``graph_paging``): a link is never where the person's
        token is sent. A link that cannot be continued, or one past
        ``_WINDOW_MAX_PAGES`` pages, is a cut, and says so.

        Returns:
            ``{"events": [...], "truncated": bool}``.
        """
        endpoint = (
            "/me/calendarView"
            if calendar_id == "primary"
            else f"/me/calendars/{_segment(calendar_id)}/calendarView"
        )
        params: dict[str, Any] = {
            "startDateTime": time_min,
            "endDateTime": time_max,
            "$top": min(_WINDOW_PAGE_SIZE, bound + 1),
            "$select": _EVENT_SELECT_FIELDS,
        }
        raw: list[dict[str, Any]] = []
        token: str | None = None
        more = False
        for _ in range(_WINDOW_MAX_PAGES):
            response = await self._make_request(
                "GET", endpoint, {**params, **graph_page_params(token)}
            )
            raw += response.get("value", [])
            more = bool(response.get("@odata.nextLink"))
            token = graph_page_token(response.get("@odata.nextLink"))
            if not token or len(raw) > bound:
                break
        events = [normalize_graph_event(event) for event in raw[:bound]]
        return {"events": events, "truncated": more or len(raw) > bound}

    async def respond_to_event(
        self, event_id: str, response: EventAnswer, calendar_id: str = "primary"
    ) -> dict[str, Any]:
        """Answer an invitation: Graph's own act, the organiser told.

        Args:
            event_id: The event, an occurrence's own id within a series.
            response: The answer.
            calendar_id: Unused: an event's id names it in any calendar.

        Returns:
            What was answered. Graph takes a declined event out of the calendar.
        """
        await self._make_request(
            "POST",
            f"/me/events/{_segment(event_id)}/{GRAPH_ACTS[response]}",
            json_data={"sendResponse": True},
        )
        logger.info("microsoft_calendar_invitation_answered", user_id=str(self.user_id))
        return {"id": event_id, "response": response}

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
        await self._make_request("DELETE", f"/me/events/{_segment(event_id)}")

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

    async def move_event(
        self, event_id: str, calendar_id: str, destination_id: str
    ) -> dict[str, Any]:
        """Move an event: Graph has no such act, so it is copied, then the original removed.

        Args:
            event_id: The event.
            calendar_id: The calendar it is in (unused: an event's id is the mailbox's).
            destination_id: The calendar it goes to.

        Returns:
            The event as the destination holds it, under the id Graph gave the copy.

        Raises:
            EventNotMovableError: It has guests, attachments or a series: nothing was sent.
            EventLeftBehindError: The copy exists, and the original could not be removed.
        """
        path = f"/me/events/{_segment(event_id)}"
        raw = await self._make_request("GET", path, {"$select": _MOVE_SELECT_FIELDS})
        if raw.get("attendees") or raw.get("hasAttachments") or _in_a_series(raw):
            raise EventNotMovableError
        body = {key: raw[key] for key in _COPIED_FIELDS if key in raw}
        # One move, one copy: a copy whose answer was lost may be sent again.
        body["transactionId"] = provider_idempotency_id(
            f"move:{event_id}:{destination_id}", "microsoft"
        )
        copy = await self._make_request(
            "POST",
            f"/me/calendars/{_segment(destination_id)}/events",
            json_data=body,
            idempotent=True,
        )
        await self._remove_original(path)
        return normalize_graph_event(copy)

    async def _remove_original(self, path: str) -> None:
        """Remove what a move copied; an original already gone is the move done.

        Args:
            path: The original's address.

        Raises:
            EventLeftBehindError: It stands beside its copy.
        """
        try:
            await self._make_request("DELETE", path)
        except ConnectorAPIError as error:
            if error.upstream_status_code != status.HTTP_404_NOT_FOUND:
                raise EventLeftBehindError from error
        except Exception as error:
            raise EventLeftBehindError from error

    async def create_calendar(self, name: str, timezone: str | None = None) -> dict[str, Any]:
        """Create a calendar of the account's.

        Args:
            name: Its name.
            timezone: Unused: a Graph calendar has no zone of its own.

        Returns:
            The calendar, as a listing names it.
        """
        raw = await self._make_request("POST", "/me/calendars", json_data={"name": name})
        return normalize_graph_calendar(raw)

    async def rename_calendar(self, calendar_id: str, name: str) -> dict[str, Any]:
        """Give a calendar another name.

        Args:
            calendar_id: The calendar.
            name: Its new name.

        Returns:
            The calendar, as a listing names it.
        """
        raw = await self._make_request(
            "PATCH", f"/me/calendars/{_segment(calendar_id)}", json_data={"name": name}
        )
        return normalize_graph_calendar(raw)

    async def delete_calendar(self, calendar_id: str) -> None:
        """Delete a calendar and all it holds.

        Args:
            calendar_id: The calendar.
        """
        await self._make_request("DELETE", f"/me/calendars/{_segment(calendar_id)}")


def _in_a_series(raw: dict[str, Any]) -> bool:
    """Whether an event belongs to a series: a copy would stand alone."""
    return bool(raw.get("seriesMasterId")) or raw.get("type", "singleInstance") != "singleInstance"


#: Events asked per page while a window is drained.
_WINDOW_PAGE_SIZE = 100
#: Pages one window read may take.
_WINDOW_MAX_PAGES = 40


def _changed_bounds(
    start: str | None, end: str | None, timezone: str | None
) -> dict[str, dict[str, str]]:
    """The bounds a change names.

    Graph keeps an event's zone when a PATCH says none: it is said only when asked.
    """
    zone = {"timeZone": timezone} if timezone is not None else {}
    bounds = {"start": start, "end": end}
    return {key: {"dateTime": value, **zone} for key, value in bounds.items() if value is not None}


def _graph_bounds(start: str, end: str, timezone: str, *, all_day: bool) -> dict[str, Any]:
    """A Graph event's bounds: ``isAllDay`` with midnight dates, or zoned times."""
    if not all_day:
        return {
            "start": {"dateTime": start, "timeZone": timezone},
            "end": {"dateTime": end, "timeZone": timezone},
        }
    first, after_last = all_day_dates(start, end)
    return {
        "isAllDay": True,
        "start": {"dateTime": f"{first.isoformat()}T00:00:00", "timeZone": timezone},
        "end": {"dateTime": f"{after_last.isoformat()}T00:00:00", "timeZone": timezone},
    }
