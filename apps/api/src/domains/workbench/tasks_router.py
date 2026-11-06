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
from src.domains.workbench import tasks_organize, tasks_service
from src.domains.workbench.ids import OptionalPageToken, ProviderId
from src.domains.workbench.rate_limits import (
    charge_selection,
    rate_limit_bulk,
    rate_limit_read,
    rate_limit_write,
)
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.tasks import (
    DueTasks,
    DueTasksQuery,
    NewTask,
    NewTaskList,
    NewTaskStep,
    Task,
    TaskChange,
    TaskList,
    TaskListClear,
    TaskListRename,
    TaskListsPage,
    TaskMoveOutcome,
    TaskPlacement,
    TasksCleared,
    TaskSelection,
    TaskSelectionCompletion,
    TaskSelectionMove,
    TasksPage,
    TaskStep,
    TaskStepChange,
    TaskViewQuery,
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


@router.patch(
    "/lists",
    response_model=TaskList,
    summary="Rename a task list",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_task_list(request: TaskListRename, user: _Account) -> TaskList:
    """Rename a task list."""
    return await tasks_organize.rename_task_list(user.id, request)


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
    "/due",
    response_model=DueTasks,
    summary="The open tasks due over the days a calendar shows",
    dependencies=[Depends(rate_limit_read)],
)
async def get_due_tasks(query: Annotated[DueTasksQuery, Query()], user: _Account) -> DueTasks:
    """The dated tasks of every list, for the calendar to draw."""
    return await tasks_service.read_due_tasks(user.id, resolve_user_timezone(user), query)


@router.get(
    "/view",
    response_model=DueTasks,
    summary="What every list holds for today, overdue or the days ahead",
    dependencies=[Depends(rate_limit_read)],
)
async def get_task_view(query: Annotated[TaskViewQuery, Query()], user: _Account) -> DueTasks:
    """A view across the lists, in the account's day."""
    return await tasks_service.read_task_view(user.id, resolve_user_timezone(user), query)


@router.post(
    "/selection/completed",
    response_model=ActOutcome,
    summary="Mark a selection done or not done; each task answered",
)
async def post_selection_completed(request: TaskSelectionCompletion, user: _Account) -> ActOutcome:
    """Mark tasks done or not done."""
    await charge_selection(user, len(request.task_ids))
    return await tasks_organize.set_completed(user.id, request)


@router.post(
    "/selection/delete",
    response_model=ActOutcome,
    summary="Delete a selection; each task answered",
)
async def post_selection_delete(request: TaskSelection, user: _Account) -> ActOutcome:
    """Delete tasks."""
    await charge_selection(user, len(request.task_ids))
    return await tasks_organize.delete_tasks(user.id, request)


@router.post(
    "/selection/move",
    response_model=TaskMoveOutcome,
    summary="Send a selection to another list; each task answered with its id from now on",
)
async def post_selection_move(request: TaskSelectionMove, user: _Account) -> TaskMoveOutcome:
    """Move tasks to another list."""
    await charge_selection(user, len(request.task_ids))
    return await tasks_organize.move_tasks(user.id, request)


@router.post(
    "/clear-completed",
    response_model=TasksCleared,
    summary="Delete what a list holds as done, up to the published bound",
    dependencies=[Depends(rate_limit_bulk)],
)
async def post_clear_completed(request: TaskListClear, user: _Account) -> TasksCleared:
    """Delete a list's done tasks."""
    return await tasks_organize.clear_completed(user.id, request.list_id)


@router.post(
    "/place",
    response_model=Task,
    summary="Put a task after another of its siblings, or first (Google only)",
    dependencies=[Depends(rate_limit_write)],
)
async def post_task_place(request: TaskPlacement, user: _Account) -> Task:
    """Reorder a task."""
    return await tasks_organize.place_task(user.id, resolve_user_timezone(user), request)


@router.post(
    "/steps",
    response_model=TaskStep,
    status_code=status.HTTP_201_CREATED,
    summary="Add a step to a task, once per submission (To Do only)",
    dependencies=[Depends(rate_limit_write)],
)
async def post_task_step(request: NewTaskStep, user: _Account) -> TaskStep:
    """Add a step."""
    return await tasks_organize.add_step(user.id, request)


@router.patch(
    "/steps",
    response_model=TaskStep,
    summary="Change a step (To Do only)",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_task_step(request: TaskStepChange, user: _Account) -> TaskStep:
    """Change a step."""
    return await tasks_organize.change_step(user.id, request)


@router.delete(
    "/steps",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a step (To Do only)",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_task_step(
    list_id: _ListId,
    task_id: Annotated[ProviderId, Query(description="The task.")],
    step_id: Annotated[ProviderId, Query(description="The step.")],
    user: _Account,
) -> None:
    """Remove a step."""
    await tasks_organize.remove_step(user.id, list_id=list_id, task_id=task_id, step_id=step_id)


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
