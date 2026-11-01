"""An all-day event's dates, one convention for the three calendar providers (ADR-369, D2).

The clients READ an all-day event the Google way — ``start.date`` and an
EXCLUSIVE ``end.date`` (a one-day event on the 3rd ends on the 4th) — whatever
the provider (Google natively, Graph's midnight bounds, CalDAV's ``DTEND;VALUE=DATE``).
They WRITE it the same way, so an event read and written back keeps its days.

A person, and a model, think in INCLUSIVE days (« from the 3rd to the 5th »):
the conversion lives here, once, for the assistant's tools and the « Tools »
editor alike — never re-derived at a call site.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

_ONE_DAY = timedelta(days=1)


def calendar_date(value: str) -> date:
    """The calendar day an ISO date — or the date part of an ISO datetime — names.

    Raises:
        ValueError: ``value`` names no calendar day.
    """
    return date.fromisoformat(str(value).strip()[:10])


def all_day_dates(start: str | None, end: str | None) -> tuple[date, date]:
    """The first day and the EXCLUSIVE end of an all-day event, checked.

    Args:
        start: Its first day (``YYYY-MM-DD``).
        end: The day after its last day (``YYYY-MM-DD``, exclusive).

    Returns:
        ``(first_day, day_after_last)``.

    Raises:
        ValueError: A date is missing or unreadable, or the end is not after the start.
    """
    if not start or not end:
        raise ValueError("An all-day event needs its first day and the day after its last.")
    first, after_last = calendar_date(start), calendar_date(end)
    if after_last <= first:
        raise ValueError("An all-day event ends after the day it starts (end is exclusive).")
    return first, after_last


def exclusive_end(last_day: date) -> date:
    """The exclusive end of an all-day event whose last day is ``last_day``."""
    return last_day + _ONE_DAY


def inclusive_last_day(exclusive: date) -> date:
    """The last day of an all-day event whose exclusive end is ``exclusive``."""
    return exclusive - _ONE_DAY


def is_all_day(event: Mapping[str, Any]) -> bool:
    """Whether a normalised event is all-day (``start.date`` without ``start.dateTime``)."""
    start = event.get("start") or {}
    return isinstance(start, Mapping) and bool(start.get("date")) and not start.get("dateTime")


__all__ = [
    "all_day_dates",
    "calendar_date",
    "exclusive_end",
    "inclusive_last_day",
    "is_all_day",
]
