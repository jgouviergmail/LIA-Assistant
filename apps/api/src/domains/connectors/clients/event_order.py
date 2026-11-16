"""When a normalised event starts, and the order a window is answered in (ADR-185 amendment).

Every calendar client answers in the Google event shape (``start.dateTime`` or
``start.date``), but not every provider ORDERS what it answers: Graph's
``calendarView`` promises no order and CalDAV answers in the server's. A reader
keeping « the soonest N » of a window must therefore sort what it read before
cutting, or it keeps an arbitrary N. One key for every client that sorts.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _zone_of(edge: dict[str, Any]) -> ZoneInfo | None:
    """The IANA zone an edge names beside a wall time, None when it names none or another kind."""
    name = str(edge.get("timeZone") or "").strip()
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        return None


def start_instant(event: dict[str, Any]) -> datetime:
    """When a normalised event starts, as an instant (offsets compared, not spelled).

    A wall time without an offset is read in the zone the edge names (Graph says
    ``timeZone`` beside a bare ``dateTime``), UTC when it names none it can; an
    all-day event starts at its day's midnight UTC; an unreadable start sorts last.

    Args:
        event: A normalised event.

    Returns:
        The instant it starts.
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
    if moment.tzinfo is not None:
        return moment
    zone = _zone_of(start) if "T" in value else None
    return moment.replace(tzinfo=zone or UTC)


def soonest_first(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The events in start order, the soonest first (a stable sort: ties keep their order).

    Args:
        events: Normalised events, in whatever order the provider answered.

    Returns:
        A new list, sorted by :func:`start_instant`.
    """
    return sorted(events, key=start_instant)
