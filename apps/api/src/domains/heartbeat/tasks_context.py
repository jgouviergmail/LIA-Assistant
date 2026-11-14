"""The person's pending tasks for the heartbeat decision: every list, the most pressing first.

Whoever reads a person's tasks reads ALL their lists (owner rule, 2026-11-10): a task due
tomorrow in « Home » weighs as much as one in the list the connector's settings name as the
default — which is where a NEW task goes when nobody names one, and nothing else. The lists are
read through the one walk (``connectors/clients/task_lists``); a list that failed leaves the
others to answer, and nothing beside a failed list is that failure: the source then reads
``failed``, never « no task ».

The client is open for the length of the read and closed before the tasks are shaped (ADR-304).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any, Final
from uuid import UUID

import structlog

from src.core.constants import HEARTBEAT_CONTEXT_TASKS_MAX, TASK_LISTS_READ_MAX
from src.core.field_names import FIELD_TASK_LIST_NAME
from src.core.task_due import in_due_order, task_due_day
from src.domains.connectors.active_client import ActiveClient, open_active_client
from src.domains.connectors.clients.task_lists import (
    PROVIDER_FAILURES,
    TaskListing,
    read_every_task_list,
)
from src.domains.heartbeat.context_sources import resolve_user_tz

logger = structlog.get_logger(__name__)

#: The provider's status of a task still to do.
_PENDING: Final = "needsAction"


def due_label(task: Mapping[str, Any], zone: tzinfo) -> str:
    """A task's due day for the prompt, through the one door (``core/task_due``).

    A Google due is the date it names; a To Do due is local midnight, which Graph answers in UTC
    (the evening before east of Greenwich): its day is that instant read in the account's zone.

    Args:
        task: A task as the clients answer it.
        zone: The account's zone.

    Returns:
        ``YYYY-MM-DD``, or « no date » without a readable one.
    """
    day = task_due_day(task, zone)
    return day.isoformat() if day else "no date"


def is_task_overdue(task: Mapping[str, Any], today: date, zone: tzinfo) -> bool:
    """Whether a task still to do has a day that passed on the person's clock.

    Args:
        task: A task as the clients answer it.
        today: The person's today.
        zone: The account's zone, which a To Do due is read in.

    Returns:
        True once its day has passed; never on the day itself, once done or without a day.
    """
    if task.get("status") != _PENDING:
        return False
    day = task_due_day(task, zone)
    return day is not None and day < today


def pending_tasks_context(
    tasks: list[dict[str, Any]], *, today: date, zone: tzinfo
) -> list[dict[str, Any]]:
    """What the decision reads of the tasks: the most pressing first, under the prompt's bound.

    Args:
        tasks: The tasks of every list, each carrying its own list's name.
        today: The person's today.
        zone: The account's zone.

    Returns:
        Each task's title, due day, whether it is overdue and the list it lives in; the tasks
        still to do only, the earliest due first across the lists.
    """
    pending = [task for task in tasks if task.get("status") == _PENDING]
    return [
        {
            "title": task.get("title", "Untitled"),
            "due": due_label(task, zone),
            "overdue": is_task_overdue(task, today, zone),
            "list": task.get(FIELD_TASK_LIST_NAME),
        }
        for task in in_due_order(pending, zone)[:HEARTBEAT_CONTEXT_TASKS_MAX]
    ]


async def fetch_tasks_context(
    user_id: UUID,
    user: Any,
    settings: Any,
) -> list[dict[str, Any]] | None:
    """Fetch the pending and overdue tasks of every list of the active provider.

    Opens through the shared door (Google Tasks or Microsoft To Do).

    Args:
        user_id: Whose tasks.
        user: The account, for its timezone.
        settings: The settings, for how far ahead a due day is read.

    Returns:
        The task dicts, or None without a connected provider or anything pending.

    Raises:
        Exception: The provider's own failure, when it left nothing to show.
    """
    now = datetime.now(UTC)
    # RFC 3339 timestamp for the due_max filter (the undated tasks leave with it).
    due_max = (now + timedelta(days=settings.heartbeat_context_tasks_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    async with open_active_client("tasks", user_id) as opened:
        if not isinstance(opened, ActiveClient):
            return None
        every = await read_every_task_list(
            opened.client,
            TaskListing(max_results=HEARTBEAT_CONTEXT_TASKS_MAX, due_max=due_max),
            lists_max=TASK_LISTS_READ_MAX,
            failures=PROVIDER_FAILURES,
        )
    tasks = every.tasks_or_failure()
    if every.unread:
        logger.info(
            "heartbeat_tasks_lists_unread",
            user_id=str(user_id),
            lists_read=len(every.lists) - len(every.unread),
            lists_unread=len(every.unread),
        )
    zone = resolve_user_tz(user)
    return pending_tasks_context(tasks, today=now.astimezone(zone).date(), zone=zone) or None


__all__ = ["due_label", "fetch_tasks_context", "is_task_overdue", "pending_tasks_context"]
