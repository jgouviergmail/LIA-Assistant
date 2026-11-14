"""The tasks card's assembly: what every list gave, as the card shows it (2026-11-10).

The card gathers every list of the tasks provider (``fetchers.fetch_tasks`` reads them through
the one walk, ``connectors/clients/task_lists``, which stamps each task with its own list).
What is decided here is pure: which tasks stand on the card and in what order, each naming its
list by its real id, where the Tools open it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, tzinfo
from typing import Any

from src.core.field_names import FIELD_TASK_LIST_ID, FIELD_TASK_LIST_NAME
from src.domains.briefing.formatters import format_task_item
from src.domains.briefing.schemas import TaskItem


def card_items(tasks: Iterable[dict[str, Any]], *, today: date, zone: tzinfo) -> list[TaskItem]:
    """Every list's pending tasks as card items, in the card's order.

    Args:
        tasks: The tasks read, each carrying its own list (``EveryTaskList.tasks``).
        today: The person's today.
        zone: The account's zone, which a To Do due is read in.

    Returns:
        The items, overdue first (the oldest first), then by due day; the undated last.
    """
    items = [
        item
        for task in tasks
        if (
            item := format_task_item(
                task,
                today,
                zone=zone,
                list_id=task.get(FIELD_TASK_LIST_ID),
                list_name=task.get(FIELD_TASK_LIST_NAME),
            )
        )
        is not None
    ]
    items.sort(key=_card_order)
    return items


def _card_order(item: TaskItem) -> tuple[bool, int]:
    return item.days_until_due is None, item.days_until_due or 0


__all__ = ["card_items"]
