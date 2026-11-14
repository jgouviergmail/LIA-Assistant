"""The listener's tasks, for the journal's « done » and « ahead » parts (ADR-324 decision 41).

The tasks due soon come from the Today Briefing's cache (``personal.py``); what the
journal's noon and evening editions add is read here, live, from the listener's active
tasks provider (the briefing's own door), in EVERY list of the account (owner rule,
2026-11-10: the list the connector's settings name as the default is where a new task
goes, and nothing else): the tasks
COMPLETED today — the provider's ``completed`` stamp read on the listener's clock, so
a task ticked at 23:30 yesterday is yesterday's — and the tasks DUE in the week ahead,
from tomorrow, under the day's own key (``task:<id>``) so one the day already tells is
never retold (``personal_facts``). Every provider is read in the Google Tasks shape its
client normalises to.

A list that failed leaves the others to answer; nothing beside a failed list is that
failure, so the source reads as unavailable and never as an empty day (ADR-292).

The client is open for the length of the read and closed before it returns (ADR-304).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any, Final
from uuid import UUID

from src.core.constants import TASK_LISTS_READ_MAX
from src.core.task_due import in_due_order, task_due_day
from src.domains.briefing.constants import ERROR_CODE_CONNECTOR_OAUTH_EXPIRED
from src.domains.briefing.exceptions import ConnectorAccessError
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable, open_active_client
from src.domains.connectors.clients.task_lists import (
    PROVIDER_FAILURES,
    TaskListing,
    read_every_task_list,
)
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
#: How many tasks one window is read for in each list (the bound is applied after the filter).
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


def task_line(raw: Mapping[str, Any], tz: tzinfo) -> TaskLine:
    """One provider task (Google Tasks shape) as the radio reads it, its day on the listener's clock."""
    task_id = raw.get("id")
    return TaskLine(
        id=str(task_id) if task_id else None,
        title=str(raw.get("title") or "").strip() or "Untitled",
        completed=raw.get("status") == _COMPLETED,
        due=task_due_day(raw, tz),
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


async def _tasks(user_id: UUID, listing: TaskListing) -> list[dict[str, Any]]:
    """The listener's tasks from every list, as the provider lists them, list after list.

    Raises:
        ConnectorAccessError: The tasks provider is connected but its credentials failed.
        Exception: The provider's own failure, when it left nothing to read.
    """
    async with open_active_client("tasks", user_id) as opened:
        if opened is ClientUnavailable.NO_CREDENTIALS:
            raise ConnectorAccessError(
                "tasks", ERROR_CODE_CONNECTOR_OAUTH_EXPIRED, "credentials refused"
            )
        if not isinstance(opened, ActiveClient):
            return []  # no tasks provider connected: nothing to read
        every = await read_every_task_list(
            opened.client, listing, lists_max=TASK_LISTS_READ_MAX, failures=PROVIDER_FAILURES
        )
    return every.tasks_or_failure()


async def read_tasks_done(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The tasks completed today, read from the listener's tasks provider.

    The provider is asked for the tasks completed since the listener's midnight (the
    bound of the scan); the listener's clock then decides which are today's.
    """
    since = datetime.combine(now.astimezone(tz).date(), time(), tzinfo=tz)
    raw = await _tasks(
        user_id,
        TaskListing(
            max_results=_SCAN_TASKS,
            show_completed=True,
            show_hidden=True,
            completed_min=since.isoformat(),
        ),
    )
    return tasks_done_drafts([task_line(item, tz) for item in raw], now=now, tz=tz)[
        : MAX_PER_SOURCE[PersonalSource.TASKS]
    ]


async def read_tasks_ahead(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The open tasks due in the week ahead, read from the listener's tasks provider.

    The soonest come first across the lists, so the source's bound never keeps one
    list's whole week ahead of another list's tomorrow.
    """
    today = now.astimezone(tz).date()
    first = datetime.combine(today + timedelta(days=1), time(), tzinfo=tz)
    last = datetime.combine(today + timedelta(days=AHEAD_DAYS + 1), time(), tzinfo=tz)
    raw = await _tasks(
        user_id,
        TaskListing(max_results=_SCAN_TASKS, due_min=first.isoformat(), due_max=last.isoformat()),
    )
    return tasks_ahead_drafts(
        [task_line(item, tz) for item in in_due_order(raw, tz)], now=now, tz=tz
    )[: MAX_PER_SOURCE[PersonalSource.TASKS]]


__all__ = [
    "AHEAD_DAYS",
    "TaskLine",
    "read_tasks_ahead",
    "read_tasks_done",
    "task_line",
    "tasks_ahead_drafts",
    "tasks_done_drafts",
]
