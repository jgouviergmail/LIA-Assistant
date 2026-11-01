"""Routes of the « Tools » tasks screen (ADR-369).

Mounted under ``/workbench`` (the capability guard is the parent router's).
Every id and cursor travels in the query string or the body, bounded and
checked (``ids``); reads and writes are counted in two windows; the account's
zone decides which day a To Do due instant falls on.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.core.session_dependencies import get_current_active_session_for_stream
from src.core.time_utils import resolve_user_timezone
from src.domains.users.models import User
from src.domains.workbench import tasks_service
from src.domains.workbench.ids import OptionalPageToken, ProviderId
from src.domains.workbench.rate_limits import rate_limit_read, rate_limit_write
from src.domains.workbench.schemas.tasks import (
    NewTask,
    NewTaskList,
    Task,
    TaskChange,
    TaskList,
    TaskListsPage,
    TasksPage,
)

router = APIRouter(prefix="/tasks")

_Account = Annotated[User, Depends(get_current_active_session_for_stream)]
_ListId = Annotated[ProviderId, Query(description="The task list.")]
_Cursor = Annotated[OptionalPageToken, Query(description="The next page's token.")]


@router.get(
    "/lists",
    response_model=TaskListsPage,
    summary="One page of the account's task lists",
    dependencies=[Depends(rate_limit_read)],
)
async def get_task_lists(user: _Account, page_token: _Cursor = None) -> TaskListsPage:
    """List the task lists of the signed-in account."""
    return await tasks_service.list_task_lists(user.id, page_token=page_token)


@router.post(
    "/lists",
    response_model=TaskList,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task list, once per submission",
    dependencies=[Depends(rate_limit_write)],
)
async def post_task_list(request: NewTaskList, user: _Account) -> TaskList:
    """Create a task list."""
    return await tasks_service.create_task_list(user.id, request)


@router.delete(
    "/lists",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task list and its tasks",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_task_list(list_id: _ListId, user: _Account) -> None:
    """Delete a task list."""
    await tasks_service.delete_task_list(user.id, list_id)


@router.get(
    "",
    response_model=TasksPage,
    summary="One page of a list's tasks",
    dependencies=[Depends(rate_limit_read)],
)
async def get_tasks(
    list_id: _ListId,
    user: _Account,
    show_completed: Annotated[bool, Query(description="Include completed tasks.")] = False,
    page_token: _Cursor = None,
) -> TasksPage:
    """List the tasks of one list."""
    return await tasks_service.list_tasks(
        user.id,
        resolve_user_timezone(user),
        list_id=list_id,
        show_completed=show_completed,
        page_token=page_token,
    )


@router.post(
    "",
    response_model=Task,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task, once per submission",
    dependencies=[Depends(rate_limit_write)],
)
async def post_task(request: NewTask, user: _Account) -> Task:
    """Create a task."""
    return await tasks_service.create_task(user.id, resolve_user_timezone(user), request)


@router.patch(
    "",
    response_model=Task,
    summary="Change a task (a field left out is kept; a null due removes it)",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_task(request: TaskChange, user: _Account) -> Task:
    """Change a task."""
    return await tasks_service.update_task(user.id, resolve_user_timezone(user), request)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_task(
    list_id: _ListId,
    task_id: Annotated[ProviderId, Query(description="The task.")],
    user: _Account,
) -> None:
    """Delete a task."""
    await tasks_service.delete_task(user.id, list_id=list_id, task_id=task_id)
