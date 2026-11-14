"""
Google Calendar API client for Calendar operations.

Handles authentication, rate limiting, and calendar event management.

LOT 5.4: Write operations with HITL integration.

Inherits from BaseGoogleClient for common functionality.
"""

import asyncio
from typing import Any
from uuid import UUID, uuid4

import structlog

from src.core.exceptions import ConnectorAPIError, ExternalServiceError
from src.core.i18n_api_messages import APIMessages
from src.core.wall_time import WallTime
from src.domains.connectors.clients.base_google_client import (
    BaseGoogleClient,
    apply_max_items_limit,
)
from src.domains.connectors.clients.calendar_answers import EventAnswer, NotInvitedError
from src.domains.connectors.clients.calendar_options import EventOptions, google_options
from src.domains.connectors.clients.event_bounds import (
    BoundsChange,
    DayBounds,
    EventBounds,
    TimedSides,
)
from src.domains.connectors.clients.normalizers.all_day import is_all_day
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.clients.retry_policy import (
    CREATE_SETTLE_READS,
    backoff_seconds,
    provider_idempotency_id,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)


def _segment(provider_id: str) -> str:
    """A calendar or event id as ONE segment of a Google URL path (``path_segments``)."""
    return path_segment(provider_id, connector_type=ConnectorType.GOOGLE_CALENDAR)


