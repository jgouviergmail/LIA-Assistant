"""A task's due DAY, whatever its provider kept: the one door (2026-11-07).

Google Tasks keeps a date: the time part of its RFC 3339 ``due`` is the provider's noise
(``2026-11-03T00:00:00.000Z`` is the 3rd in every zone; converting it to a zone west of
Greenwich would show the 2nd). Microsoft To Do keeps the instant of midnight in the zone it is
GIVEN and answers it in UTC — measured on Graph: given UTC, it keeps the UTC date, which made a day
written as its UTC instant the day before east of Greenwich. So a day is written to To Do as its
midnight in the account's zone, named (``todo_due``), and a To Do due is read as its instant in that
zone (``due_day``). Every reader of a task's day goes through here: the Tools, the home's card, the
heartbeat, the radio, the assistant.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, tzinfo
from typing import Any, Final
from zoneinfo import ZoneInfo

#: The marker the To Do normalizer stamps on a task (Google's tasks carry none).
_TODO_MARKER: Final = "microsoft"


def todo_due(day: date, zone: ZoneInfo) -> tuple[str, str]:
    """What To Do is given for a day: its midnight on the account's wall, and that zone's name.

    Args:
        day: The day the task is due.
        zone: The account's zone.

    Returns:
        Graph's ``dateTime`` (no offset) and ``timeZone``.
    """
    return f"{day.isoformat()}T00:00:00", zone.key


def due_day(raw: str | None, *, todo: bool, zone: tzinfo) -> date | None:
    """The day a provider's ``due`` names, or None without a readable one.

    Args:
        raw: The ``due`` a client answered (RFC 3339, or a bare date).
        todo: It is To Do's (an instant), else Google's (a date).
        zone: The account's zone, which a To Do instant is read in.

    Returns:
        The day, or None.
    """
    if not raw:
        return None
    try:
        if not todo:
            return date.fromisoformat(raw[:10])
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(zone).date()


def task_due_day(task: Mapping[str, Any], zone: tzinfo) -> date | None:
    """The day a normalized task is due, its provider told by its normalizer's marker.

    Args:
        task: A task as the tasks clients answer it (Google Tasks' shape).
        zone: The account's zone.

    Returns:
        The day, or None without a readable one.
    """
    raw = task.get("due")
    return due_day(
        raw if isinstance(raw, str) else None,
        todo=task.get("_provider") == _TODO_MARKER,
        zone=zone,
    )


__all__ = ["due_day", "task_due_day", "todo_due"]
