"""The tasks of the « Tools » section, by the person's own hand (ADR-369).

Each call opens the account's tasks provider through the door — no session is
held while it answers (ADR-304) —, makes its provider call under the
workbench's failure contract (``provider_call``) and answers in the section's
vocabulary (``schemas/tasks``): a due date is a DAY (``task_dates``),
completion a boolean, a page says whether more exists. A create runs once per
submission (``run_once``). A gesture the provider lacks — a subtask on To Do,
an importance on Google — is refused before anything is sent: its client would
drop it in silence. A view gathers what every list holds: for one stretch of the
account's days, or every open task, dated or not; the lists are walked through the
one door (``connectors/clients/task_lists``). Moving, renaming and thinning a list
live in ``tasks_organize``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.constants import WORKBENCH_DUE_TASKS_PAGES_MAX, WORKBENCH_TASK_UPCOMING_DAYS
from src.core.exceptions import BaseAPIException
from src.core.time_utils import now_utc
from src.domains.connectors.clients.protocols import TasksClientProtocol
from src.domains.connectors.clients.task_details import TaskDetails
from src.domains.connectors.clients.task_lists import (
    TaskListing,
    TaskListRead,
    read_task_lists,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.owner_defaults import TASK_LIST
from src.domains.connectors.preferences.resolver import is_preferred
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import INVALID_REQUEST, NOT_SUPPORTED_BY_PROVIDER, refuse
from src.domains.workbench.features import PROVIDER_FEATURES, WorkbenchFeature, WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.schemas.tasks import (
    DueTask,
    DueTasks,
    DueTasksQuery,
    NewTask,
    NewTaskList,
    Task,
    TaskChange,
    TaskList,
    TaskListsPage,
    TasksPage,
    TaskStep,
    TaskViewQuery,
    ViewTask,
    ViewTasks,
)
from src.domains.workbench.task_dates import due_for_provider, due_from_provider

_TOOL = WorkbenchTool.TASKS
#: The days a read gathers, both included; None gathers every open task, dated or not.
_Days = tuple[date, date] | None


async def list_task_lists(user_id: UUID, *, page_token: str | None = None) -> TaskListsPage:
    """One page of the account's task lists, the settings' default named."""
    async with open_tool_client(_TOOL, user_id, container=TASK_LIST) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "list_lists", act=False):
            raw = await client.list_task_lists(listing_page_size(), page_token=page_token)
    preferred = opened.preferred_name
    return TaskListsPage(
        items=[task_list_of(item, preferred) for item in raw.get("items") or []],
        next_page_token=raw.get("next_page_token") or None,
    )


async def create_task_list(user_id: UUID, request: NewTaskList) -> TaskList:
    """Create a list, once per submission."""

    async def create() -> TaskList:
        async with open_tool_client(_TOOL, user_id) as opened:
            require_feature(opened.connector_type, WorkbenchFeature.LIST_MANAGEMENT)
            client: TasksClientProtocol = opened.client
            async with provider_call(_TOOL, "create_list", act=True):
                raw = await client.create_task_list(request.title)
        return task_list_of(raw)

    return await run_once(
        user_id,
        request.idempotency_key,
        create,
        tool=_TOOL.value,
        record=lambda made: {"list_id": made.id},
    )


async def delete_task_list(user_id: UUID, list_id: str) -> None:
    """Delete a list and every task in it."""
    async with open_tool_client(_TOOL, user_id) as opened:
        require_feature(opened.connector_type, WorkbenchFeature.LIST_MANAGEMENT)
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "delete_list", act=True):
            await client.delete_task_list(list_id)


async def list_tasks(
    user_id: UUID,
    zone: ZoneInfo,
    *,
    list_id: str,
    show_completed: bool = False,
    page_token: str | None = None,
) -> TasksPage:
    """One page of a list's tasks.

    Completed tasks are asked for with the hidden ones: Google hides a task
    completed in its own apps unless both are asked (its documented rule).
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "list", act=False):
            raw = await client.list_tasks(
                list_id,
                max_results=listing_page_size(),
                show_completed=show_completed,
                show_hidden=show_completed,
                page_token=page_token,
            )
        provider = opened.connector_type
    return TasksPage(
        items=[task_of(item, provider, zone) for item in raw.get("items") or []],
        next_page_token=raw.get("next_page_token") or None,
    )


