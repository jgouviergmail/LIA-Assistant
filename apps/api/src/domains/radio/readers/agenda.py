"""The listener's calendar, for the journal's « done » and « ahead » parts (ADR-324 decision 41).

The day ahead comes from the Today Briefing's cache (``personal.py``); what the
journal's noon and evening editions add is read here, live, from the listener's
active calendar (the briefing's own door, ``open_active_calendar``): the appointments
that TOOK PLACE today — started today and over — and the week ahead, from tomorrow.
An all-day event is never « done » before its day is; an appointment the day already
tells keeps its key, so the week ahead never retells it (``personal_facts``).

Every instant is read by ``briefing.formatters.event_instant`` — the ONE reading of
the three providers' shapes — and written on the listener's clock. The client is
open for the length of the read and closed before it returns (ADR-304).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo
from typing import Any, Final
from uuid import UUID

from src.domains.briefing.constants import ERROR_CODE_CONNECTOR_OAUTH_EXPIRED
from src.domains.briefing.exceptions import ConnectorAccessError
from src.domains.briefing.formatters import event_instant
from src.domains.connectors.active_client import ClientUnavailable
from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar
from src.domains.radio.facts import FactKind, Sensitivity, local_day_text, local_time_text
from src.domains.radio.personal import (
    MAX_PER_SOURCE,
    JournalPart,
    PersonalDraft,
    PersonalSource,
    digest,
)

#: How far the week ahead reaches, in local days from tomorrow.
AHEAD_DAYS: Final[int] = 7
#: How many events one window is read for (the bound is applied after the filter).
_SCAN_EVENTS: Final[int] = 30


@dataclass(frozen=True, slots=True)
class EventLine:
    """What the radio reads of one event.

    Attributes:
        id: The provider's id, if any.
        title: Its title.
        start: When it starts (aware).
        end: When it ends (aware), if the provider says.
        all_day: Whether it fills its day rather than hours.
        location: Where, if the provider says.
    """

    id: str | None
    title: str
    start: datetime
    end: datetime | None
    all_day: bool
    location: str | None


def event_line(raw: Mapping[str, Any], tz: tzinfo) -> EventLine | None:
    """One provider event as the radio reads it, or ``None`` when it has no start."""
    start_field = raw.get("start")
    start = event_instant(start_field, tz)
    if start is None:
        return None
    all_day = (
        isinstance(start_field, dict)
        and bool(start_field.get("date"))
        and not bool(start_field.get("dateTime"))
    )
    event_id = raw.get("id")
    location = raw.get("location")
    return EventLine(
        id=str(event_id) if event_id else None,
        title=str(raw.get("summary") or "").strip() or "Untitled",
        start=start,
        end=event_instant(raw.get("end"), tz),
        all_day=all_day,
        location=str(location).strip() if isinstance(location, str) and location.strip() else None,
    )


def _key(prefix: str, line: EventLine) -> str:
    return f"{prefix}{line.id or digest(line.title, line.start.isoformat())}"


def agenda_done_drafts(
    lines: Sequence[EventLine], *, now: datetime, tz: tzinfo
) -> list[PersonalDraft]:
    """The appointments that took place today: started today, over by now.

    Args:
        lines: The events read for the day so far.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        One draft per finished appointment, in the order given.
    """
    local_now = now.astimezone(tz)
    drafts: list[PersonalDraft] = []
    for line in lines:
        start = line.start.astimezone(tz)
        end = line.end.astimezone(tz) if line.end is not None else None
        if line.all_day or start.date() != local_now.date() or (end or start) > local_now:
            continue
        text = f'Appointment "{line.title}" took place today from {start:%H:%M}'
        if end is not None:
            text += f" to {end:%H:%M}"
        if line.location:
            text += f", at {line.location}"
        drafts.append(
            PersonalDraft(
                FactKind.EVENT,
                text,
                _key("done:event:", line),
                Sensitivity.PERSONAL,
                JournalPart.DONE,
            )
        )
    return drafts


def agenda_ahead_drafts(
    lines: Sequence[EventLine], *, now: datetime, tz: tzinfo
) -> list[PersonalDraft]:
    """The appointments of the week ahead, from tomorrow.

    Args:
        lines: The events read for the week.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        One draft per appointment starting between tomorrow and ``AHEAD_DAYS`` days on.
    """
    today = now.astimezone(tz).date()
    first, last = today + timedelta(days=1), today + timedelta(days=AHEAD_DAYS)
    drafts: list[PersonalDraft] = []
    for line in lines:
        start = line.start.astimezone(tz)
        if not first <= start.date() <= last:
            continue
        when = f"{local_day_text(start)} (all day)" if line.all_day else local_time_text(start)
        text = f'Appointment "{line.title}" on {when}'
        end = line.end.astimezone(tz) if line.end is not None else None
        if end is not None and not line.all_day and end.date() == start.date():
            text += f" until {end:%H:%M}"
        if line.location:
            text += f", at {line.location}"
        # The day's own key (``event:<id>``): an appointment the day tells is one fact.
        drafts.append(
            PersonalDraft(
                FactKind.EVENT, text, _key("event:", line), Sensitivity.PERSONAL, JournalPart.AHEAD
            )
        )
    return drafts


async def _events(user_id: UUID, *, time_min: datetime, time_max: datetime) -> list[dict[str, Any]]:
    """The listener's events over a window, from their active calendar.

    Raises:
        ConnectorAccessError: The calendar is connected but its credentials failed —
            a failure to record, never « nothing planned ».
    """
    async with open_active_calendar(user_id) as access:
        if access is ClientUnavailable.NO_CREDENTIALS:
            raise ConnectorAccessError(
                "calendar", ERROR_CODE_CONNECTOR_OAUTH_EXPIRED, "credentials refused"
            )
        if not isinstance(access, CalendarAccess):
            return []  # no calendar connected: nothing to read
        result = await access.client.list_events(
            time_min=time_min.isoformat(),
            time_max=time_max.isoformat(),
            max_results=_SCAN_EVENTS,
            calendar_id=access.calendar_id,
        )
    return [item for item in (result.get("items") or []) if isinstance(item, dict)]


def _local_midnight(now: datetime, tz: tzinfo, *, days: int = 0) -> datetime:
    return datetime.combine(now.astimezone(tz).date() + timedelta(days=days), time(), tzinfo=tz)


async def read_agenda_done(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The appointments that took place today, read from the listener's calendar."""
    raw = await _events(user_id, time_min=_local_midnight(now, tz), time_max=now)
    lines = [line for item in raw if (line := event_line(item, tz)) is not None]
    return agenda_done_drafts(lines, now=now, tz=tz)[: MAX_PER_SOURCE[PersonalSource.AGENDA]]


async def read_agenda_ahead(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The appointments of the week ahead, from tomorrow, read from the listener's calendar."""
    raw = await _events(
        user_id,
        time_min=_local_midnight(now, tz, days=1),
        time_max=_local_midnight(now, tz, days=AHEAD_DAYS + 1),
    )
    lines = [line for item in raw if (line := event_line(item, tz)) is not None]
    return agenda_ahead_drafts(lines, now=now, tz=tz)[: MAX_PER_SOURCE[PersonalSource.AGENDA]]


__all__ = [
    "AHEAD_DAYS",
    "EventLine",
    "agenda_ahead_drafts",
    "agenda_done_drafts",
    "event_line",
    "read_agenda_ahead",
    "read_agenda_done",
]
