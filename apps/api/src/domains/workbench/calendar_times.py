"""Event times between a provider's fields and the calendar screen (ADR-369).

The screen speaks two shapes: an all-day event's DAYS (``YYYY-MM-DD``, the end
exclusive — the providers' own convention) and a timed event's INSTANTS (RFC
3339 in UTC). A provider answers ``{"date"}`` or ``{"dateTime", "timeZone"}``:
Google with an offset, Graph without one (its seven fractional digits read as
they are), in the zone it names. A time that cannot be read — a Windows zone name a
header forgot to turn into UTC included — reads as nothing, never as a guess.
What the page sends back is a WALL time plus a zone id, never an offset (spec
§14): the calendar clients take exactly that pair.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_WALL_TIME: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")


def window_bounds(first: date, last: date, zone: ZoneInfo) -> tuple[str, str]:
    """The instants the account's days ``first``..``last`` (included) cover."""
    start = datetime.combine(first, time.min, tzinfo=zone)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone)
    return _utc(start), _utc(end)


def provider_time(field: Mapping[str, Any]) -> tuple[bool, str] | None:
    """``(all_day, value)`` of a provider's start or end; None when unreadable."""
    day = field.get("date")
    if day:
        try:
            return True, date.fromisoformat(str(day)[:10]).isoformat()
        except ValueError:
            return None
    stamp = field.get("dateTime")
    if not stamp:
        return None
    try:
        instant = datetime.fromisoformat(str(stamp))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=ZoneInfo(str(field.get("timeZone") or "UTC")))
    except ValueError, ZoneInfoNotFoundError:
        return None
    return False, _utc(instant)


def wall_time(text: str) -> datetime:
    """A wall time as the page sends it: a day and a time, no zone, no offset.

    Raises:
        ValueError: Not a wall time (an offset, a day alone, anything else).
    """
    if not _WALL_TIME.match(text):
        raise ValueError("a wall time is YYYY-MM-DDTHH:MM, without an offset")
    return datetime.fromisoformat(text)


def ends_after(start: str, end: str, zone: ZoneInfo, *, all_day: bool) -> bool:
    """Whether ``end`` comes after ``start``: as days (end exclusive) or as instants.

    Raises:
        ValueError: A bound that is not a day (all-day) or a wall time.
    """
    if all_day:
        return date.fromisoformat(end) > date.fromisoformat(start)
    first = wall_time(start).replace(tzinfo=zone)
    last = wall_time(end).replace(tzinfo=zone)
    return last.astimezone(UTC) > first.astimezone(UTC)


def _utc(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
