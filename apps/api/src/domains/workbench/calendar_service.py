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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.constants import WORKBENCH_EVENT_SEARCH_MAX, WORKBENCH_EVENT_SEARCH_SPAN_DAYS
from src.core.exceptions import BaseAPIException
from src.core.markup_detection import looks_like_html
from src.core.recurrence import RecurrenceSpec
from src.core.validators import validate_timezone
from src.domains.connectors.clients.calendar_answers import own_answer
from src.domains.connectors.clients.calendar_options import EventOptions
from src.domains.connectors.clients.event_recurrence import (
    first_day_of,
    is_series,
    series_bounds,
)
from src.domains.connectors.clients.normalizers.html_text import html_to_text
from src.domains.connectors.clients.protocols import (
    CalendarAnswerProtocol,
    CalendarClientProtocol,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.owner_defaults import CALENDAR
from src.domains.connectors.preferences.resolver import is_preferred
from src.domains.workbench.calendar_series import spec_from
from src.domains.workbench.calendar_times import provider_time, wall_time, window_bounds
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import (
    INVALID_REQUEST,
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
    EventInvitationAnswer,
    EventScope,
    EventSearch,
    EventSearchQuery,
    EventsWindow,
    EventWindowQuery,
    NewEvent,
    Response,
)

_TOOL = WorkbenchTool.CALENDAR
#: The answers an attendee gives, as the three normalisers spell them (Google's words).
#: How a provider keeps an instant: a zone nobody chose.
_KEPT_IN: Final = frozenset({"UTC", "Etc/UTC", "GMT", "Etc/GMT"})
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
    """The account's calendars, hidden ones left out, the settings' default named."""
    async with open_tool_client(_TOOL, user_id, container=CALENDAR) as opened:
        client: CalendarClientProtocol = opened.client
        async with provider_call(_TOOL, "list_calendars", act=False):
            raw = await client.list_calendars()
    preferred = opened.preferred_name
    return CalendarList(
        calendars=[calendar_info(item, preferred) for item in raw.get("items") or []]
    )


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


async def search_events(user_id: UUID, zone: ZoneInfo, query: EventSearchQuery) -> EventSearch:
    """Words looked for around today in every calendar asked, a few at a time.

    Each provider searches in its own way: what it understands by a word is its own.
    A calendar that fails is named beside what the others found.
    """
    today = datetime.now(zone).date()
    span = timedelta(days=WORKBENCH_EVENT_SEARCH_SPAN_DAYS)
    time_min, time_max = window_bounds(today - span, today + span, zone)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: CalendarClientProtocol = opened.client
        gate = asyncio.Semaphore(WINDOW_CONCURRENCY)

        async def bounded(calendar_id: str) -> tuple[list[CalendarEvent], BaseAPIException | None]:
            async with gate:
                return await _found(client, calendar_id, query.q, time_min, time_max)

        read = await asyncio.gather(*(bounded(calendar_id) for calendar_id in query.calendar_ids))
    refusals = [refusal for _, refusal in read if refusal is not None]
    if len(refusals) == len(read):
        raise refusals[0]
    found = sorted((event for events, _ in read for event in events), key=lambda item: item.start)
    return EventSearch(
        events=found[:WORKBENCH_EVENT_SEARCH_MAX],
        truncated=len(found) > WORKBENCH_EVENT_SEARCH_MAX,
        failed=[
            calendar_id
            for calendar_id, (_, refusal) in zip(query.calendar_ids, read, strict=True)
            if refusal is not None
        ],
    )


async def read_event(user_id: UUID, calendar_id: str, event_id: str) -> EventDetail:
    """One event, whole."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: CalendarClientProtocol = opened.client
        async with provider_call(_TOOL, "read", act=False):
            raw = await client.get_event(event_id, calendar_id)
    return event_detail(raw, calendar_id)


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
                options=_options(request, _new_series(request)),
            )
    return event_detail(raw, request.calendar_id)


def _new_series(request: NewEvent) -> RecurrenceSpec | None:
    """The rule of a new event, from its own first day."""
    if request.recurrence is None:
        return None
    return spec_from(
        request.recurrence, date.fromisoformat(request.start[:10]), request.timezone or "UTC"
    )


async def update_event(user_id: UUID, request: EventChange) -> EventDetail:
    """Change one event — an occurrence alone unless a whole series is asked for."""
    async with open_tool_client(_TOOL, user_id) as opened:
        provider = opened.connector_type
        client: CalendarClientProtocol = opened.client
        send_updates = _send_updates(provider, request.notify)
        if request.conference:
            _require(provider, WorkbenchFeature.CONFERENCE)
        reach = await _reach(client, provider, request)
        async with provider_call(_TOOL, "update", act=True):
            raw = await client.update_event(
                reach.event_id,
                summary=request.summary,
                start_datetime=reach.start,
                end_datetime=reach.end,
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
                add_conference=request.conference,
                options=_options(request, reach.spec, all_day=reach.all_day),
            )
    return event_detail(raw, request.calendar_id)


@dataclass(frozen=True, slots=True)
class _Reach:
    """What a change reaches: the event, its bounds, and a series' rule from its first day."""

    event_id: str
    start: str | None = None
    end: str | None = None
    spec: RecurrenceSpec | None = None
    all_day: bool = False


async def _reach(
    client: CalendarClientProtocol, provider: ConnectorType, request: EventChange
) -> _Reach:
    """What a change reaches, a whole series read first."""
    if request.scope == "series":
        master = await _master_of(client, request.calendar_id, request.event_id)
        return _series_reach(master, request)
    await _refuse_a_series(client, provider, request.calendar_id, request.event_id)
    all_day = bool(request.all_day)
    if request.start is None or request.end is None:
        return _Reach(request.event_id, all_day=all_day)
    start, end = _client_bounds(request.start, request.end, all_day=all_day)
    return _Reach(request.event_id, start, end, all_day=all_day)


def _series_reach(master: Mapping[str, Any], request: EventChange) -> _Reach:
    """A series' bounds and rule, from its first day; a title alone reads none."""
    target = str(master.get("id") or request.event_id)
    # A rule sent alone says nothing of days: the series does.
    all_day = bool((master.get("start") or {}).get("date"))
    moves = request.start is not None and request.end is not None
    if not moves and request.recurrence is None:
        return _Reach(target, all_day=all_day)
    zone = request.timezone or "UTC"
    first_day = first_day_of(master, zone)
    if first_day is None:
        refuse(INVALID_REQUEST)
    start, end = None, None
    if moves:
        start, end = series_bounds(
            first_day, str(request.start), str(request.end), all_day=bool(request.all_day)
        )
    spec = spec_from(request.recurrence, first_day, zone) if request.recurrence else None
    return _Reach(target, start, end, spec, all_day=all_day)


async def _master_of(
    client: CalendarClientProtocol, calendar_id: str, event_id: str
) -> Mapping[str, Any]:
    """The event a series is held by; what is no series is refused unsent."""
    async with provider_call(_TOOL, "read", act=False):
        raw = await client.get_event(event_id, calendar_id)
        series_id = raw.get("recurringEventId")
        if series_id and series_id != event_id:
            return {"id": series_id, **await client.get_event(series_id, calendar_id)}
    if not is_series(raw):
        refuse(INVALID_REQUEST)
    return {"id": event_id, **raw}


async def answer_event(user_id: UUID, request: EventInvitationAnswer) -> None:
    """Answer an invitation: the person's own line, the organiser told."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: CalendarAnswerProtocol = opened.client
        async with provider_call(_TOOL, "answer", act=True):
            await client.respond_to_event(request.event_id, request.response, request.calendar_id)


async def delete_event(
    user_id: UUID,
    *,
    calendar_id: str,
    event_id: str,
    notify: bool | None,
    scope: EventScope = "occurrence",
) -> None:
    """Delete one event — an occurrence alone unless a whole series is asked for."""
    async with open_tool_client(_TOOL, user_id) as opened:
        provider = opened.connector_type
        client: CalendarClientProtocol = opened.client
        send_updates = _send_updates(provider, notify)
        target = event_id
        if scope == "series":
            target = str((await _master_of(client, calendar_id, event_id)).get("id") or event_id)
        else:
            await _refuse_a_series(client, provider, calendar_id, event_id)
        async with provider_call(_TOOL, "delete", act=True):
            await client.delete_event(target, calendar_id, send_updates=send_updates or "all")


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


async def _found(
    client: CalendarClientProtocol, calendar_id: str, words: str, time_min: str, time_max: str
) -> tuple[list[CalendarEvent], BaseAPIException | None]:
    """What one calendar found, or the refusal that kept it unread."""
    try:
        async with provider_call(_TOOL, "search", act=False):
            raw = await client.list_events(
                time_min=time_min,
                time_max=time_max,
                max_results=WORKBENCH_EVENT_SEARCH_MAX,
                calendar_id=calendar_id,
                query=words,
            )
    except BaseAPIException as refusal:
        return [], refusal
    drawn = (
        _event(item, calendar_id)
        for item in raw.get("items") or []
        if item.get("status") != "cancelled"
    )
    return [event for event in drawn if event is not None], None


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


def calendar_info(raw: Mapping[str, Any], preferred: str | None) -> CalendarInfo:
    """A calendar as the page names it.

    Args:
        raw: The calendar, as a provider's listing gives it.
        preferred: The name the settings chose for the default one.

    Returns:
        The calendar in the page's words.
    """
    role = raw.get("accessRole")
    return CalendarInfo(
        id=str(raw.get("id") or ""),
        name=str(raw.get("summaryOverride") or raw.get("summary") or ""),
        color=raw.get("backgroundColor") or None,
        primary=bool(raw.get("primary")),
        default=is_preferred(preferred, raw.get("summary"), raw.get("id")),
        # CalDAV publishes no role: its calendars are the account's own.
        writable=role is None or role in _WRITABLE_ROLES,
        manageable=_manageable(raw),
    )


def _manageable(raw: Mapping[str, Any]) -> bool:
    """Whether the person may rename and delete it: their own, never the account's main one."""
    if raw.get("primary"):
        return False
    if "removable" in raw:
        return bool(raw["removable"])
    return raw.get("accessRole") in (None, "owner")


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


def event_detail(raw: Mapping[str, Any], calendar_id: str) -> EventDetail:
    """One event, whole, as the page reads it.

    Args:
        raw: The event, as a normaliser gives it.
        calendar_id: Its calendar.

    Returns:
        The event in the page's words.
    """
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
        reminder_minutes=_reminder(raw),
        busy=raw.get("transparency") != "transparent",
        private=raw.get("visibility") == "private",
        zone=_own_zone(raw),
        my_response=_own_response(raw),
    )


