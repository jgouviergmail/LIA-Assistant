"""Organising the tasks of the « Tools » section, by the person's own hand (ADR-369, lot 9).

What moves, renames, sorts or thins a list, beside what writes a task (``tasks_service``). An
act on a selection answers item by item (``selection_acts``). What the provider lacks is refused
before anything is sent: steps are To Do's, an order Google's.

Clearing what is done DELETES it, on both providers: Google's own `clear` only hides a task from
a listing, and the screen's « completed » listing asks for the hidden ones, so it would answer
the person's click by changing nothing they can see.
"""

from __future__ import annotations

from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.constants import WORKBENCH_DUE_TASKS_PAGES_MAX, WORKBENCH_TASKS_CLEAR_MAX
from src.domains.connectors.clients.protocols import (
    TaskOrderProtocol,
    TasksClientProtocol,
    TaskStepsProtocol,
)
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.features import WorkbenchFeature, WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.tasks import (
    MovedTask,
    NewTaskStep,
    Task,
    TaskList,
    TaskListRename,
    TaskMoveOutcome,
    TaskPlacement,
    TasksCleared,
    TaskSelection,
    TaskSelectionCompletion,
    TaskSelectionMove,
    TaskStep,
    TaskStepChange,
)
from src.domains.workbench.selection_acts import act_outcome, settle_each
from src.domains.workbench.tasks_service import (
    completion_status,
    require_feature,
    task_list_of,
    task_of,
)

_TOOL = WorkbenchTool.TASKS


async def rename_task_list(user_id: UUID, request: TaskListRename) -> TaskList:
    """Rename a list."""
    async with open_tool_client(_TOOL, user_id) as opened:
        require_feature(opened.connector_type, WorkbenchFeature.LIST_MANAGEMENT)
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "rename_list", act=True):
            raw = await client.rename_task_list(request.list_id, request.title)
    return task_list_of(raw)


async def set_completed(user_id: UUID, request: TaskSelectionCompletion) -> ActOutcome:
    """Mark a selection done or not done; each task answered."""
    status = completion_status(request.completed)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "complete_selection", act=True):
            settled = await settle_each(
                request.task_ids,
                lambda task_id: client.update_task(request.list_id, task_id, status=status),
            )
            return act_outcome(request.task_ids, settled, tool=_TOOL.value)


async def delete_tasks(user_id: UUID, request: TaskSelection) -> ActOutcome:
    """Delete a selection; each task answered."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "delete_selection", act=True):
            settled = await settle_each(
                request.task_ids, lambda task_id: client.delete_task(request.list_id, task_id)
            )
            return act_outcome(request.task_ids, settled, tool=_TOOL.value)


async def move_tasks(user_id: UUID, request: TaskSelectionMove) -> TaskMoveOutcome:
    """Send a selection to another list; each task answered, with its id from now on.

    Args:
        user_id: The account.
        request: The tasks, their list and the one they go to.

    Returns:
        What each became: To Do gives a copy another id, and a task that could not be removed
        from its list is said to stand in both.
    """
    moved: dict[str, str] = {}
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client

        async def move(task_id: str) -> None:
            raw = await client.move_task(request.list_id, task_id, request.destination_list_id)
            moved[task_id] = str(raw.get("id") or task_id)

        async with provider_call(_TOOL, "move", act=True):
            settled = await settle_each(request.task_ids, move)
            outcome = act_outcome(request.task_ids, settled, tool=_TOOL.value)
    return TaskMoveOutcome(
        done=outcome.done,
        failed=outcome.failed,
        moved=[MovedTask(id=old, new_id=new) for old, new in moved.items()],
    )


async def clear_completed(user_id: UUID, list_id: str) -> TasksCleared:
    """Delete what a list holds as done, up to the published bound.

    Args:
        user_id: The account.
        list_id: The list.

    Returns:
        How many went, and whether done tasks remain. A subtask gone with its parent went.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        client: TasksClientProtocol = opened.client
        async with provider_call(_TOOL, "clear_completed", act=True):
            ids, more = await _completed_ids(client, list_id)
            settled = await settle_each(ids, lambda task_id: client.delete_task(list_id, task_id))
            outcome = act_outcome(ids, settled, tool=_TOOL.value)
    left = [item for item in outcome.failed if item.status != "not_found"]
    return TasksCleared(deleted=len(ids) - len(left), remaining=more or bool(left))


async def _completed_ids(client: TasksClientProtocol, list_id: str) -> tuple[list[str], bool]:
    """The done tasks of a list, within the bound, and whether it holds more."""
    found: list[str] = []
    token: str | None = None
    for _page in range(WORKBENCH_DUE_TASKS_PAGES_MAX):
        raw = await client.list_tasks(
            list_id,
            max_results=listing_page_size(),
            show_completed=True,
            show_hidden=True,
            page_token=token,
        )
        found += [
            str(item.get("id"))
            for item in raw.get("items") or []
            if item.get("status") == "completed"
        ]
        token = raw.get("next_page_token") or None
        if token is None or len(found) > WORKBENCH_TASKS_CLEAR_MAX:
            break
    return found[:WORKBENCH_TASKS_CLEAR_MAX], (
        token is not None or len(found) > WORKBENCH_TASKS_CLEAR_MAX
    )


async def place_task(user_id: UUID, zone: ZoneInfo, request: TaskPlacement) -> Task:
    """Put a task after another of its siblings, or first."""
    async with open_tool_client(_TOOL, user_id) as opened:
        provider = opened.connector_type
        require_feature(provider, WorkbenchFeature.TASK_ORDER)
        client: TaskOrderProtocol = opened.client
        async with provider_call(_TOOL, "place", act=True):
            raw = await client.place_task(request.list_id, request.task_id, request.after)
    return task_of(raw, provider, zone)


async def add_step(user_id: UUID, request: NewTaskStep) -> TaskStep:
    """Add a step to a task, once per submission."""

    async def add() -> TaskStep:
        async with open_tool_client(_TOOL, user_id) as opened:
            require_feature(opened.connector_type, WorkbenchFeature.TASK_STEPS)
            client: TaskStepsProtocol = opened.client
            async with provider_call(_TOOL, "add_step", act=True):
                raw = await client.add_task_step(request.list_id, request.task_id, request.title)
        return TaskStep.model_validate(raw)

    return await run_once(
        user_id,
        request.idempotency_key,
        add,
        tool=_TOOL.value,
        record=lambda made: {"step_id": made.id},
    )


async def change_step(user_id: UUID, request: TaskStepChange) -> TaskStep:
    """Change a step: what the request leaves out is kept."""
    async with open_tool_client(_TOOL, user_id) as opened:
        require_feature(opened.connector_type, WorkbenchFeature.TASK_STEPS)
        client: TaskStepsProtocol = opened.client
        async with provider_call(_TOOL, "change_step", act=True):
            raw = await client.change_task_step(
                request.list_id,
                request.task_id,
                request.step_id,
                title=request.title,
                checked=request.checked,
            )
    return TaskStep.model_validate(raw)


async def remove_step(user_id: UUID, *, list_id: str, task_id: str, step_id: str) -> None:
    """Remove a step."""
    async with open_tool_client(_TOOL, user_id) as opened:
        require_feature(opened.connector_type, WorkbenchFeature.TASK_STEPS)
        client: TaskStepsProtocol = opened.client
        async with provider_call(_TOOL, "remove_step", act=True):
            await client.remove_task_step(list_id, task_id, step_id)
