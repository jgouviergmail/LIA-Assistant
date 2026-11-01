"""The calendar of the « Tools » section, by the person's own hand (ADR-369).

Each call opens the account's calendar provider through the door — no session
held while it answers (ADR-304) — and makes its provider calls under the
workbench's failure contract (``provider_call``). A window reads each calendar
on its own, drained up to the published bound: a calendar that fails is named
with its refusal and the others still answer; only when every one fails is the
refusal the answer. A create carries the provider's own idempotency (its key
becomes the event's id, a transaction id or a uid — S1). A change or a deletion
reaches the occurrence it names; where the provider names an occurrence by its
series (CalDAV), a series is refused rather than changed whole. Whether the
attendees are told is the page's choice only where the provider lets it be;
elsewhere a choice is refused, never silently ignored (ADR-184).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.core.markup_detection import looks_like_html
from src.domains.connectors.clients.normalizers.html_text import html_to_text
from src.domains.connectors.clients.protocols import CalendarClientProtocol
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.calendar_times import provider_time, wall_time, window_bounds
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import (
    NOT_SUPPORTED_BY_PROVIDER,
    PROVIDER_UNAVAILABLE,
    refusal_code_of,
    refuse,
)
from src.domains.workbench.features import PROVIDER_FEATURES, WorkbenchFeature, WorkbenchTool
from src.domains.workbench.schemas.calendar import (
    Attendee,
    CalendarEvent,
    CalendarInfo,
    CalendarList,
    CalendarWindow,
    EventChange,
    EventDetail,
    EventsWindow,
    EventWindowQuery,
    NewEvent,
    Response,
)

_TOOL = WorkbenchTool.CALENDAR
#: The answers an attendee gives, as the three normalisers spell them (Google's words).
_RESPONSES: dict[str, Response] = {
    "accepted": "accepted",
    "declined": "declined",
    "tentative": "tentative",
    "needsAction": "needsAction",
}
_WRITABLE_ROLES = frozenset({"owner", "writer"})
#: Calendars read at once over a window (a provider answers a burst with 429).
WINDOW_CONCURRENCY: Final = 4
#: The only links an event may hand the page: an invitation's sender wrote them.
_WEB_SCHEMES: Final = frozenset({"https", "http"})


async def list_calendars(user_id: UUID) -> CalendarList:
    """The account's calendars, hidden ones left out."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: CalendarClientProtocol = opened.client
        async with provider_call(_TOOL, "list_calendars", act=False):
            raw = await client.list_calendars()
    return CalendarList(calendars=[_calendar(item) for item in raw.get("items") or []])


async def read_window(user_id: UUID, zone: ZoneInfo, query: EventWindowQuery) -> EventsWindow:
    """Every calendar asked over the account's days, a few at a time, each answered on its own."""
    time_min, time_max = window_bounds(query.start, query.end, zone)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: CalendarClientProtocol = opened.client
        gate = asyncio.Semaphore(WINDOW_CONCURRENCY)

        async def bounded(calendar_id: str) -> tuple[CalendarWindow, BaseAPIException | None]:
            async with gate:
                return await _window(client, calendar_id, time_min, time_max)

        read = await asyncio.gather(*(bounded(calendar_id) for calendar_id in query.calendar_ids))
    refusals = [refusal for _window_read, refusal in read if refusal is not None]
    if len(refusals) == len(read):
        raise refusals[0]
    return EventsWindow(calendars=[window for window, _refusal in read])


