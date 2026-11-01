"""How the calendar tools turn what the model gave into an event's bounds (ADR-369).

Beside the calendar manifests, not among the tools: the manifest reads its wording
here, and importing the tools package from a manifest would load every tool.

Timed bounds are LOCAL times the tool re-localises to the person's zone (a model
sends a wrong offset as often as a right one). All-day bounds are DAYS: the model
names the first and the LAST day (inclusive, as a person says them), and the
clients take the first day and the EXCLUSIVE end they read back
(``connectors/clients/normalizers/all_day``) — converted here, once.

An UPDATE speaks the same days: an all-day event the model moves without
restating ``all_day`` stays all-day, so the event is read before its bounds — a
last day taken for the client's exclusive end loses a day without a word.

The parameter's wording is ONE constant read by the planner's manifest and the
tool's own schema: the ReAct loop binds the schema and never sees the manifest
(ADR-310), so a rule only one of them stated would be hidden from the other. A
value it cannot read is refused (``core/date_contract``), never guessed.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from datetime import date
from typing import Any, Final

from src.core.date_contract import InvertedPeriodError, UnreadableDateError
from src.core.time_utils import normalize_user_datetime
from src.domains.connectors.clients.normalizers.all_day import (
    calendar_date,
    exclusive_end,
    inclusive_last_day,
    is_all_day,
)

#: What ``all_day`` means, for the manifest and the tool schema alike.
ALL_DAY_DESCRIPTION: Final = (
    "True for an all-day event: start_datetime is its FIRST day and end_datetime its LAST "
    "day, as dates (YYYY-MM-DD, the same day for a one-day event). False or omitted: "
    "timed bounds."
)
#: What ``all_day`` means on an update, where omitting it keeps the event's shape.
ALL_DAY_UPDATE_DESCRIPTION: Final = (
    "True turns the event all-day, false turns it timed (give both new times); omit it to "
    "keep its shape. An all-day event's days are given as on creation: start_datetime its "
    "FIRST day, end_datetime its LAST day (YYYY-MM-DD); a day not given stays the event's."
)


def all_day_bounds(first_day: str, last_day: str | None) -> tuple[str, str]:
    """The client's all-day bounds for the days the model named.

    Args:
        first_day: The event's first day (a date, or a datetime whose date counts).
        last_day: Its last day, INCLUSIVE; None for a one-day event.

    Returns:
        ``(first_day, exclusive_end)`` as ISO dates.

    Raises:
        UnreadableDateError: A day the model gave cannot be read.
        InvertedPeriodError: The last day is before the first.
    """
    first = _day(first_day)
    last = _day(last_day) if last_day else first
    if last < first:
        raise InvertedPeriodError(
            "an all-day event's last day (end_datetime) is before its first day (start_datetime)"
        )
    return first.isoformat(), exclusive_end(last).isoformat()


def updated_bounds(
    start: str | None,
    end: str | None,
    timezone: str,
    all_day: bool | None,
    current: Mapping[str, Any],
) -> tuple[str | None, str | None, bool | None]:
    """An update's bounds and shape, as the client takes them.

    The event's shape decides how the model's days are read: an all-day event
    updated without ``all_day`` stays all-day and its days are converted like a
    new event's, a day not given being the event's own. A timed event keeps its
    shape and re-localises the times it is given.

    Args:
        start: The new start the model gave, or None.
        end: The new end — for an all-day event, its LAST day — or None.
        timezone: The person's IANA timezone, for times.
        all_day: True/False switches the shape; None keeps it.
        current: The event as the client read it.

    Returns:
        ``(start, end, all_day)``: dates with the exclusive end for an all-day
        event (``all_day`` then True), times otherwise (None for one not given).

    Raises:
        UnreadableDateError: A day the model gave cannot be read.
        InvertedPeriodError: The resulting last day is before the first.
        ValueError: A switch to timed without both times.
    """
    if all_day is None and not is_all_day(current):
        return (_localized_or_none(start, timezone), _localized_or_none(end, timezone), None)
    if all_day is False:
        if not (start and end):
            raise ValueError(
                "all_day=false needs both start_datetime and end_datetime: the event's new times"
            )
        return localized(start, timezone), localized(end, timezone), False
    own_first, own_last = _own_days(current)
    first = start or own_first
    if not first:
        raise ValueError("all_day=true needs start_datetime: the event's first day (YYYY-MM-DD)")
    return (*all_day_bounds(first, end or own_last), True)


def localized(value: str, timezone: str) -> str:
    """A local time re-localised to the person's zone (a wrong model offset stripped)."""
    return normalize_user_datetime(value, timezone) or value


def timed_bounds(start: str, end: str, timezone: str) -> tuple[str, str]:
    """Timed bounds, each re-localised to the person's zone."""
    return localized(start, timezone), localized(end, timezone)


def _localized_or_none(value: str | None, timezone: str) -> str | None:
    return localized(value, timezone) if value else None


def _day(value: str) -> date:
    """The day a value the model gave names, or the refusal that names it."""
    try:
        return calendar_date(value)
    except ValueError as error:
        raise UnreadableDateError(str(value).strip()) from error


def _own_days(event: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """An all-day event's first and LAST day as read; Nones for any other shape.

    An end read as absent is one day: CalDAV's ``DTSTART;VALUE=DATE`` alone lasts
    one day (RFC 5545), and its normaliser reads it as ``end: {}``. Nor is a
    provider's value ever blamed on the model as an unreadable day of its own.
    """
    if not is_all_day(event):
        return None, None
    first = event["start"]["date"]
    last = None
    with suppress(ValueError, TypeError, KeyError):
        last = inclusive_last_day(calendar_date(event["end"]["date"])).isoformat()
    return first, last


__all__ = [
    "ALL_DAY_DESCRIPTION",
    "ALL_DAY_UPDATE_DESCRIPTION",
    "all_day_bounds",
    "localized",
    "timed_bounds",
    "updated_bounds",
]
