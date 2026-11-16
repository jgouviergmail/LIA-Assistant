"""Availability pre-fetch for agentic calls (spec D-5).

Builds a compact free/busy summary from every calendar the user owns on their
active calendar connector (``calendar_lists``), projecting
events to busy time ranges ONLY — never titles, attendees, or locations. This is
minimization *by capability*, not by prompt: the projection reads solely the
``start``/``end`` of each event, and asks the provider for those fields alone where
it projects (Graph and CalDAV answer whole events, of which nothing else is read).
The summary is injected as the ``{{availability_summary}}`` dynamic variable so the
agent can answer availability questions on the call without ever seeing what the
user is actually doing.

Since lot B (2026-08) the Google client exposes ``query_freebusy``: when the
resolved client offers it, busy ranges come from the freeBusy endpoint (even
less data than the projection). Other providers keep the start/end projection of
every event of the window.

The pre-fetch is best-effort: any resolution/HTTP failure (or no calendar
connector) yields the localized "unavailable" line and NEVER raises — a missing
calendar must not block placing the call.

The structural phrases (header / all-free / unavailable) live in
``core.i18n_telephony`` (all 6 languages).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import structlog

from src.core.constants import CALENDARS_READ_MAX
from src.core.i18n import resolve_language
from src.core.i18n_telephony import get_availability_phrases
from src.core.time_utils import format_datetime_for_display
from src.domains.connectors.clients.calendar_lists import (
    calendars_to_read,
    read_owned_events,
    unread_in_freebusy,
)
from src.domains.connectors.clients.event_order import soonest_first

if TYPE_CHECKING:
    from src.domains.connectors.calendar_access import CalendarAccess

logger = structlog.get_logger(__name__)

# Hard safety cap on the events pulled for the projection (NOT a business knob):
# the pre-fetch window itself is bounded upstream by telephony_prefetch_window_days.
_MAX_EVENTS = 100


def _busy_line(event: dict[str, Any], user_timezone: str, user_language: str) -> str | None:
    """Project one calendar event to a localized busy range, or ``None``.

    Reads ONLY ``start``/``end`` (Google-shaped: ``dateTime`` for timed events,
    ``date`` for all-day). Titles, attendees and locations are never touched.
    All-day blocks (``date`` only) render as a date without a spurious time.
    """
    start = event.get("start") or {}
    end = event.get("end") or {}
    start_raw = start.get("dateTime") or start.get("date")
    if not start_raw:
        return None
    end_raw = end.get("dateTime") or end.get("date") or ""

    start_fmt = format_datetime_for_display(
        start_raw, user_timezone, user_language, include_time="T" in start_raw
    )
    if not end_raw:
        return f"- {start_fmt}"
    end_fmt = format_datetime_for_display(
        end_raw, user_timezone, user_language, include_time="T" in end_raw
    )
    return f"- {start_fmt} → {end_fmt}"


def summarize_busy_periods(
    events: list[dict[str, Any]], user_timezone: str, user_language: str
) -> str:
    """Project a list of calendar events to a compact free/busy summary.

    This is the leak-critical core: it emits busy time ranges only, never any
    event detail. Pure and side-effect-free so the minimization guarantee is
    unit-testable in isolation.

    Args:
        events: Raw calendar events (Google-shaped ``start``/``end`` dicts).
        user_timezone: IANA timezone the ranges are rendered in.
        user_language: Language for the structural phrases and date formatting.

    Returns:
        A localized summary: a header plus one ``- start → end`` line per busy
        block, or the "all free" line when there are no busy blocks.
    """
    phrases = get_availability_phrases(user_language)
    # One line per busy range: two calendars holding one meeting say it once.
    lines = list(
        dict.fromkeys(
            line
            for event in events
            if (line := _busy_line(event, user_timezone, user_language)) is not None
        )
    )
    if not lines:
        return phrases["all_free"]
    return phrases["header"] + "\n" + "\n".join(lines)


async def _busy_events(
    access: CalendarAccess, window_start: datetime, window_end: datetime
) -> tuple[list[dict[str, Any]], bool]:
    """The busy blocks of every calendar the account owns, soonest first, and whether whole.

    The configured default says where an event is created, never where a
    meeting is (``calendar_lists``, owner rule 2026-11-15): an invitation in the
    main calendar makes the person busy too. A busy list read in part would tell
    the voice a booked hour is free: the caller says « unavailable » instead
    (ADR-185 amendment 2026-11-15).
    """
    client = access.client
    time_min, time_max = window_start.isoformat(), window_end.isoformat()
    if hasattr(client, "query_freebusy"):
        # Lot B (2026-08): the freeBusy endpoint returns busy ranges only —
        # even less data than the start/end projection, so it wins when
        # the provider offers it. Projected to the Google event shape so
        # summarize_busy_periods stays the single rendering path.
        calendars = await calendars_to_read(client, access.calendar_id, bound=CALENDARS_READ_MAX)
        freebusy = await client.query_freebusy(
            time_min=time_min, time_max=time_max, calendar_ids=calendars.ids
        )
        blocks = [
            {"start": {"dateTime": block.get("start")}, "end": {"dateTime": block.get("end")}}
            for calendar in (freebusy.get("calendars") or {}).values()
            for block in calendar.get("busy", [])
        ]
        whole = not (calendars.cut or unread_in_freebusy(freebusy, calendars.ids))
        return soonest_first(blocks), whole
    # Every event of the window, pages drained: the agents' one-request listing
    # stopped at its ceiling and left the rest of the window « free ».
    owned = await read_owned_events(
        client,
        access.calendar_id,
        [(time_min, time_max)],
        bound=_MAX_EVENTS,
        # Minimization by capability: never ask for titles, attendees, locations.
        fields=["start", "end"],
    )
    return soonest_first(owned.events), not owned.cut


@dataclass(frozen=True)
class AvailabilityRead:
    """What the free/busy pre-fetch produced, and whether a calendar was opened.

    The consultation register needs the second half (ADR-263): a read that
    happened is recorded, a read that failed is recorded as ``failed``, and
    « no calendar connected » opened nothing and records nothing.

    Attributes:
        summary: The localized free/busy text handed to the voice agent.
        opened: True when a calendar was actually queried.
        failed: True when the query was attempted and could not be read.
    """

    summary: str
    opened: bool
    failed: bool


async def build_availability(
    user_id: UUID,
    window_start: datetime,
    window_end: datetime,
    user_timezone: str,
    user_language: str | None = None,
) -> AvailabilityRead:
    """Build the free/busy summary injected as the ``{{availability_summary}}`` var.

    Resolves the user's active calendar connector, reads the busy ranges over
    ``[window_start, window_end]`` (freeBusy where the provider has it, every
    event of the window otherwise), and projects them to a compact busy summary.
    Best-effort: returns the localized "unavailable" line on any failure, and on
    a window read in part, and never raises.

    Args:
        user_id: Owner of the calendar.
        window_start: Inclusive lower bound of the pre-fetch window (UTC-aware).
        window_end: Exclusive upper bound of the pre-fetch window (UTC-aware).
        user_timezone: IANA timezone the busy ranges are rendered in.
        user_language: Language for phrases + date formatting (app code, e.g.
            ``"fr"``, ``"zh-CN"``).

    Returns:
        The localized summary, plus whether a calendar was opened and whether
        the read failed.
    """
    user_language = resolve_language(user_language)
    phrases = get_availability_phrases(user_language)
    not_opened = AvailabilityRead(summary=phrases["unavailable"], opened=False, failed=False)
    try:
        from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar

        # The shared door (ADR-304): no session held while the calendar
        # answers, the client closed on every path — it never was here.
        async with open_active_calendar(user_id) as access:
            if not isinstance(access, CalendarAccess):
                return not_opened
            events, whole = await _busy_events(access, window_start, window_end)
    except (TimeoutError, httpx.HTTPError, ValueError, KeyError, AttributeError) as exc:
        logger.warning(
            "telephony_availability_prefetch_failed", user_id=str(user_id), error=str(exc)
        )
        return AvailabilityRead(summary=phrases["unavailable"], opened=True, failed=True)
    if not whole:
        # Said, never guessed: a cut busy list is no free/busy answer.
        logger.warning("telephony_availability_window_cut", user_id=str(user_id))
        return AvailabilityRead(summary=phrases["unavailable"], opened=True, failed=True)

    return AvailabilityRead(
        summary=summarize_busy_periods(events, user_timezone, user_language),
        opened=True,
        failed=False,
    )
