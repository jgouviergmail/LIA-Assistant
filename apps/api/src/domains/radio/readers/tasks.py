"""The listener's tasks, for the journal's « done » and « ahead » parts (ADR-324 decision 41).

The tasks due soon come from the Today Briefing's cache (``personal.py``); what the
journal's noon and evening editions add is read here, live, from the listener's active
tasks provider (the briefing's own door and the owner's preferred list): the tasks
COMPLETED today — the provider's ``completed`` stamp read on the listener's clock, so
a task ticked at 23:30 yesterday is yesterday's — and the tasks DUE in the week ahead,
from tomorrow, under the day's own key (``task:<id>``) so one the day already tells is
never retold (``personal_facts``). Every provider is read in the Google Tasks shape its
client normalises to.

The client is open for the length of the read and closed before it returns (ADR-304).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any, Final
from uuid import UUID

from src.domains.briefing.constants import ERROR_CODE_CONNECTOR_OAUTH_EXPIRED
from src.domains.briefing.exceptions import ConnectorAccessError
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable, open_active_client
from src.domains.connectors.preferences.owner_defaults import TASK_LIST, resolve_owner_container_id
from src.domains.radio.facts import FactKind, Sensitivity, local_day_text
from src.domains.radio.personal import (
    MAX_PER_SOURCE,
    JournalPart,
    PersonalDraft,
    PersonalSource,
    digest,
)

#: How far the week ahead reaches, in local days from tomorrow.
AHEAD_DAYS: Final[int] = 7
#: How many tasks one window is read for (the bound is applied after the filter).
_SCAN_TASKS: Final[int] = 40
#: The provider's status of a task that was ticked.
_COMPLETED: Final[str] = "completed"


@dataclass(frozen=True, slots=True)
class TaskLine:
    """What the radio reads of one task.

    Attributes:
        id: The provider's id, if any.
        title: Its title.
        completed: Whether it was ticked.
        due: Its due day, if any.
        completed_at: When it was ticked (aware), when the provider says.
    """

    id: str | None
    title: str
    completed: bool
    due: date | None
    completed_at: datetime | None


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def task_line(raw: Mapping[str, Any]) -> TaskLine:
    """One provider task (Google Tasks shape) as the radio reads it."""
    due = _instant(raw.get("due"))
    task_id = raw.get("id")
    return TaskLine(
        id=str(task_id) if task_id else None,
        title=str(raw.get("title") or "").strip() or "Untitled",
        completed=raw.get("status") == _COMPLETED,
        due=due.date() if due is not None else None,
        completed_at=_instant(raw.get(_COMPLETED)),
    )


def _key(prefix: str, line: TaskLine) -> str:
    return f"{prefix}{line.id or digest(line.title)}"


def tasks_done_drafts(
    lines: Sequence[TaskLine], *, now: datetime, tz: tzinfo
) -> list[PersonalDraft]:
    """The tasks completed today, on the listener's clock.

    Args:
        lines: The tasks read, completed ones included.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        One draft per task ticked today, in the order given.
    """
    today = now.astimezone(tz).date()
    drafts: list[PersonalDraft] = []
    for line in lines:
        if not line.completed or line.completed_at is None:
            continue
        ticked = line.completed_at.astimezone(tz)
        if ticked.date() != today:
            continue
        drafts.append(
            PersonalDraft(
                FactKind.TASK,
                f'Task "{line.title}" completed today at {ticked:%H:%M}',
                _key("done:task:", line),
                Sensitivity.PERSONAL,
                JournalPart.DONE,
            )
        )
    return drafts


def tasks_ahead_drafts(
    lines: Sequence[TaskLine], *, now: datetime, tz: tzinfo
) -> list[PersonalDraft]:
    """The open tasks due in the week ahead, from tomorrow.

    Args:
        lines: The tasks read for the week.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        One draft per open task due between tomorrow and ``AHEAD_DAYS`` days on.
    """
    today = now.astimezone(tz).date()
    first, last = today + timedelta(days=1), today + timedelta(days=AHEAD_DAYS)
    drafts: list[PersonalDraft] = []
    for line in lines:
        if line.completed or line.due is None or not first <= line.due <= last:
            continue
        due_day = local_day_text(datetime.combine(line.due, time(), tzinfo=tz))
        drafts.append(
            PersonalDraft(
                FactKind.TASK,
                f'Task "{line.title}" is due on {due_day}',
                _key("task:", line),
                Sensitivity.PERSONAL,
                JournalPart.AHEAD,
            )
        )
    return drafts


async def _tasks(user_id: UUID, **listing: Any) -> list[dict[str, Any]]:
    """The listener's tasks from their preferred list, as the provider lists them.

    Raises:
        ConnectorAccessError: The tasks provider is connected but its credentials failed.
    """
    async with open_active_client("tasks", user_id, container=TASK_LIST) as opened:
        if opened is ClientUnavailable.NO_CREDENTIALS:
            raise ConnectorAccessError(
                "tasks", ERROR_CODE_CONNECTOR_OAUTH_EXPIRED, "credentials refused"
            )
        if not isinstance(opened, ActiveClient):
            return []  # no tasks provider connected: nothing to read
        task_list_id = await resolve_owner_container_id(
            client=opened.client,
            name=opened.preferred_name,
            owner_id=user_id,
            container=TASK_LIST,
        )
        result = await opened.client.list_tasks(
            task_list_id=task_list_id, max_results=_SCAN_TASKS, **listing
        )
    return [item for item in (result.get("items") or []) if isinstance(item, dict)]


async def read_tasks_done(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The tasks completed today, read from the listener's tasks provider.

    The provider is asked for the tasks completed since the listener's midnight (the
    bound of the scan); the listener's clock then decides which are today's.
    """
    since = datetime.combine(now.astimezone(tz).date(), time(), tzinfo=tz)
    raw = await _tasks(
        user_id, show_completed=True, show_hidden=True, completed_min=since.isoformat()
    )
    return tasks_done_drafts([task_line(item) for item in raw], now=now, tz=tz)[
        : MAX_PER_SOURCE[PersonalSource.TASKS]
    ]


async def read_tasks_ahead(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The open tasks due in the week ahead, read from the listener's tasks provider."""
    today = now.astimezone(tz).date()
    first = datetime.combine(today + timedelta(days=1), time(), tzinfo=tz)
    last = datetime.combine(today + timedelta(days=AHEAD_DAYS + 1), time(), tzinfo=tz)
    raw = await _tasks(
        user_id,
        show_completed=False,
        due_min=first.isoformat(),
        due_max=last.isoformat(),
    )
    return tasks_ahead_drafts([task_line(item) for item in raw], now=now, tz=tz)[
        : MAX_PER_SOURCE[PersonalSource.TASKS]
    ]


__all__ = [
    "AHEAD_DAYS",
    "TaskLine",
    "read_tasks_ahead",
    "read_tasks_done",
    "task_line",
    "tasks_ahead_drafts",
    "tasks_done_drafts",
]