async def read_event(user_id: UUID, calendar_id: str, event_id: str) -> EventDetail:
    """One event, whole."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: CalendarClientProtocol = opened.client
        async with provider_call(_TOOL, "read", act=False):
            raw = await client.get_event(event_id, calendar_id)
    return _detail(raw, calendar_id)


async def create_event(user_id: UUID, request: NewEvent) -> EventDetail:
    """Create an event; the provider's own idempotency makes a replay create nothing."""
    async with open_tool_client(_TOOL, user_id) as opened:
        if request.conference:
            _require(opened.connector_type, WorkbenchFeature.CONFERENCE)
        client: CalendarClientProtocol = opened.client
        start, end = _client_bounds(request.start, request.end, all_day=request.all_day)
        async with provider_call(_TOOL, "create", act=True):
            raw = await client.create_event(
                summary=request.summary,
                start_datetime=start,
                end_datetime=end,
                timezone=request.timezone,
                description=request.description,
                location=request.location,
                attendees=[str(address) for address in request.attendees] or None,
                calendar_id=request.calendar_id,
                add_conference=request.conference,
                idempotency_key=str(request.idempotency_key),
                all_day=request.all_day,
            )
    return _detail(raw, request.calendar_id)


async def update_event(user_id: UUID, request: EventChange) -> EventDetail:
    """Change one event — an occurrence alone; a field left out is kept."""
    async with open_tool_client(_TOOL, user_id) as opened:
        provider = opened.connector_type
        client: CalendarClientProtocol = opened.client
        send_updates = _send_updates(provider, request.notify)
        await _refuse_a_series(client, provider, request.calendar_id, request.event_id)
        start, end = (None, None)
        if request.start is not None and request.end is not None:
            start, end = _client_bounds(request.start, request.end, all_day=bool(request.all_day))
        async with provider_call(_TOOL, "update", act=True):
            raw = await client.update_event(
                request.event_id,
                summary=request.summary,
                start_datetime=start,
                end_datetime=end,
                timezone=request.timezone,
                description=request.description,
                location=request.location,
                attendees=(
                    None
                    if request.attendees is None
                    else [str(address) for address in request.attendees]
                ),
                calendar_id=request.calendar_id,
                all_day=request.all_day,
                send_updates=send_updates,
            )
    return _detail(raw, request.calendar_id)


async def delete_event(
    user_id: UUID, *, calendar_id: str, event_id: str, notify: bool | None
) -> None:
    """Delete one event — an occurrence alone."""
    async with open_tool_client(_TOOL, user_id) as opened:
        provider = opened.connector_type
        client: CalendarClientProtocol = opened.client
        send_updates = _send_updates(provider, notify)
        await _refuse_a_series(client, provider, calendar_id, event_id)
        async with provider_call(_TOOL, "delete", act=True):
            await client.delete_event(event_id, calendar_id, send_updates=send_updates or "all")


async def _window(
    client: CalendarClientProtocol, calendar_id: str, time_min: str, time_max: str
) -> tuple[CalendarWindow, BaseAPIException | None]:
    """One calendar's events over the window, or the refusal that kept it unread."""
    try:
        async with provider_call(_TOOL, "list", act=False):
            raw = await client.list_events_window(
                calendar_id, time_min, time_max, bound=settings.workbench_calendar_window_max_events
            )
    except BaseAPIException as refusal:
        code = refusal_code_of(refusal) or PROVIDER_UNAVAILABLE
        empty = CalendarWindow(
            calendar_id=calendar_id, events=[], truncated=False, skipped=0, error=code
        )
        return empty, refusal
    events: list[CalendarEvent] = []
    skipped = 0
    for item in raw.get("events") or []:
        if item.get("status") == "cancelled":
            continue
        event = _event(item, calendar_id)
        if event is None:
            skipped += 1
        else:
            events.append(event)
    window = CalendarWindow(
        calendar_id=calendar_id,
        events=events,
        truncated=bool(raw.get("truncated")),
        skipped=skipped,
        error=None,
    )
    return window, None


async def _refuse_a_series(
    client: CalendarClientProtocol, provider: ConnectorType, calendar_id: str, event_id: str
) -> None:
    """Refuse, unsent, a change that would reach a whole series.

    Where the provider names an occurrence by its own id, the id IS the
    occurrence. Where it names it by the series' (CalDAV's uid), the event is
    read first: a series is refused, never changed or deleted whole.
    """
    if WorkbenchFeature.OCCURRENCE_EDIT in PROVIDER_FEATURES[provider]:
        return
    async with provider_call(_TOOL, "read", act=False):
        raw = await client.get_event(event_id, calendar_id)
    if raw.get("recurringEventId") or raw.get("recurrence"):
        refuse(NOT_SUPPORTED_BY_PROVIDER)