async def read_due_tasks(user_id: UUID, zone: ZoneInfo, query: DueTasksQuery) -> DueTasks:
    """The open tasks due over the days shown, every list asked, a few at a time.

    Args:
        user_id: The account.
        zone: Its zone, which decides the day a To Do instant falls on.
        query: The days shown.

    Returns:
        What was read, earliest first; what could not be is said, never silent.

    Raises:
        BaseAPIException: Every list failed: nothing can be drawn.
    """
    read = await _read_across(user_id, zone, (query.start, query.end))
    return DueTasks(
        tasks=[
            DueTask(id=task.id, list_id=task.list_id, title=task.title, due=task.due)
            for task in read.tasks
            if task.due is not None
        ],
        truncated=read.truncated,
        failed=read.failed,
    )


async def read_task_view(user_id: UUID, zone: ZoneInfo, query: TaskViewQuery) -> ViewTasks:
    """The open tasks of a view, every list asked, in the account's day.

    Args:
        user_id: The account.
        zone: Its zone, which decides what today is.
        query: The view.

    Returns:
        What was read, the earliest first and the undated last; what could not be is said,
        never silent.

    Raises:
        BaseAPIException: Every list failed: nothing can be shown.
    """
    return await _read_across(user_id, zone, _view_days(query, now_utc().astimezone(zone).date()))


def _view_days(query: TaskViewQuery, today: date) -> _Days:
    """The days a view gathers: a late task may be as old as the person's oldest."""
    if query.view == "all":
        return None
    if query.view == "today":
        return today, today
    yesterday = today - timedelta(days=1)
    if query.view == "overdue":
        return date.min, yesterday
    horizon = today + timedelta(days=WORKBENCH_TASK_UPCOMING_DAYS)
    if query.view == "timeline":
        # The three views together: what is late, today's and the days ahead.
        return date.min, horizon
    return today + timedelta(days=1), horizon


async def _read_across(user_id: UUID, zone: ZoneInfo, days: _Days) -> ViewTasks:
    """What every list holds and is still to do, over some days or whatever its day."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "list_lists", act=False):
            lists = await client.list_task_lists(listing_page_size())
        ids = [str(item.get("id")) for item in lists.get("items") or []]
        read = await read_task_lists(
            client,
            ids,
            TaskListing(max_results=listing_page_size(), pages_max=WORKBENCH_DUE_TASKS_PAGES_MAX),
            failures=(BaseAPIException,),
            guard=lambda: provider_call(_TOOL, "list", act=False),
        )
        provider = opened.connector_type
    _refuse_when_every_list_failed(read)
    return ViewTasks(
        tasks=_in_time_order(ids, read, provider, zone, days),
        truncated=bool(lists.get("next_page_token")) or any(item.cut for item in read),
        failed=[list_id for list_id, item in zip(ids, read, strict=True) if item.failure],
    )


def _refuse_when_every_list_failed(read: list[TaskListRead]) -> None:
    """A read where no list answered is the refusal of the first: nothing can be shown."""
    refusals = [item.failure for item in read if item.failure is not None]
    if read and len(refusals) == len(read):
        raise refusals[0]


def _in_time_order(
    ids: list[str],
    read: list[TaskListRead],
    provider: ConnectorType,
    zone: ZoneInfo,
    days: _Days,
) -> list[ViewTask]:
    """The tasks kept, the earliest first; the undated last, in their lists' own order."""
    kept = [
        task
        for list_id, item in zip(ids, read, strict=True)
        for task in _within(item.items, list_id, provider, zone, days)
    ]
    return sorted(kept, key=lambda task: (task.due is None, task.due or date.min))


def _within(
    items: Iterable[Mapping[str, Any]],
    list_id: str,
    provider: ConnectorType,
    zone: ZoneInfo,
    days: _Days,
) -> list[ViewTask]:
    """The tasks of a list that fall within the days; every one of them without days."""
    found: list[ViewTask] = []
    for item in items:
        task = task_of(item, provider, zone)
        if days is None or (task.due is not None and days[0] <= task.due <= days[1]):
            found.append(ViewTask(id=task.id, list_id=list_id, title=task.title, due=task.due))
    return found


async def create_task(user_id: UUID, zone: ZoneInfo, request: NewTask) -> Task:
    """Create a task, once per submission."""

    async def create() -> Task:
        async with open_tool_client(_TOOL, user_id) as opened:
            provider = opened.connector_type
            if request.parent is not None:
                require_feature(provider, WorkbenchFeature.SUBTASKS)
            if request.steps:
                require_feature(provider, WorkbenchFeature.TASK_STEPS)
            details = _new_details(request)
            if details is not None:
                require_feature(provider, WorkbenchFeature.TASK_DETAILS)
            client: TasksClientProtocol = opened.client
            due = due_for_provider(provider, request.due, zone) if request.due else None
            async with provider_call(_TOOL, "create", act=True):
                raw = await client.create_task(
                    request.list_id,
                    title=request.title,
                    notes=request.notes,
                    due=due.value if due else None,
                    parent=request.parent,
                    details=details,
                    steps=tuple(request.steps),
                    due_zone=due.zone if due else None,
                )
        return task_of(raw, provider, zone)

    return await run_once(
        user_id,
        request.idempotency_key,
        create,
        tool=_TOOL.value,
        record=lambda made: {"task_id": made.id},
    )


