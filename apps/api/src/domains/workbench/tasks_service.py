"""The tasks of the « Tools » section, by the person's own hand (ADR-369).

Each call opens the account's tasks provider through the door — no session is
held while it answers (ADR-304) —, makes its provider call under the
workbench's failure contract (``provider_call``) and answers in the section's
vocabulary (``schemas/tasks``): a due date is a DAY (``task_dates``),
completion a boolean, a page says whether more exists. A create runs once per
submission (``run_once``). A gesture the provider lacks — a subtask on To Do —
is refused before anything is sent: its client would drop it in silence.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.domains.connectors.clients.protocols import TasksClientProtocol
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, refuse
from src.domains.workbench.features import PROVIDER_FEATURES, WorkbenchFeature, WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.schemas.tasks import (
    NewTask,
    NewTaskList,
    Task,
    TaskChange,
    TaskList,
    TaskListsPage,
    TasksPage,
)
from src.domains.workbench.task_dates import due_for_provider, due_from_provider

_TOOL = WorkbenchTool.TASKS


async def list_task_lists(user_id: UUID, *, page_token: str | None = None) -> TaskListsPage:
    """One page of the account's task lists."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "list_lists", act=False):
            raw = await client.list_task_lists(listing_page_size(), page_token=page_token)
    return TaskListsPage(
        items=[_task_list(item) for item in raw.get("items") or []],
        next_page_token=raw.get("next_page_token") or None,
    )


async def create_task_list(user_id: UUID, request: NewTaskList) -> TaskList:
    """Create a list, once per submission."""

    async def create() -> TaskList:
        async with open_tool_client(_TOOL, user_id) as opened:
            _require(opened.connector_type, WorkbenchFeature.LIST_MANAGEMENT)
            client: TasksClientProtocol = opened.client
            async with provider_call(_TOOL, "create_list", act=True):
                raw = await client.create_task_list(request.title)
        return _task_list(raw)

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
        _require(opened.connector_type, WorkbenchFeature.LIST_MANAGEMENT)
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
        items=[_task(item, provider, zone) for item in raw.get("items") or []],
        next_page_token=raw.get("next_page_token") or None,
    )


async def create_task(user_id: UUID, zone: ZoneInfo, request: NewTask) -> Task:
    """Create a task, once per submission."""

    async def create() -> Task:
        async with open_tool_client(_TOOL, user_id) as opened:
            provider = opened.connector_type
            if request.parent is not None:
                _require(provider, WorkbenchFeature.SUBTASKS)
            client: TasksClientProtocol = opened.client
            due = due_for_provider(provider, request.due, zone) if request.due else None
            async with provider_call(_TOOL, "create", act=True):
                raw = await client.create_task(
                    request.list_id,
                    title=request.title,
                    notes=request.notes,
                    due=due,
                    parent=request.parent,
                )
        return _task(raw, provider, zone)

    return await run_once(
        user_id,
        request.idempotency_key,
        create,
        tool=_TOOL.value,
        record=lambda made: {"task_id": made.id},
    )


async def update_task(user_id: UUID, zone: ZoneInfo, request: TaskChange) -> Task:
    """Change a task: what the request leaves out is kept; a null due removes it."""
    async with open_tool_client(_TOOL, user_id) as opened:
        provider = opened.connector_type
        client: TasksClientProtocol = opened.client
        due = due_for_provider(provider, request.due, zone) if request.due else None
        status = None if request.completed is None else _status(request.completed)
        async with provider_call(_TOOL, "update", act=True):
            raw = await client.update_task(
                request.list_id,
                request.task_id,
                title=request.title,
                notes=request.notes,
                due=due,
                status=status,
                clear_due=request.removes_due,
            )
    return _task(raw, provider, zone)


async def delete_task(user_id: UUID, *, list_id: str, task_id: str) -> None:
    """Delete one task."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "delete", act=True):
            await client.delete_task(list_id, task_id)


def _require(provider: ConnectorType, feature: WorkbenchFeature) -> None:
    """Refuse, unsent, a gesture the active provider does not accept."""
    if feature not in PROVIDER_FEATURES[provider]:
        refuse(NOT_SUPPORTED_BY_PROVIDER)


def _status(completed: bool) -> str:
    return "completed" if completed else "needsAction"


def _task_list(raw: Mapping[str, Any]) -> TaskList:
    return TaskList(id=str(raw.get("id") or ""), title=str(raw.get("title") or ""))


def _task(raw: Mapping[str, Any], provider: ConnectorType, zone: ZoneInfo) -> Task:
    return Task(
        id=str(raw.get("id") or ""),
        title=str(raw.get("title") or ""),
        notes=raw.get("notes") or None,
        completed=raw.get("status") == "completed",
        due=due_from_provider(provider, raw.get("due"), zone),
        parent=raw.get("parent") or None,
        position=raw.get("position") or None,
    )
