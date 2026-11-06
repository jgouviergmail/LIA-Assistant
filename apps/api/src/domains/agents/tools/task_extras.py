"""What the assistant may ask of To Do beyond a title, notes and a day (ADR-369, lot 9, D2).

Out of ``tasks_tools.py``, frozen at its audited size. Steps, an importance, a reminder and a
repetition are To Do's own: on Google the tool refuses them by name, so the model tells the
person rather than promise what the client would refuse after the confirmation. A repetition
starts on a due day (``task_details``). What is accepted rides the draft, shows on the card and
is carried at execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Final

from src.domains.agents.tasks.extras import TaskExtras, read_extras
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.mailbox_draft_base import refusal
from src.domains.connectors.clients.task_details import TaskDetails
from src.domains.connectors.models import ConnectorType

IMPORTANCES: Final = ("low", "normal", "high")
REPEATS: Final = ("daily", "weekly", "monthly", "yearly")


def extras_refusal(client: Any, extras: TaskExtras, *, has_due: bool) -> dict[str, Any] | None:
    """Why a call cannot be taken as it stands; None when it can.

    Args:
        client: The active tasks client.
        extras: What the call asks.
        has_due: The task has, or will have, a due day.

    Returns:
        The refusal to hand back to the model.
    """
    if not extras.asked:
        return None
    if client.connector_type != ConnectorType.MICROSOFT_TASKS:
        return refusal(
            ToolErrorCode.INVALID_INPUT,
            "Google Tasks keeps no steps, importance, reminder or repetition: tell the person.",
        )
    if extras.importance and extras.importance not in IMPORTANCES:
        return refusal(ToolErrorCode.INVALID_INPUT, f"importance is one of {IMPORTANCES}.")
    if extras.repeat and extras.repeat not in REPEATS:
        return refusal(ToolErrorCode.INVALID_INPUT, f"repeat is one of {REPEATS}.")
    if extras.repeat and not has_due:
        return refusal(ToolErrorCode.INVALID_INPUT, "repeat starts on a due date: give one.")
    return None


def _instant(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None


def _day(raw: str | None) -> date | None:
    return date.fromisoformat(raw[:10]) if raw else None


def details_of(content: Mapping[str, Any]) -> TaskDetails | None:
    """The client's details a confirmed draft carries; None when it carries none."""
    extras = read_extras(content)
    if not (
        extras.importance
        or extras.reminder
        or extras.repeat
        or extras.clear_reminder
        or extras.clear_repeat
    ):
        return None
    return TaskDetails(
        importance=extras.importance,
        reminder=_instant(extras.reminder),
        clear_reminder=extras.clear_reminder,
        repeat=extras.repeat,
        repeat_from=_day(content.get("due")) if extras.repeat else None,
        clear_repeat=extras.clear_repeat,
    )


__all__ = [
    "IMPORTANCES",
    "REPEATS",
    "TaskExtras",
    "details_of",
    "extras_refusal",
    "read_extras",
]