async def read_task(user_id: UUID, zone: ZoneInfo, *, list_id: str, task_id: str) -> Task:
    """One task, whole: the home opens one the open page does not hold (2026-11-07)."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "read", act=False):
            raw = await client.get_task(list_id, task_id)
        provider = opened.connector_type
    return task_of(raw, provider, zone)


async def update_task(user_id: UUID, zone: ZoneInfo, request: TaskChange) -> Task:
    """Change a task: what the request leaves out is kept; a null due removes it."""
    async with open_tool_client(_TOOL, user_id) as opened:
        provider = opened.connector_type
        client: TasksClientProtocol = opened.client
        details = await _changed_details(client, provider, zone, request)
        due = due_for_provider(provider, request.due, zone) if request.due else None
        status = None if request.completed is None else completion_status(request.completed)
        async with provider_call(_TOOL, "update", act=True):
            raw = await client.update_task(
                request.list_id,
                request.task_id,
                title=request.title,
                notes=request.notes,
                due=due.value if due else None,
                due_zone=due.zone if due else None,
                status=status,
                clear_due=request.removes_due,
                details=details,
            )
    return task_of(raw, provider, zone)


async def delete_task(user_id: UUID, *, list_id: str, task_id: str) -> None:
    """Delete one task."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "delete", act=True):
            await client.delete_task(list_id, task_id)


def _new_details(request: NewTask) -> TaskDetails | None:
    """What a new task carries beyond a title, notes and a day; None when it is nothing."""
    if request.importance is None and request.reminder is None and request.repeat is None:
        return None
    return TaskDetails(
        importance=request.importance,
        reminder=request.reminder,
        repeat=request.repeat,
        repeat_from=request.due if request.repeat else None,
    )


async def _changed_details(
    client: TasksClientProtocol, provider: ConnectorType, zone: ZoneInfo, request: TaskChange
) -> TaskDetails | None:
    """What a change touches of what To Do alone keeps; None when it touches none of it."""
    if not request.changes_details:
        return None
    require_feature(provider, WorkbenchFeature.TASK_DETAILS)
    start = None
    if request.repeat is not None:
        start = request.due or await _held_day(client, provider, zone, request)
        if start is None:
            refuse(INVALID_REQUEST)
    return TaskDetails(
        importance=request.importance,
        reminder=request.reminder,
        clear_reminder=request.removes_reminder,
        repeat=request.repeat,
        repeat_from=start,
        clear_repeat=request.removes_repeat,
    )


async def _held_day(
    client: TasksClientProtocol, provider: ConnectorType, zone: ZoneInfo, request: TaskChange
) -> date | None:
    """The day a task already holds: a repetition starts on it."""
    async with provider_call(_TOOL, "read", act=False):
        raw = await client.get_task(request.list_id, request.task_id)
    return due_from_provider(provider, raw.get("due"), zone)


def require_feature(provider: ConnectorType, feature: WorkbenchFeature) -> None:
    """Refuse, unsent, a gesture the active provider does not accept."""
    if feature not in PROVIDER_FEATURES[provider]:
        refuse(NOT_SUPPORTED_BY_PROVIDER)


def completion_status(completed: bool) -> str:
    """The provider's word for a task done or not done."""
    return "completed" if completed else "needsAction"


def task_list_of(raw: Mapping[str, Any], preferred: str | None = None) -> TaskList:
    """A list in the section's vocabulary, the settings' default named."""
    return TaskList(
        id=str(raw.get("id") or ""),
        title=str(raw.get("title") or ""),
        default=is_preferred(preferred, raw.get("title"), raw.get("id")),
    )


def _instant(raw: str | None) -> datetime | None:
    """An instant the client answered in RFC 3339; None without a readable one."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def task_of(raw: Mapping[str, Any], provider: ConnectorType, zone: ZoneInfo) -> Task:
    """A task in the section's vocabulary."""
    return Task(
        id=str(raw.get("id") or ""),
        title=str(raw.get("title") or ""),
        notes=raw.get("notes") or None,
        completed=raw.get("status") == "completed",
        due=due_from_provider(provider, raw.get("due"), zone),
        parent=raw.get("parent") or None,
        position=raw.get("position") or None,
        steps=[TaskStep.model_validate(step) for step in raw.get("steps") or []],
        importance=raw.get("importance") or None,
        reminder=_instant(raw.get("reminder")),
        repeat=raw.get("repeat") or None,
    )