def _options(
    request: NewEvent | EventChange,
    recurrence: RecurrenceSpec | None = None,
    *,
    all_day: bool | None = None,
) -> EventOptions:
    """What the form said of the event beyond its time."""
    return EventOptions(
        reminder_minutes=request.reminder_minutes,
        busy=request.busy,
        private=request.private,
        recurrence=recurrence,
        zone=request.timezone or "UTC",
        all_day=bool(request.all_day) if all_day is None else all_day,
    )


def _reminder(raw: Mapping[str, Any]) -> int | None:
    """The event's own reminder: the two normalisers' figure, or Google's earliest override."""
    if raw.get("reminderMinutes") is not None:
        return int(raw["reminderMinutes"])
    overrides = (raw.get("reminders") or {}).get("overrides") or []
    minutes = [item["minutes"] for item in overrides if isinstance(item.get("minutes"), int)]
    return max(minutes) if minutes else None


def _own_zone(raw: Mapping[str, Any]) -> str | None:
    """The zone the event was set in: Graph says it beside its times, the others on them.

    A day has none, though Graph keeps one on an all-day event.
    """
    start = raw.get("start") or {}
    zone = raw.get("ownZone") or start.get("timeZone")
    if "date" in start or not isinstance(zone, str) or zone in _KEPT_IN:
        return None
    return zone if validate_timezone(zone) else None


def _own_response(raw: Mapping[str, Any]) -> Response | None:
    """What the person answered, in the page's words; None when nothing invites them."""
    answer = own_answer(raw)
    return None if answer is None else _RESPONSES.get(answer, "needsAction")


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