def _send_updates(provider: ConnectorType, notify: bool | None) -> str | None:
    """Who the provider tells: the page's choice where it can choose, else its own way."""
    if notify is None:
        return None
    if WorkbenchFeature.NOTIFY_ATTENDEES not in PROVIDER_FEATURES[provider]:
        refuse(NOT_SUPPORTED_BY_PROVIDER)
    return "all" if notify else "none"


def _require(provider: ConnectorType, feature: WorkbenchFeature) -> None:
    """Refuse, unsent, a gesture the active provider does not accept."""
    if feature not in PROVIDER_FEATURES[provider]:
        refuse(NOT_SUPPORTED_BY_PROVIDER)


def _client_bounds(start: str, end: str, *, all_day: bool) -> tuple[str, str]:
    """The bounds as the calendar clients take them: days, or wall times to the second."""
    if all_day:
        return start, end
    return (
        wall_time(start).isoformat(timespec="seconds"),
        wall_time(end).isoformat(timespec="seconds"),
    )


def _calendar(raw: Mapping[str, Any]) -> CalendarInfo:
    role = raw.get("accessRole")
    return CalendarInfo(
        id=str(raw.get("id") or ""),
        name=str(raw.get("summaryOverride") or raw.get("summary") or ""),
        color=raw.get("backgroundColor") or None,
        primary=bool(raw.get("primary")),
        # CalDAV publishes no role: its calendars are the account's own.
        writable=role is None or role in _WRITABLE_ROLES,
    )


def _event(raw: Mapping[str, Any], calendar_id: str) -> CalendarEvent | None:
    """The event as a view draws it; None when its times cannot be read."""
    start = provider_time(raw.get("start") or {})
    end = provider_time(raw.get("end") or {})
    if start is None or end is None or start[0] != end[0]:
        return None
    return CalendarEvent(
        id=str(raw.get("id") or ""),
        calendar_id=calendar_id,
        summary=str(raw.get("summary") or ""),
        all_day=start[0],
        start=start[1],
        end=end[1],
        location=raw.get("location") or None,
        recurring=bool(raw.get("recurringEventId") or raw.get("recurrence")),
        conference_url=_conference_url(raw),
    )


def _detail(raw: Mapping[str, Any], calendar_id: str) -> EventDetail:
    event = _event(raw, calendar_id)
    if event is None:
        # The provider answered an event whose times it does not say: nothing to show.
        refuse(PROVIDER_UNAVAILABLE)
    organizer = raw.get("organizer") or {}
    return EventDetail(
        **event.model_dump(),
        description=_description(raw.get("description")),
        attendees=[_attendee(item) for item in raw.get("attendees") or [] if item.get("email")],
        organizer=organizer.get("email") or None,
        link=_web_address(raw.get("htmlLink")),
    )


def _description(value: object) -> str | None:
    """The notes as text: Graph keeps an event's body as HTML, read here once."""
    if not isinstance(value, str) or not value:
        return None
    return html_to_text(value) if looks_like_html(value) else value


def _attendee(raw: Mapping[str, Any]) -> Attendee:
    return Attendee(
        email=str(raw.get("email")),
        name=raw.get("displayName") or None,
        response=_RESPONSES.get(str(raw.get("responseStatus")), "needsAction"),
    )


def _conference_url(raw: Mapping[str, Any]) -> str | None:
    """Meet's link, or the video entry point Graph's Teams link is normalised into."""
    if found := _web_address(raw.get("hangoutLink")):
        return found
    for entry in (raw.get("conferenceData") or {}).get("entryPoints") or []:
        if entry.get("entryPointType") == "video" and (found := _web_address(entry.get("uri"))):
            return found
    return None


def _web_address(value: object) -> str | None:
    """``value`` when it is a web address with a host; never a script or a data URI."""
    if not isinstance(value, str) or not value:
        return None
    parts = urlsplit(value)
    return value if parts.scheme.lower() in _WEB_SCHEMES and parts.netloc else None
