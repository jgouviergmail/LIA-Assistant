"""What To Do keeps beyond a title, notes and a day (ADR-369, lot 9).

An importance, a reminder and a repetition are To Do's own: Google Tasks has no such field, so
its client refuses them rather than drop them in silence, and the page offers them only where
the descriptor says so. A repetition is one word on the screen, read from and written to
Graph's pattern; a pattern the word cannot say stays named ``custom`` and is left as it is. It
starts from a day, because each pattern but the daily one names the day it falls on.

To Do has no move: its `/move` answers 400, and a PATCH of `parentListId` answers 200 and moves
nothing (measured on 2026-11-05). A task is copied, then its original removed last, so a task
is never lost, and one that could not be removed is said to stand in both lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

#: The repetitions the screen can say, each with Graph's pattern type.
_REPEAT_TYPES: Final[dict[str, str]] = {
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "absoluteMonthly",
    "yearly": "absoluteYearly",
}
_REPEAT_WORDS: Final[dict[str, str]] = {value: key for key, value in _REPEAT_TYPES.items()}
#: A repetition Graph holds and the screen has no word for.
REPEAT_CUSTOM: Final = "custom"
#: Graph's days, in `date.weekday()` order.
_WEEKDAYS: Final = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_GRAPH_INSTANT: Final = "%Y-%m-%dT%H:%M:%S.0000000"


class TaskLeftBehindError(Exception):
    """The task reached its new list and its original could not be removed."""


@dataclass(frozen=True, slots=True)
class TaskDetails:
    """What a write changes beyond a title, notes and a day; what is left out is kept."""

    importance: str | None = None
    reminder: datetime | None = None
    clear_reminder: bool = False
    repeat: str | None = None
    #: The day a repetition starts on: it needs one.
    repeat_from: date | None = None
    clear_repeat: bool = False


def graph_recurrence(repeat: str, start: date) -> dict[str, Any]:
    """Graph's ``patternedRecurrence`` for a repetition starting on a day.

    Args:
        repeat: ``daily``, ``weekly``, ``monthly`` or ``yearly``.
        start: The day it starts on, in the account's calendar.

    Returns:
        The pattern and an open range.
    """
    pattern: dict[str, Any] = {"type": _REPEAT_TYPES[repeat], "interval": 1}
    if repeat == "weekly":
        pattern["daysOfWeek"] = [_WEEKDAYS[start.weekday()]]
    if repeat in {"monthly", "yearly"}:
        pattern["dayOfMonth"] = start.day
    if repeat == "yearly":
        pattern["month"] = start.month
    return {"pattern": pattern, "range": {"type": "noEnd", "startDate": start.isoformat()}}


def repeat_of(recurrence: dict[str, Any] | None) -> str | None:
    """The word for what Graph holds; ``custom`` for a pattern the screen cannot say."""
    if not recurrence:
        return None
    pattern = recurrence.get("pattern") or {}
    word = _REPEAT_WORDS.get(str(pattern.get("type")))
    plain = pattern.get("interval") == 1 and len(pattern.get("daysOfWeek") or ()) <= 1
    return word if word is not None and plain else REPEAT_CUSTOM


def details_body(details: TaskDetails | None) -> dict[str, Any]:
    """The fields of a To Do write; nothing for what the details leave out.

    Raises:
        ValueError: A repetition with no day to start from.
    """
    if details is None:
        return {}
    body: dict[str, Any] = {}
    if details.importance is not None:
        body["importance"] = details.importance
    if details.reminder is not None:
        instant = details.reminder.astimezone(UTC).strftime(_GRAPH_INSTANT)
        body["isReminderOn"] = True
        body["reminderDateTime"] = {"dateTime": instant, "timeZone": "UTC"}
    elif details.clear_reminder:
        # Measured: the flag alone answers 200 and leaves the reminder on.
        body["isReminderOn"] = False
        body["reminderDateTime"] = None
    if details.repeat is not None:
        if details.repeat_from is None:
            raise ValueError("a repetition starts on a day")
        body["recurrence"] = graph_recurrence(details.repeat, details.repeat_from)
    elif details.clear_repeat:
        body["recurrence"] = None
    return body


__all__ = [
    "REPEAT_CUSTOM",
    "TaskDetails",
    "TaskLeftBehindError",
    "details_body",
    "graph_recurrence",
    "repeat_of",
]
