"""
Apple iCloud Calendar client (CalDAV).

Implements the same interface as GoogleCalendarClient for transparent
provider switching via functional_category in ConnectorTool.

Uses caldav.aio (async native) — no asyncio.to_thread() needed.

IMPORTANT: event_by_uid() is broken on iCloud.
Always use calendar.search() + client-side UID filter.

Created: 2026-03-10
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any, Final
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import structlog

from src.core.config import settings
from src.core.read_budget import current_read_owner, source_dav_request, source_http_hooks
from src.core.wall_time import WallTime
from src.domains.connectors.clients.apple_calendar_acts_mixin import AppleCalendarActsMixin
from src.domains.connectors.clients.base_apple_client import BaseAppleClient
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.calendar_answers import PARTSTATS, EventAnswer, NotInvitedError
from src.domains.connectors.clients.calendar_options import EventOptions, apply_ical_options
from src.domains.connectors.clients.event_bounds import (
    BoundsChange,
    DayBounds,
    EventBounds,
    TimedSides,
)
from src.domains.connectors.clients.normalizers.calendar_normalizer import (
    normalize_calendar,
    normalize_vevent,
)
from src.domains.connectors.clients.retry_policy import provider_idempotency_id
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import AppleCredentials

logger = structlog.get_logger(__name__)


class AppleCalendarClient(AppleCalendarActsMixin, BaseAppleClient):
    """
    Apple iCloud Calendar client using CalDAV.

    Interface matches GoogleCalendarClient for transparent provider switching.
    """

    connector_type = ConnectorType.APPLE_CALENDAR

    def __init__(
        self,
        user_id: UUID,
        credentials: AppleCredentials,
        connector_service: Any,
    ) -> None:
        super().__init__(user_id, credentials, connector_service)
        self._dav_client: Any | None = None
        self._principal: Any | None = None
        self._known_addresses: set[str] | None = None

    # =========================================================================
    # CalDAV CONNECTION
    # =========================================================================

    async def _get_principal(self) -> Any:
        """Get or create CalDAV principal (lazy init with discovery)."""
        if self._principal is None:
            try:
                from caldav.aio import get_async_davclient

                if current_read_owner() is not None:
                    # Install before discovery. Fixed Basic auth avoids a replaced session
                    # escaping the hook during CalDAV's automatic negotiation fallback.
                    self._dav_client = await get_async_davclient(
                        url=settings.apple_caldav_url,
                        username=self.credentials.apple_id,
                        password=self.credentials.app_password,
                        probe=False,
                        auth_type="basic",
                        features={"http.multiplexing": False},
                    )
                    if isinstance(self._dav_client.session, httpx.AsyncClient):
                        self._dav_client.session.event_hooks["request"].extend(
                            source_http_hooks(self.user_id)["request"]
                        )
                    else:
                        self._dav_client.session.hooks["pre_request"].append(source_dav_request)
                else:
                    self._dav_client = await get_async_davclient(
                        url=settings.apple_caldav_url,
                        username=self.credentials.apple_id,
                        password=self.credentials.app_password,
                    )
                self._principal = await self._dav_client.get_principal()
            except Exception as e:
                self._check_http_auth_error(getattr(getattr(e, "response", None), "status_code", 0))
                raise
        return self._principal

    @staticmethod
    async def _display_name(cal: Any) -> str | None:
        """Read a calendar's display name through caldav's ONE awaitable door.

        On an async client ``get_display_name()`` returns a coroutine even when
        the value already sits in the props cache (``get_calendars()`` fills it,
        so this never opens a request), and the deprecated ``name`` property
        delegates to it: ``getattr(cal, "name", ...)`` yields a coroutine, not a
        string. Measured on production 2026-09-11: every calendar listing of an
        Apple connector answered 500 (``input_type=coroutine``) and a default
        calendar chosen by name could never be matched. ``str(cal)`` is trapped
        the same way — never stringify an async DAV object.
        """
        name = await cal.get_display_name()
        return str(name) if name else None

    async def _get_calendar(self, calendar_id: str = "primary") -> Any:
        """Get a specific calendar by ID or the default (primary)."""
        principal = await self._get_principal()
        calendars = await principal.get_calendars()
        names = [await self._display_name(c) for c in calendars]

        logger.debug(
            "caldav_calendars_found",
            count=len(calendars),
            calendars=[
                {"name": name or "?", "url": str(c.url)}
                for c, name in zip(calendars, names, strict=True)
            ],
        )

        if not calendars:
            raise ValueError("No calendars found on this iCloud account")

        if calendar_id == "primary":
            return calendars[0]  # First calendar is default

        # Match by URL or display name
        for cal, cal_name in zip(calendars, names, strict=True):
            if calendar_id in (str(cal.url), cal_name):
                return cal

        raise ValueError(f"Calendar '{calendar_id}' not found")

    # =========================================================================
    # PUBLIC INTERFACE (matches GoogleCalendarClient exactly)
    # =========================================================================

    async def list_calendars(
        self, max_results: int = 100, show_hidden: bool = False
    ) -> dict[str, Any]:
        """List all calendars."""
        return await self._execute_with_retry(
            "list_calendars",
            self._list_calendars_impl,
            max_results,
            show_hidden,
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
        """List events in a calendar."""
        return await self._execute_with_retry(
            "list_events",
            self._list_events_impl,
            time_min,
            time_max,
            max_results,
            calendar_id,
            query,
            fields,
        )

    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get a single event by UID."""
        return await self._execute_with_retry(
            "get_event",
            self._get_event_impl,
            event_id,
            calendar_id,
            fields,
        )

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
        """Create a new event, at the bounds it is given (``event_bounds``, ADR-380).

        ``add_conference`` is accepted for provider parity but ignored:
        CalDAV/iCloud has no conference-creation concept (graceful
        degradation — the event is created without a video link).

        The event's ``uid`` is fixed BEFORE the retry loop, derived from the effect's
        ``idempotency_key`` (ADR-263): the object's URL derives from it, so a resend
        writes the same object again — caldav mints a new uid per save otherwise, and
        a resent create was a second event (S1).
        """
        if add_conference:
            logger.debug(
                "apple_calendar_conference_not_supported",
                user_id=str(self.user_id),
            )
        return await self._execute_with_retry(
            "create_event",
            self._create_event_impl,
            summary,
            bounds,
            description,
            location,
            attendees,
            calendar_id,
            uid=provider_idempotency_id(idempotency_key or uuid4().hex, "apple"),
            options=options,
        )

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
        """Update an existing event (full PUT, no PATCH on iCloud).

        ``send_updates`` is unused: CalDAV leaves scheduling to the server (ADR-369).
        """
        return await self._execute_with_retry(
            "update_event",
            self._update_event_impl,
            event_id,
            summary,
            bounds,
            description,
            location,
            attendees,
            calendar_id,
            options=options,
        )

    async def list_events_window(
        self, calendar_id: str, time_min: str, time_max: str, *, bound: int
    ) -> dict[str, Any]:
        """Every event of a window — occurrences expanded — up to ``bound`` (ADR-369).

        One REPORT; the server (or caldav) expands the recurrences, and the
        answer is cut at ``bound`` in start order, saying so.

        Returns:
            ``{"events": [...], "truncated": bool}``.
        """
        return await self._execute_with_retry(
            "list_events_window", self._events_window_impl, calendar_id, time_min, time_max, bound
        )

    async def respond_to_event(
        self, event_id: str, response: EventAnswer, calendar_id: str = "primary"
    ) -> dict[str, Any]:
        """Answer an invitation: the person's own ``PARTSTAT``, the server tells the organiser.

        Args:
            event_id: The event's UID.
            response: The answer.
            calendar_id: Its calendar.

        Returns:
            The event as it is now.

        Raises:
            NotInvitedError: No attendee of this event is an address of the account.
            ValueError: The calendar holds no such event.
        """
        return await self._execute_with_retry(
            "respond_to_event",
            self._respond_impl,
            event_id,
            response,
            calendar_id,
            max_retries=0,
        )

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> dict[str, Any]:
        """Delete an event."""
        return await self._execute_with_retry(
            "delete_event",
            self._delete_event_impl,
            event_id,
            calendar_id,
            send_updates,
        )

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _find_event_by_uid(self, calendar: Any, event_id: str) -> Any:
        """
        Search for a CalDAV event by UID.

        IMPORTANT: event_by_uid() is broken on iCloud.
        We use search() + client-side UID filtering instead.

        Returns the raw caldav event object or None.
        """
        now = datetime.now(tz=UTC)
        events = await calendar.search(
            start=now - timedelta(days=365),
            end=now + timedelta(days=365),
            event=True,
        )

        for event in events:
            try:
                vevent = event.vobject_instance.vevent
                uid = str(vevent.uid.value) if hasattr(vevent, "uid") else ""
                if uid == event_id:
                    return event
            except Exception:
                continue

        return None

    # =========================================================================
    # IMPLEMENTATION
    # =========================================================================

    async def _list_calendars_impl(self, max_results: int, show_hidden: bool) -> dict[str, Any]:
        """List all CalDAV calendars."""
        principal = await self._get_principal()
        calendars = await principal.get_calendars()

        items = []
        for i, cal in enumerate(calendars[:max_results]):
            normalized = normalize_calendar(cal, await self._display_name(cal))
            if i == 0:
                normalized["primary"] = True
            items.append(normalized)

        return {"items": items}

    async def _list_events_impl(
        self,
        time_min: str | None,
        time_max: str | None,
        max_results: int,
        calendar_id: str,
        query: str | None,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """List events via CalDAV REPORT."""
        # Enforce the global per-request volumetry ceiling (centralized cap).
        max_results = apply_max_items_limit(max_results)

        calendar = await self._get_calendar(calendar_id)

        # Parse date range
        search_kwargs: dict[str, Any] = {"event": True}
        if time_min:
            search_kwargs["start"] = _parse_iso_datetime(time_min)
        if time_max:
            search_kwargs["end"] = _parse_iso_datetime(time_max)

        # Default range if not specified
        if "start" not in search_kwargs and "end" not in search_kwargs:
            now = datetime.now(tz=UTC)
            search_kwargs["start"] = now - timedelta(days=30)
            search_kwargs["end"] = now + timedelta(days=90)

        logger.debug(
            "caldav_search_params",
            calendar_url=str(calendar.url),
            calendar_name=await self._display_name(calendar) or "unknown",
            search_kwargs={k: str(v) for k, v in search_kwargs.items()},
        )
        events = await calendar.search(**search_kwargs)
        logger.debug(
            "caldav_search_results",
            events_count=len(events) if events else 0,
        )

        items = []
        for event in events:
            try:
                normalized = normalize_vevent(event)

                # Client-side query filtering (CalDAV search doesn't support text search)
                if query:
                    query_lower = query.lower()
                    summary = normalized.get("summary", "").lower()
                    description = normalized.get("description", "").lower()
                    if query_lower not in summary and query_lower not in description:
                        continue

                items.append(normalized)
            except Exception as e:
                logger.warning(
                    "apple_calendar_event_parse_error",
                    error=str(e),
                )

        # Sort by start time (most recent first)
        items.sort(
            key=lambda x: x.get("start", {}).get("dateTime", x.get("start", {}).get("date", "")),
            reverse=False,  # Ascending chronological (matches Google Calendar API)
        )

        return {"items": items[:max_results]}

    async def _events_window_impl(
        self, calendar_id: str, time_min: str, time_max: str, bound: int
    ) -> dict[str, Any]:
        """One expanded REPORT over the window, cut at ``bound``."""
        calendar = await self._get_calendar(calendar_id)
        found = await calendar.search(
            start=_parse_iso_datetime(time_min),
            end=_parse_iso_datetime(time_max),
            event=True,
            expand=True,
        )
        events: list[dict[str, Any]] = []
        for event in found or []:
            try:
                events.append(normalize_vevent(event))
            except Exception as error:
                logger.warning("apple_calendar_event_parse_error", error_type=type(error).__name__)
        events.sort(key=_start_instant)
        await self._mark_own_organizer(events)
        return {"events": events[:bound], "truncated": len(events) > bound}

    async def _get_event_impl(
        self,
        event_id: str,
        calendar_id: str,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        """Get a single event by UID."""
        calendar = await self._get_calendar(calendar_id)
        event = await self._find_event_by_uid(calendar, event_id)

        if event is None:
            raise ValueError(f"Event '{event_id}' not found in calendar")

        return await self._with_own_attendee(normalize_vevent(event))

    async def _create_event_impl(
        self,
        summary: str,
        bounds: EventBounds,
        description: str | None,
        location: str | None,
        attendees: list[str] | None,
        calendar_id: str,
        *,
        uid: str,
        options: EventOptions | None = None,
    ) -> dict[str, Any]:
        """Create a new event via CalDAV, under the ``uid`` its caller fixed."""
        calendar = await self._get_calendar(calendar_id)
        dtstart, dtend = _ical_values(bounds)

        kwargs: dict[str, Any] = {
            "uid": uid,
            "dtstart": dtstart,
            "dtend": dtend,
            "summary": summary,
        }
        if description:
            kwargs["description"] = description
        if location:
            kwargs["location"] = location

        event = await calendar.save_event(**kwargs)

        # What save_event takes no argument for is written on the VEVENT afterwards.
        if (attendees or options) and event.vobject_instance:
            vevent = event.vobject_instance.vevent
            for email in attendees or []:
                att = vevent.add("attendee")
                att.value = f"mailto:{email}"
            apply_ical_options(vevent, options or EventOptions())
            await event.save()

        return normalize_vevent(event)

    async def _mark_own_organizer(self, events: list[dict[str, Any]]) -> None:
        """Say which events the person organises, in Google's word: iCloud names no such thing."""
        organizers = [event["organizer"] for event in events if "organizer" in event]
        if not organizers:
            return
        if self._known_addresses is None:
            try:
                self._known_addresses = await self._own_addresses()
            except Exception as error:
                # The word only sorts a meeting between two lists: the sign-in still answers.
                logger.info("apple_calendar_addresses_unread", error_type=type(error).__name__)
                self._known_addresses = {self.credentials.apple_id.casefold()}
        for organizer in organizers:
            if str(organizer.get("email") or "").casefold() in self._known_addresses:
                organizer["self"] = True

    async def _own_addresses(self) -> set[str]:
        """The addresses the server knows the account by, in lower case, the sign-in's first."""
        principal = await self._get_principal()
        known = await principal.calendar_user_address_set()
        cleaned = {str(item).removeprefix("mailto:").casefold() for item in known if item}
        return {self.credentials.apple_id.casefold(), *cleaned}

    async def _respond_impl(
        self, event_id: str, response: EventAnswer, calendar_id: str
    ) -> dict[str, Any]:
        """Write the answer on the attendee the account is, and on no other."""
        calendar = await self._get_calendar(calendar_id)
        target = await self._find_event_by_uid(calendar, event_id)
        if target is None:
            raise ValueError(f"Event '{event_id}' not found")
        addresses = {address.casefold() for address in await self._own_addresses()}
        vevent = target.vobject_instance.vevent
        mine = [item for item in _attendees_of(vevent) if _address_of(item) in addresses]
        if not mine:
            raise NotInvitedError
        for attendee in mine:
            attendee.params["PARTSTAT"] = [PARTSTATS[response]]
            attendee.params.pop("RSVP", None)
        await target.save()
        return await self._with_own_attendee(normalize_vevent(target))

    async def _with_own_attendee(self, event: dict[str, Any]) -> dict[str, Any]:
        """Marks the attendee the account is, as Google does: only the server knows its names."""
        attendees = event.get("attendees") or []
        if not attendees:
            return event
        addresses = await self._own_addresses()
        for attendee in attendees:
            if str(attendee.get("email") or "").casefold() in addresses:
                attendee["self"] = True
        return event

    async def _update_event_impl(
        self,
        event_id: str,
        summary: str | None,
        bounds: BoundsChange | None,
        description: str | None,
        location: str | None,
        attendees: list[str] | None,
        calendar_id: str,
        *,
        options: EventOptions | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing event (full PUT, no PATCH on iCloud).

        Gets the existing event, modifies fields, then saves.
        """
        calendar = await self._get_calendar(calendar_id)
        target_event = await self._find_event_by_uid(calendar, event_id)

        if target_event is None:
            raise ValueError(f"Event '{event_id}' not found for update")

        vevent = target_event.vobject_instance.vevent

        # Update fields (only non-None values)
        if summary is not None:
            vevent.summary.value = summary

        if isinstance(bounds, TimedSides):
            # The event keeps its shape: a side given replaces, a side left out stays.
            if bounds.start is not None:
                _write(vevent, "dtstart", _ical_time(bounds.start))
            if bounds.end is not None:
                _write_end(vevent, _ical_time(bounds.end))
        elif bounds is not None:
            # A whole pair gives the event its shape (ADR-369): dates, or zoned times.
            _set_bounds(vevent, *_ical_values(bounds))

        _apply_text_fields(vevent, description, location, attendees)
        apply_ical_options(vevent, options or EventOptions())

        await target_event.save()
        return normalize_vevent(target_event)

    async def _delete_event_impl(
        self,
        event_id: str,
        calendar_id: str,
        send_updates: str,
    ) -> dict[str, Any]:
        """Delete an event via CalDAV."""
        calendar = await self._get_calendar(calendar_id)
        event = await self._find_event_by_uid(calendar, event_id)

        if event is None:
            raise ValueError(f"Event '{event_id}' not found for deletion")

        await event.delete()
        return {
            "success": True,
            "event_id": event_id,
            "message": f"Event '{event_id}' deleted successfully",
        }

    # =========================================================================
    # CLEANUP
    # =========================================================================

    async def close(self) -> None:
        """Close CalDAV client connection."""
        if self._dav_client:
            try:
                await self._dav_client.close()
            except Exception as e:
                logger.debug("caldav_close_error", error=str(e))
            self._dav_client = None
            self._principal = None


class _IcalZone(ZoneInfo):
    """A zone as iCalendar must name it: by its IANA key.

    vobject, which writes every UPDATE, names a zone by its ``tzid`` and, finding
    none, by its winter abbreviation — « EST » for New York, which is ANOTHER
    zone's name: a server that knows it places a summer event an hour late.
    caldav's own writer, which writes every create, reads ``key`` and always
    wrote the name.
    """

    @property
    def tzid(self) -> str:
        """The name vobject writes as the zone's TZID."""
        return self.key


#: UTC as BOTH writers render ``…Z`` (vobject cannot name ``datetime.UTC``).
_ICAL_UTC: Final = ZoneInfo("UTC")
#: What an old value leaves on its line: its shape, its zone, and the zone vobject
#: sets aside on reading — which it would write back as a TZID on a time in UTC.
_STALE_PARAMS: Final = ("VALUE", "TZID", "X-VOBJ-ORIGINAL-TZID")


def _ical_time(moment: WallTime) -> datetime:
    """A DATE-TIME for both writers: the wall time, under its zone's own name.

    An hour the zone's clocks skip or show twice is said in UTC: RFC 5545 and its
    readers do not agree on which instant such a local time is.
    """
    if not moment.zone_suffices:
        return moment.instant().astimezone(_ICAL_UTC)
    return moment.local.replace(tzinfo=_IcalZone(moment.zone.key))


def _ical_values(bounds: EventBounds) -> tuple[date | datetime, date | datetime]:
    """DTSTART/DTEND values: dates (``VALUE=DATE``, end exclusive) or times in their zone."""
    if isinstance(bounds, DayBounds):
        return bounds.first, bounds.after_last
    return _ical_time(bounds.start), _ical_time(bounds.end)


def _parse_iso_datetime(dt_str: str) -> datetime:
    """Parse a SEARCH bound: an ISO 8601 instant, read as UTC when it names no offset.

    An event's own times never come through here: they are wall times that
    travel with their zone (``event_bounds``).

    Args:
        dt_str: ISO 8601 datetime string (with or without offset/Z).

    Returns:
        The instant, timezone-aware.
    """
    # Normalize trailing Z to +00:00 so strptime %z handles it as UTC
    normalized = dt_str.replace("Z", "+00:00") if dt_str.endswith("Z") else dt_str
    dt: datetime | None = None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(normalized, fmt)
            break
        except ValueError:
            continue
    if dt is None:
        # Fallback: use dateutil (may also return a naive datetime)
        from dateutil.parser import parse

        dt = parse(dt_str)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _write(vevent: Any, name: str, value: date | datetime) -> None:
    """Write DTSTART or DTEND: what the old value left on its line goes with it."""
    line = getattr(vevent, name, None) or vevent.add(name)
    for stale in _STALE_PARAMS:
        line.params.pop(stale, None)
    line.value = value


def _set_bounds(vevent: Any, start: date | datetime, end: date | datetime) -> None:
    """Write DTSTART/DTEND of a new shape."""
    _write(vevent, "dtstart", start)
    _write(vevent, "dtend", end)
    _drop_duration(vevent)


def _write_end(vevent: Any, end: datetime) -> None:
    """Write DTEND, added when the event had none (it may have ended by a DURATION)."""
    _write(vevent, "dtend", end)
    _drop_duration(vevent)


def _drop_duration(vevent: Any) -> None:
    """An end is now a DTEND: a DURATION beside it is invalid (RFC 5545) — vobject refuses it."""
    duration = getattr(vevent, "duration", None)
    if duration is not None:
        vevent.remove(duration)


def _start_instant(event: dict[str, Any]) -> datetime:
    """When a normalised event starts, as an instant (offsets compared, not spelled).

    An all-day event starts at its day's midnight UTC; an unreadable start sorts last.
    """
    start = event.get("start") or {}
    value = str(start.get("dateTime") or start.get("date") or "")
    try:
        moment = (
            datetime.fromisoformat(value)
            if "T" in value
            else datetime.combine(date.fromisoformat(value), datetime.min.time())
        )
    except ValueError:
        return datetime.max.replace(tzinfo=UTC)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _attendees_of(vevent: Any) -> list[Any]:
    """The event's attendees, none when it names nobody."""
    return list(getattr(vevent, "attendee_list", ()) or ())


def _address_of(attendee: Any) -> str:
    """An attendee's address, in lower case, whatever the case of its scheme."""
    value = str(getattr(attendee, "value", ""))
    return value.split(":", 1)[-1].casefold()


def _apply_text_fields(
    vevent: Any, description: str | None, location: str | None, attendees: list[str] | None
) -> None:
    """Write the given text fields into a VEVENT; None keeps a field as it is."""
    for name, value in (("description", description), ("location", location)):
        if value is None:
            continue
        line = getattr(vevent, name, None)
        if line is not None:
            line.value = value
        else:
            vevent.add(name).value = value
    if attendees is None:
        return
    # The attendee list given replaces the whole list.
    while hasattr(vevent, "attendee"):
        vevent.remove(vevent.attendee)
    for email in attendees:
        vevent.add("attendee").value = f"mailto:{email}"