def _create_may_have_happened(error: ExternalServiceError | ConnectorAPIError) -> bool:
    """Whether a failed create may still have made its event (S1).

    Every attempt carried this act's own id, so any of them may have been kept: a lost
    answer, resends spent on a 5xx or a 429 after an earlier attempt was kept (the loop
    then fails with no cause — third fresh review, 2026-10-29), or Google refusing the id
    this very create chose. Only a 4xx other than 409 is an answer that nothing was kept;
    no other act holds the id, so reading it back can never adopt someone else's event.
    """
    if isinstance(error, ConnectorAPIError):
        return error.status_code == 409 or error.status_code >= 500
    return True


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
        >>> paris = ZoneInfo("Europe/Paris")
        >>> result = await client.create_event(
        ...     summary="Team Meeting",
        ...     bounds=bounds_of("2025-01-15T10:00", "2025-01-15T11:00", paris, all_day=False),
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
        bounds: EventBounds,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
        add_conference: bool = False,
        idempotency_key: str | None = None,
        options: EventOptions | None = None,
    ) -> dict[str, Any]:
        """
        Create a new calendar event in Google Calendar.

        LOT 5.4: Write operation with HITL integration.
        This method is called after user confirms the draft via HITL.

        Args:
            summary: Event title/summary (required)
            bounds: When it takes place: wall times in their zone, or days whose
                end is exclusive (``event_bounds``, ADR-380)
            description: Event description (optional)
            location: Event location (optional)
            attendees: List of attendee email addresses (optional)
            calendar_id: Target calendar ID (default: "primary" for user's main calendar)
            add_conference: When True, ask Google to attach a Meet link
                (conferenceData.createRequest + conferenceDataVersion=1).
                Best-effort on Google's side: the event is created even if the
                conference creation fails (the link is then simply absent).
            idempotency_key: The effect's key (ADR-263); the event's id is derived
                from it, so a create whose answer was lost is found again by that id
                rather than sent twice (S1). None: a key minted for this call.

        Returns:
            Created event data with event ID

        Example:
            >>> result = await client.create_event(
            ...     summary="Team Meeting",
            ...     bounds=bounds_of("2025-01-15T10:00", "2025-01-15T11:00", paris, all_day=False),
            ...     description="Weekly sync",
            ...     attendees=["alice@example.com", "bob@example.com"],
            ...     calendar_id="family_calendar_id",
            ... )
            >>> print(result["id"])  # "event_123..."
        """
        # Build event body per Google Calendar API spec
        # https://developers.google.com/calendar/api/v3/reference/events/insert
        event_id = provider_idempotency_id(idempotency_key or uuid4().hex, "google")
        event_body: dict[str, Any] = {
            "id": event_id,
            "summary": summary,
            **_event_bounds(bounds),
        }

        if description:
            event_body["description"] = description

        if location:
            event_body["location"] = location

        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]

        # Meet link: Google dedupes conference creation by requestId, so a
        # fresh UUID per event is required (a reused id would attach the SAME
        # meeting to different events). conferenceDataVersion=1 opts into the
        # conference-aware API behavior.
        params: dict[str, Any] | None = None
        event_body.update(google_options(options or EventOptions()))
        if add_conference:
            event_body.update(_conference_request())
            params = {"conferenceDataVersion": 1}

        # POST /calendars/{calendarId}/events — replay-safe: it carries its own id, which
        # Google refuses once held (measured), so a lost answer is resent like Graph's
        # transactionId and CalDAV's uid.
        try:
            response = await self._make_request(
                "POST",
                f"/calendars/{_segment(calendar_id)}/events",
                json_data=event_body,
                params=params,
                idempotent=True,
            )
        except (ExternalServiceError, ConnectorAPIError) as error:
            if not _create_may_have_happened(error):
                raise
            response = await self._created_event_or_raise(calendar_id, event_id, error)

        logger.info(
            "calendar_event_created",
            user_id=str(self.user_id),
            event_id=response.get("id"),
        )

        return response

    async def _created_event_or_raise(
        self, calendar_id: str, event_id: str, error: ExternalServiceError | ConnectorAPIError
    ) -> dict[str, Any]:
        """Settle a create that may have happened by reading the event it named (S1).

        Found, the create happened; « cancelled » is a final answer (the act was
        undone); « not found » is read again, ``CREATE_SETTLE_READS`` times at most —
        measured live, an event whose answer was lost read 404 at once while Google
        was still writing it. Anything else leaves the failure standing.

        Args:
            calendar_id: The calendar the event was created in.
            event_id: The id the create carried.
            error: The create's failure.

        Returns:
            The created event.

        Raises:
            ExternalServiceError: ``error`` itself, when nothing proves the create.
            ConnectorAPIError: ``error`` itself, when nothing proves the create.
        """
        for read in range(CREATE_SETTLE_READS):
            if read:
                await asyncio.sleep(backoff_seconds(read - 1))
            try:
                event = await self.get_event(event_id, calendar_id)
            except ConnectorAPIError as lookup:
                if lookup.status_code == 404:
                    continue
                raise error from lookup
            except ExternalServiceError as lookup:
                raise error from lookup
            if not event or event.get("status") == "cancelled":
                raise error
            logger.info("calendar_event_create_reconciled", user_id=str(self.user_id))
            return event
        raise error

    async def query_freebusy(
        self,
        time_min: str,
        time_max: str,
        calendar_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Query busy time ranges over one or more calendars (freeBusy endpoint).

        Returns busy ranges ONLY — strictly less data than listing events
        (minimization by capability, same doctrine as telephony availability).

        Args:
            time_min: RFC3339 inclusive lower bound.
            time_max: RFC3339 exclusive upper bound.
            calendar_ids: Calendars to query (default: ["primary"]).

        Returns:
            Google freeBusy response: {"calendars": {id: {"busy": [...]}}}.
        """
        body: dict[str, Any] = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": calendar_id} for calendar_id in (calendar_ids or ["primary"])],
        }
        response = await self._make_request(
            "POST", "/freeBusy", json_data=body, idempotent=True  # a read
        )
        logger.info(
            "calendar_freebusy_queried",
            user_id=str(self.user_id),
            calendars=len(body["items"]),
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
        # Metadata enumeration (calendar name -> ID resolution), NOT item
        # volumetry: intentionally exempt from the global per-request cap so a
        # user with many (shared) calendars can still resolve any of them. Bounded
        # by the Google API hard limit (250). See the volumetry guard allow-list.
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

    @staticmethod
    def _events_params(
        *,
        time_min: str | None,
        time_max: str | None,
        max_results: int,
        query: str | None = None,
        fields: list[str] | None = None,
        updated_min: str | None = None,
    ) -> dict[str, Any]:
        """Query parameters shared by the single-request event listings.

        Enforces the global per-request volumetry ceiling (ADR: centralized
        cap): these listings do NOT go through ``BaseGoogleClient._paginate``,
        so the cap is applied here — the domain-level cap is applied upstream
        in the tool, this is the hard safety ceiling.
        """
        params: dict[str, Any] = {
            "maxResults": apply_max_items_limit(max_results),
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if query:
            params["q"] = query
        if updated_min:
            params["updatedMin"] = updated_min
        # Field projection for optimization (reduces response size and latency):
        # Google Calendar API uses "fields" with the items(field1,field2) syntax.
        if fields:
            params["fields"] = f"items({','.join(fields)}),nextPageToken"
        return params

    async def list_updated_events(
        self,
        *,
        calendar_id: str,
        updated_min: str,
        time_min: str,
        time_max: str,
        max_results: int = 20,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Events changed since ``updated_min`` that start inside the window (ADR-261).

        Google-only on purpose: the provider protocol's ``list_events`` has no
        "changed since" filter and the other calendar providers cannot honour
        one, so the push wake reads its delta through this dedicated method
        rather than widening the shared signature (the parity contract would
        rightly refuse).

        Args:
            calendar_id: Calendar to read.
            updated_min: RFC3339 lower bound on the event's last modification.
            time_min: RFC3339 start of the window the event must start in.
            time_max: RFC3339 end of that window.
            max_results: Hard-capped by ``apply_max_items_limit``.
            fields: Optional projection, as for ``list_events``.

        Returns:
            The raw listing (``items``), unsorted beyond the API's start-time order.
        """
        params = self._events_params(
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            fields=fields,
            updated_min=updated_min,
        )
        return await self._make_request(
            "GET", f"/calendars/{_segment(calendar_id)}/events", params=params
        )

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
        params = self._events_params(
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            query=query,
            fields=fields,
        )

        response = await self._make_request(
            "GET",
            f"/calendars/{_segment(calendar_id)}/events",
            params=params,
        )

        logger.info(
            "calendar_events_listed",
            user_id=str(self.user_id),
            count=len(response.get("items", [])),
            # A query is a name, a subject or an address: content, never INFO.
            has_query=bool(query),
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
            f"/calendars/{_segment(calendar_id)}/events/{_segment(event_id)}",
            params=params if params else None,
        )

        logger.info(
            "calendar_event_retrieved",
            user_id=str(self.user_id),
            event_id=event_id,
            fields_projected=bool(fields),
        )

        return response

    async def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        bounds: BoundsChange | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
        send_updates: str | None = None,
        add_conference: bool = False,
        options: EventOptions | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing calendar event.

        LOT 9: Write operation with HITL integration.
        This method is called after user confirms the update draft via HITL.

        Only provided fields are updated. Omitted fields keep their existing values.

        Args:
            event_id: Event ID to update
            summary: New event title/summary (optional)
            bounds: What changes of its bounds (``event_bounds``, ADR-380): a whole
                new pair gives the event its shape, sides alone keep the shape it
                has, None leaves its bounds as they are
            description: New event description (optional)
            location: New event location (optional)
            attendees: New list of attendee email addresses (optional)
            send_updates: Who Google tells of the change (``all``, ``externalOnly``,
                ``none``); None leaves Google's own default, which tells nobody.
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
        # First, get the existing event to preserve unchanged fields
        existing_event = await self.get_event(event_id, calendar_id)

        # Build the update body: each value given replaces, an absent one is kept.
        # A whole pair of bounds gives the event its shape (ADR-369), the other
        # half of each provider object CLEARED (a PATCH merges objects: a « date »
        # left beside a new « dateTime » is refused). Sides alone keep the
        # EXISTING shape.
        event_body: dict[str, Any] = {
            **_kept_fields(
                existing_event,
                summary=summary,
                description=description,
                location=location,
                attendees=None if attendees is None else [{"email": e} for e in attendees],
            ),
            **(
                _kept_bounds(existing_event, bounds or TimedSides())
                if bounds is None or isinstance(bounds, TimedSides)
                else _switched_bounds(bounds)
            ),
        }

        event_body.update(google_options(options or EventOptions()))
        params: dict[str, Any] = {} if send_updates is None else {"sendUpdates": send_updates}
        if add_conference:
            event_body.update(_conference_request())
            params["conferenceDataVersion"] = 1

        # Make PATCH request to update event
        # Using PATCH for partial update (PUT would replace entirely)
        response = await self._make_request(
            "PATCH",
            f"/calendars/{_segment(calendar_id)}/events/{_segment(event_id)}",
            json_data=event_body,
            params=params or None,
        )

        logger.info(
            "calendar_event_updated",
            user_id=str(self.user_id),
            event_id=event_id,
        )

        return response

    async def respond_to_event(
        self, event_id: str, response: EventAnswer, calendar_id: str = "primary"
    ) -> dict[str, Any]:
        """Answer an invitation: the person's own attendee, the organiser told.

        Args:
            event_id: The event, an occurrence's own id within a series.
            response: The answer.
            calendar_id: Its calendar.

        Returns:
            The event as it is now.

        Raises:
            NotInvitedError: Google marks no attendee of this event as the person.
        """
        event = await self.get_event(event_id, calendar_id)
        attendees = event.get("attendees") or []
        if not any(item.get("self") for item in attendees):
            raise NotInvitedError
        answered = await self._make_request(
            "PATCH",
            f"/calendars/{_segment(calendar_id)}/events/{_segment(event_id)}",
            json_data={
                "attendees": [
                    {**item, "responseStatus": response} if item.get("self") else item
                    for item in attendees
                ]
            },
            params={"sendUpdates": "all"},
        )
        logger.info("calendar_invitation_answered", user_id=str(self.user_id))
        return answered

    async def list_events_window(
        self, calendar_id: str, time_min: str, time_max: str, *, bound: int
    ) -> dict[str, Any]:
        """Every event of a window — occurrences expanded — up to ``bound`` (ADR-369).

        Pages are drained (``pageToken``) until the window is read or ``bound``
        events are; past it — or past ``_WINDOW_MAX_PAGES`` pages, since Google
        may answer an empty page with a token — the answer says it was cut.

        Returns:
            ``{"events": [...], "truncated": bool}``.
        """
        events: list[dict[str, Any]] = []
        page_token: str | None = None
        for _ in range(_WINDOW_MAX_PAGES):
            params: dict[str, Any] = {
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": True,
                "orderBy": "startTime",
                "maxResults": min(_WINDOW_PAGE_SIZE, bound - len(events) + 1),
            }
            if page_token:
                params["pageToken"] = page_token
            response = await self._make_request(
                "GET", f"/calendars/{_segment(calendar_id)}/events", params=params
            )
            events += response.get("items", [])
            page_token = response.get("nextPageToken")
            if not page_token or len(events) > bound:
                break
        return {"events": events[:bound], "truncated": bool(page_token) or len(events) > bound}

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
            f"/calendars/{_segment(calendar_id)}/events/{_segment(event_id)}",
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

    async def move_event(
        self, event_id: str, calendar_id: str, destination_id: str
    ) -> dict[str, Any]:
        """Move an event to another calendar, its id kept: Google's own act.

        Args:
            event_id: The event.
            calendar_id: The calendar it is in.
            destination_id: The calendar it goes to.

        Returns:
            The event as the destination holds it.
        """
        return await self._make_request(
            "POST",
            f"/calendars/{_segment(calendar_id)}/events/{_segment(event_id)}/move",
            params={"destination": destination_id},
        )

    async def create_calendar(self, name: str, timezone: str | None = None) -> dict[str, Any]:
        """Create a calendar of the account's.

        Args:
            name: Its name.
            timezone: The zone Google shows it in; left out, Google's own default.

        Returns:
            The calendar, as a listing names it.
        """
        body = {"summary": name, **({"timeZone": timezone} if timezone else {})}
        return await self._make_request("POST", "/calendars", json_data=body)

    async def rename_calendar(self, calendar_id: str, name: str) -> dict[str, Any]:
        """Give a calendar another name.

        Args:
            calendar_id: The calendar.
            name: Its new name.

        Returns:
            The calendar, as a listing names it.
        """
        return await self._make_request(
            "PATCH", f"/calendars/{_segment(calendar_id)}", json_data={"summary": name}
        )

    async def delete_calendar(self, calendar_id: str) -> None:
        """Delete a calendar and all it holds.

        Args:
            calendar_id: The calendar.
        """
        await self._make_request("DELETE", f"/calendars/{_segment(calendar_id)}")

    async def watch_events(
        self,
        channel_id: str,
        token: str,
        address: str,
        ttl_seconds: int,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Open a push channel on a calendar's events (lot H phase 1).

        Google's contract: ``type`` must be ``web_hook`` and ``ttl`` is a
        STRING inside ``params``. The response carries ``resourceId`` and the
        effective ``expiration`` (epoch ms — Google may shorten the asked TTL).

        Args:
            channel_id: Our channel identifier (echoed in X-Goog-Channel-ID).
            token: Opaque secret echoed in X-Goog-Channel-Token.
            address: Public HTTPS webhook URL (domain must be verified).
            ttl_seconds: Requested channel lifetime.
            calendar_id: Calendar to watch (default primary).

        Returns:
            The channel resource returned by Google.
        """
        return await self._make_request(
            "POST",
            f"/calendars/{_segment(calendar_id)}/events/watch",
            json_data={
                "id": channel_id,
                "type": "web_hook",
                "address": address,
                "token": token,
                "params": {"ttl": str(ttl_seconds)},
            },
        )

    async def stop_channel(self, channel_id: str, resource_id: str) -> dict[str, Any]:
        """Close a push channel (API-wide /channels/stop endpoint)."""
        return await self._make_request(
            "POST",
            "/channels/stop",
            json_data={"id": channel_id, "resourceId": resource_id},
        )


#: Events asked per page while a window is drained (Google allows 2 500).
_WINDOW_PAGE_SIZE = 250
#: Pages one window read may take — a page can be empty and still name a next one.
_WINDOW_MAX_PAGES = 40


def _zoned(moment: WallTime) -> dict[str, str]:
    """A timed bound as Google reads it: the time on the wall, beside its zone.

    Google's own contract: « a time zone offset is required unless a time zone is
    explicitly specified in ``timeZone`` ». The wall time is sent WITHOUT one —
    Google reads an offset before it reads the zone, so a wall time given a ``Z``
    on the way is that hour in UTC, an hour late in Paris (production, 2026-11-12).

    One exception, and it uses that very rule: an hour the zone's clocks skip or
    show twice is not placed by the zone, so its offset is written and Google
    reads the instant that is meant.
    """
    written = (
        moment.iso() if moment.zone_suffices else moment.in_its_zone().isoformat(timespec="seconds")
    )
    return {"dateTime": written, "timeZone": moment.zone.key}


def _event_bounds(bounds: EventBounds) -> dict[str, dict[str, Any]]:
    """A new event's ``start``/``end`` objects: dates (end exclusive) or zoned times."""
    if isinstance(bounds, DayBounds):
        return {
            "start": {"date": bounds.first.isoformat()},
            "end": {"date": bounds.after_last.isoformat()},
        }
    return {"start": _zoned(bounds.start), "end": _zoned(bounds.end)}


def _conference_request() -> dict[str, Any]:
    """What asks Google for a Meet link: a fresh id each time, a reused one is the same meeting."""
    return {
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
    }


def _kept_fields(existing: dict[str, Any], **given: Any) -> dict[str, Any]:
    """An update's own fields: each value given replaces, an absent one is kept as read."""
    return {
        name: value if value is not None else existing[name]
        for name, value in given.items()
        if value is not None or name in existing
    }


def _kept_bounds(existing: dict[str, Any], sides: TimedSides) -> dict[str, Any]:
    """An update's bounds in the EXISTING shape: a side left out is sent as it was read.

    An all-day event keeps days: a side it is given names its day.
    """
    keeps_dates = is_all_day(existing)
    bounds: dict[str, Any] = {}
    for name, side in (("start", sides.start), ("end", sides.end)):
        if side is None:
            if name in existing:
                bounds[name] = existing[name]
        elif keeps_dates:
            bounds[name] = {"date": side.local.date().isoformat()}
        else:
            bounds[name] = _zoned(side)
    return bounds


def _switched_bounds(bounds: EventBounds) -> dict[str, dict[str, Any]]:
    """The PATCH that gives an event its shape, the other half of each object cleared."""
    if isinstance(bounds, DayBounds):
        return {
            "start": {"date": bounds.first.isoformat(), "dateTime": None, "timeZone": None},
            "end": {"date": bounds.after_last.isoformat(), "dateTime": None, "timeZone": None},
        }
    return {
        "start": {"date": None, **_zoned(bounds.start)},
        "end": {"date": None, **_zoned(bounds.end)},
    }
