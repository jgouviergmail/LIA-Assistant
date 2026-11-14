"""An event's bounds, as the three calendars are written from (ADR-380).

The calendar clients used to take two strings, a zone that could be missing and
a flag saying how to read the strings. Each client then decided for itself what
a string without an offset meant, and one of them decided « UTC »: an event moved
to half past nine landed at half past ten (production, 2026-11-12).

They take one of three things now, and a string is none of them:

- :class:`TimedBounds` — from one wall time to another (``core/wall_time``);
- :class:`DayBounds` — an all-day event, its end EXCLUSIVE (``normalizers/all_day``);
- :class:`TimedSides` — a change to one side or both that keeps the event's shape.

Whoever still holds text — a validated request, a confirmed draft — turns it into
bounds HERE, once (:func:`bounds_of`, :func:`change_of`). A client only says the
bounds in its provider's words: it reads no text and stamps no zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from src.core.wall_time import WallTime
from src.domains.connectors.clients.normalizers.all_day import all_day_dates


@dataclass(frozen=True, slots=True)
class TimedBounds:
    """An event from one wall time to another.

    Attributes:
        start: When it starts.
        end: When it ends.
    """

    start: WallTime
    end: WallTime


@dataclass(frozen=True, slots=True)
class DayBounds:
    """An all-day event: days, not instants.

    Attributes:
        first: Its first day.
        after_last: The day AFTER its last one (exclusive, as the clients read it).
        zone: The zone whose midnights bound the days where a provider wants
            instants (Graph); a provider that keeps a day a day ignores it.
    """

    first: date
    after_last: date
    zone: ZoneInfo


@dataclass(frozen=True, slots=True)
class TimedSides:
    """A change that keeps the event's shape: a side given replaces, a side left out stays.

    Attributes:
        start: The new start, or None to leave it where it is.
        end: The new end, or None to leave it where it is.
    """

    start: WallTime | None = None
    end: WallTime | None = None


#: What a new event is given.
EventBounds = TimedBounds | DayBounds
#: What a change may say of an event's bounds.
BoundsChange = TimedBounds | DayBounds | TimedSides


def bounds_of(start: str, end: str, zone: ZoneInfo, *, all_day: bool) -> EventBounds:
    """The bounds two written values name.

    Args:
        start: A day (all-day) or a day and a time, with or without an offset.
        end: The same; for an all-day event, the day AFTER its last.
        zone: The zone of the person who wrote them.
        all_day: The values are days.

    Returns:
        The bounds.

    Raises:
        ValueError: A value that cannot be read, a day given for a time, or an
            all-day event that does not end after it starts.
    """
    if all_day:
        first, after_last = all_day_dates(start, end)
        return DayBounds(first, after_last, zone)
    return TimedBounds(WallTime.read(start, zone), WallTime.read(end, zone))


def change_of(
    start: str | None, end: str | None, zone: ZoneInfo, *, all_day: bool | None
) -> BoundsChange | None:
    """What a change says of an event's bounds, from the values it was written with.

    Args:
        start: The new start, or None.
        end: The new end, or None.
        zone: The zone of the person who wrote them.
        all_day: True or False names the event's shape, and both bounds come
            with it; None keeps the shape it has.

    Returns:
        The change, or None when it says nothing of the bounds.

    Raises:
        ValueError: A shape named with one bound only, or a value that cannot be read.
    """
    if all_day is not None:
        if start is None or end is None:
            raise ValueError("Turning an event all-day or timed needs its new start and end.")
        return bounds_of(start, end, zone, all_day=all_day)
    if start is None and end is None:
        return None
    return TimedSides(
        start=None if start is None else WallTime.read(start, zone),
        end=None if end is None else WallTime.read(end, zone),
    )


def series_bounds(first_day: date, bounds: EventBounds) -> EventBounds:
    """The bounds a whole series takes from an occurrence's: the same ones, from its first day.

    Both bounds move by the same number of DAYS, on the wall: the series shows the
    times its occurrence was given. No instant is read — an occurrence across a
    night the clocks change lasts an hour more or less than the series it belongs to.

    Args:
        first_day: The day the series starts.
        bounds: The bounds the occurrence was given.

    Returns:
        The series' own: the same times of day, as many days apart, from its first day.
    """
    if isinstance(bounds, DayBounds):
        return DayBounds(first_day, first_day + (bounds.after_last - bounds.first), bounds.zone)
    moved = first_day - bounds.start.local.date()
    return TimedBounds(
        WallTime(bounds.start.local + moved, bounds.start.zone),
        WallTime(bounds.end.local + moved, bounds.end.zone),
    )


__all__ = [
    "BoundsChange",
    "DayBounds",
    "EventBounds",
    "TimedBounds",
    "TimedSides",
    "bounds_of",
    "change_of",
    "series_bounds",
]
