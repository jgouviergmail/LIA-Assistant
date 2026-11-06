"""A repeating event, in each calendar's words (ADR-369, lot 10).

One spec, the one every recurrence of LIA is (``core/recurrence``). Google and iCloud take an RRULE;
Graph takes a ``patternedRecurrence``. A shape Graph cannot hold is refused by name, never held
differently: « the last day of the month » as a 31st would skip every short month, and the person
would find out by missing it. An end date is the LAST local day, included: an all-day series says
it as a day, and a timed one as the last second of that day in UTC, which is what RFC 5545 asks of
an event with a zone.

A series starts on the event's own day: a rule that day does not belong to is refused before
anything is sent, because each provider would answer it differently (Google keeps the day as an
extra occurrence, Graph refuses). What the rule says of a time of day is not read: an event has
its own. Changing a whole series keeps its first day and takes the new time of day and the new
length: an occurrence's date is no date for the series.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from typing import Any, Final
from zoneinfo import ZoneInfo

from src.core.constants import WORKBENCH_EVENT_SERIES_MAX_COUNT
from src.core.recurrence import (
    DailyTimes,
    RecurrenceLimits,
    RecurrenceSpec,
    TimeOfDay,
    series,
)

#: RRULE's words for the days, by ISO weekday.
_RRULE_DAYS: Final = {1: "MO", 2: "TU", 3: "WE", 4: "TH", 5: "FR", 6: "SA", 7: "SU"}
#: Graph's words for them.
_GRAPH_DAYS: Final = {
    1: "monday",
    2: "tuesday",
    3: "wednesday",
    4: "thursday",
    5: "friday",
    6: "saturday",
    7: "sunday",
}
_GRAPH_INDEX: Final = {1: "first", 2: "second", 3: "third", 4: "fourth", -1: "last"}
_LAST_SECOND: Final = time(23, 59, 59)


#: What an event's rule may ask: its time is the event's, its length is bounded.
_LIMITS: Final = RecurrenceLimits(
    max_times_per_day=1,
    min_step_minutes=1,
    max_series_count=WORKBENCH_EVENT_SERIES_MAX_COUNT,
)
_NOON: Final = DailyTimes(mode="at", at=[TimeOfDay(hour=12, minute=0)])


class RecurrenceNotHeldError(ValueError):
    """A shape this calendar cannot hold: refused, never held differently."""


class EventStartOutsideSeriesError(ValueError):
    """A series starting on a day its own rule does not serve."""


def anchored_spec(spec: RecurrenceSpec, start_day: date, zone: str) -> RecurrenceSpec:
    """A rule as an event's own: from its first day, that day being one the rule serves.

    Args:
        spec: The rule as it was given.
        start_day: The event's first day.
        zone: The zone it is read in.

    Returns:
        The rule, anchored.

    Raises:
        RecurrenceError: A rule past the event's bound, or one that is no series.
        EventStartOutsideSeriesError: A first day the rule does not serve.
    """
    if spec.freq == "once":
        raise RecurrenceNotHeldError("a single occurrence is no series")
    anchored = spec.model_copy(update={"anchor_date": start_day, "times": _NOON})
    anchored.validate_against(_LIMITS)
    tz = ZoneInfo(zone)
    first = next(series(anchored, tz), None)
    if first is None or first.astimezone(tz).date() != start_day:
        raise EventStartOutsideSeriesError("the first day is not one the rule serves")
    return anchored


def is_series(event: Mapping[str, Any]) -> bool:
    """Whether an event belongs to a series, on any of the three calendars.

    Graph's master carries its pattern apart (``recurrence_pattern``), its ``recurrence`` empty.
    """
    return bool(
        event.get("recurringEventId") or event.get("recurrence") or event.get("recurrence_pattern")
    )


def first_day_of(master: Mapping[str, Any], zone: str) -> date | None:
    """The day a series starts, on the clock of the person who asks; None when unreadable."""
    start = master.get("start") or {}
    if start.get("date"):
        return date.fromisoformat(str(start["date"])[:10])
    stamp = start.get("dateTime")
    if not stamp:
        return None
    instant = datetime.fromisoformat(str(stamp))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=ZoneInfo(str(start.get("timeZone") or "UTC")))
    return instant.astimezone(ZoneInfo(zone)).date()


def series_bounds(first_day: date, start: str, end: str, *, all_day: bool) -> tuple[str, str]:
    """The bounds a whole series takes from an occurrence's: its first day, their time and length.

    Args:
        first_day: The day the series starts.
        start: The new start, a wall time or a day.
        end: The new end.
        all_day: The bounds are days, the end exclusive.

    Returns:
        The bounds as the calendar clients take them.
    """
    if all_day:
        span = date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])
        return first_day.isoformat(), (first_day + span).isoformat()
    wall_start, wall_end = datetime.fromisoformat(start), datetime.fromisoformat(end)
    moved = datetime.combine(first_day, wall_start.time())
    return (
        moved.isoformat(timespec="seconds"),
        (moved + (wall_end - wall_start)).isoformat(timespec="seconds"),
    )


def rrule_of(spec: RecurrenceSpec, *, zone: str, all_day: bool) -> str:
    """A recurrence as an RRULE line.

    Args:
        spec: The recurrence.
        zone: The event's IANA zone, which an end date is read in.
        all_day: The event is all-day: its end is a day, not an instant.

    Returns:
        The line, ``RRULE:`` included.

    Raises:
        RecurrenceNotHeldError: A series of one is no series.
    """
    if spec.freq == "once":
        raise RecurrenceNotHeldError("a single occurrence is no series")
    parts = [f"FREQ={spec.freq.upper()}"]
    if spec.interval > 1:
        parts.append(f"INTERVAL={spec.interval}")
    if spec.freq == "weekly":
        parts.append("BYDAY=" + ",".join(_RRULE_DAYS[day] for day in spec.byweekday))
    if spec.nth_weekday is not None:
        nth, weekday = spec.nth_weekday
        parts.append(f"BYDAY={nth}{_RRULE_DAYS[weekday]}")
    if spec.bymonth:
        parts.append("BYMONTH=" + ",".join(str(month) for month in spec.bymonth))
    if spec.bymonthday:
        parts.append("BYMONTHDAY=" + ",".join(str(day) for day in spec.bymonthday))
    if spec.end.kind == "after_count":
        parts.append(f"COUNT={spec.end.after_count}")
    if spec.end.on_date is not None:
        parts.append(f"UNTIL={_until(spec.end.on_date, zone, all_day=all_day)}")
    return "RRULE:" + ";".join(parts)


def _until(last_day: date, zone: str, *, all_day: bool) -> str:
    if all_day:
        return last_day.strftime("%Y%m%d")
    local = datetime.combine(last_day, _LAST_SECOND, tzinfo=ZoneInfo(zone))
    return local.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def graph_recurrence(spec: RecurrenceSpec, *, zone: str) -> dict[str, Any]:
    """A recurrence as Graph's ``patternedRecurrence``.

    Args:
        spec: The recurrence.
        zone: The event's IANA zone.

    Returns:
        The pattern and the range.

    Raises:
        RecurrenceNotHeldError: A shape Graph cannot hold.
    """
    return {"pattern": _pattern(spec), "range": _range(spec, zone)}


def _pattern(spec: RecurrenceSpec) -> dict[str, Any]:
    interval = {"interval": spec.interval}
    if spec.freq == "daily":
        return {"type": "daily", **interval}
    if spec.freq == "weekly":
        days = [_GRAPH_DAYS[day] for day in spec.byweekday]
        return {"type": "weekly", **interval, "daysOfWeek": days, "firstDayOfWeek": "monday"}
    if spec.freq == "monthly":
        return _monthly(spec) | interval
    if spec.freq == "yearly":
        return {
            "type": "absoluteYearly",
            **interval,
            "month": _only(spec.bymonth),
            "dayOfMonth": _a_day_of_the_month(spec),
        }
    raise RecurrenceNotHeldError("a single occurrence is no series")


def _monthly(spec: RecurrenceSpec) -> dict[str, Any]:
    if spec.nth_weekday is None:
        return {"type": "absoluteMonthly", "dayOfMonth": _a_day_of_the_month(spec)}
    nth, weekday = spec.nth_weekday
    if nth not in _GRAPH_INDEX:
        raise RecurrenceNotHeldError("Graph has no fifth weekday of a month")
    return {
        "type": "relativeMonthly",
        "daysOfWeek": [_GRAPH_DAYS[weekday]],
        "index": _GRAPH_INDEX[nth],
    }


def _a_day_of_the_month(spec: RecurrenceSpec) -> int:
    day = _only(spec.bymonthday)
    if day < 1:
        raise RecurrenceNotHeldError("Graph has no last day of a month")
    return day


def _only(values: tuple[int, ...]) -> int:
    if len(values) != 1:
        raise RecurrenceNotHeldError("Graph holds one day, and one month, of a series")
    return values[0]


def _range(spec: RecurrenceSpec, zone: str) -> dict[str, Any]:
    start = {"startDate": spec.anchor_date.isoformat(), "recurrenceTimeZone": zone}
    if spec.end.kind == "after_count":
        return {"type": "numbered", "numberOfOccurrences": spec.end.after_count, **start}
    if spec.end.on_date is not None:
        return {"type": "endDate", "endDate": spec.end.on_date.isoformat(), **start}
    return {"type": "noEnd", **start}


__all__ = [
    "EventStartOutsideSeriesError",
    "RecurrenceNotHeldError",
    "anchored_spec",
    "first_day_of",
    "graph_recurrence",
    "is_series",
    "rrule_of",
    "series_bounds",
]
