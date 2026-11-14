"""The assistant's hands on how tasks are organised (ADR-369, lot 9, D2).

The account's lists, and what the screen gained, in the same lot. Both acts run at once: renaming
a list and moving a task are each undone by one more call, as completing a task is. On To Do a
move is a copy and the task comes back under another id, which the answer gives; a task left in
both lists is a failure the model reads, never a success.
"""

from __future__ import annotations

import json
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import get_settings
from src.domains.agents.constants import AGENT_TASK, CONTEXT_DOMAIN_TASKS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.tasks.parameter_descriptions import (
    TASK_LIST_NAMED_DESCRIPTION,
    TASK_LIST_OF_TASK_DESCRIPTION,
)
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mailbox_draft_base import refusal
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.task_list_scope import (
    LIST_PARAMETER,
    named_task_list,
    new_task_list,
    own_task_list_id,
)
from src.domains.agents.tools.validation_helpers import require_field
from src.domains.connectors.clients.google_tasks_client import GoogleTasksClient
from src.domains.connectors.clients.task_details import TaskLeftBehindError
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


def _answer(result: dict[str, Any]) -> UnifiedToolOutput:
    """A failure read as one, a success said in the payload's own words."""
    if "error_code" in result:
        return UnifiedToolOutput.failure(
            message=str(result["message"]), error_code=str(result["error_code"])
        )
    return UnifiedToolOutput.action_success(
        message=str(result.get("message") or ""), structured_data=result
    )


class RenameTaskListTool(ConnectorTool[GoogleTasksClient]):
    """Rename a task list."""

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="rename_task_list_tool", operation="rename_list")

    async def execute_api_call(
        self, client: GoogleTasksClient, user_id: UUID, **kwargs: Any
    ) -> dict[str, Any]:
        """Rename the list."""
        # The list named, by its id or its name: one no list answers to is refused.
        named = await named_task_list(client, require_field(kwargs, LIST_PARAMETER))
        task_list_id = str(named["id"])
        title: str = require_field(kwargs, "title")
        renamed = await client.rename_task_list(task_list_id, title)
        logger.info("task_list_renamed", user_id=str(user_id))
        return {
            "success": True,
            "task_list_id": task_list_id,
            "title": renamed.get("title") or title,
            "message": "Task list renamed",
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """A renamed list, said in the payload's own words."""
        return _answer(result)


class MoveTaskTool(ConnectorTool[GoogleTasksClient]):
    """Move a task to another list."""

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="move_task_tool", operation="move")

    async def execute_api_call(
        self, client: GoogleTasksClient, user_id: UUID, **kwargs: Any
    ) -> dict[str, Any]:
        """Move the task; its id may change, and the answer gives the one it has now."""
        task_id: str = require_field(kwargs, "task_id")
        # From the task's own list to the one named, each by its id or its name.
        task_list_id = await own_task_list_id(
            client, user_id, task_id, kwargs, runtime=self.runtime, tool_name=self.tool_name
        )
        named = await named_task_list(client, require_field(kwargs, "destination_list_id"))
        destination = str(named["id"])
        if destination == task_list_id:
            return refusal(ToolErrorCode.INVALID_INPUT, "The task is already in that list.")
        try:
            moved = await client.move_task(task_list_id, task_id, destination)
        except TaskLeftBehindError:
            return refusal(
                ToolErrorCode.CONFLICT,
                "The task reached the new list but the original could not be removed: it stands "
                "in both. Tell the person.",
            )
        logger.info("task_moved", user_id=str(user_id))
        return {
            "success": True,
            "task_id": str(moved.get("id") or task_id),
            "task_list_id": destination,
            "title": moved.get("title"),
            "message": "Task moved",
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """A moved task, or why it stands where it does."""
        return _answer(result)


class ListTaskListsTool(ToolOutputMixin, ConnectorTool[GoogleTasksClient]):
    """List all task lists for the user."""

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="list_task_lists_tool", operation="list_lists")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute list task lists API call."""
        max_results: int = kwargs.get("max_results", get_settings().tasks_tool_default_max_results)

        result = await client.list_task_lists(max_results=max_results)

        task_lists = result.get("items", [])

        logger.info(
            "list_task_lists_success",
            user_id=str(user_id),
            total_results=len(task_lists),
        )

        # Which one a new task goes in when nobody names a list (the settings' default).
        default = await new_task_list(client, user_id, None)

        return {"task_lists": task_lists, "default_list_id": default["id"]}

    def format_response(self, result: dict[str, Any]) -> str:
        """Format using JSON (legacy mode)."""
        task_lists = result.get("task_lists", [])
        formatted = []
        for tl in task_lists:
            formatted.append(
                {
                    "id": tl.get("id"),
                    "title": tl.get("title"),
                    "updated": tl.get("updated"),
                }
            )

        return json.dumps(
            {
                "success": True,
                "data": {
                    "task_lists": formatted,
                    "total": len(formatted),
                },
            },
            ensure_ascii=False,
        )

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput.

        The lists reach the answer through ``structured_data`` (ADR-347): each one's id
        and name, and which is the default one. That last fact is said only when it is
        known: a default list that is not among those listed marks none of them, rather
        than telling the model that no list is the default. The registry items stay what
        a later step references (``tasks[i].id``).
        """
        task_lists = result.get("task_lists", [])
        default_id = result.get("default_list_id")
        default_known = any(tl.get("id") == default_id for tl in task_lists)
        registry_updates: dict[str, RegistryItem] = {}
        item_ids: list[str] = []
        item_names: list[str] = []

        for tl in task_lists:
            list_id = tl.get("id", "")
            if not list_id:
                continue

            # Use TASK type with task_list prefix for lists
            item_id = f"tasklist_{list_id[:8]}"
            registry_updates[item_id] = RegistryItem(
                id=item_id,
                type=RegistryItemType.TASK,  # Task lists are related to tasks
                payload=tl,
                meta=RegistryItemMeta(source="google_tasks", domain=CONTEXT_DOMAIN_TASKS),
            )
            item_ids.append(item_id)
            item_names.append(tl.get("title") or item_id)

        # Minimal summary for debug/logs only
        summary = f"[list] {len(task_lists)} task list(s): {self._build_item_preview(item_names)}"

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            structured_data={
                "task_lists": [
                    {
                        "id": tl.get("id"),
                        "title": tl.get("title"),
                        **({"is_default": tl.get("id") == default_id} if default_known else {}),
                    }
                    for tl in task_lists
                    if tl.get("id")
                ],
                "count": len(task_lists),
            },
            metadata={
                "tool_name": "list_task_lists_tool",
                "total_results": len(task_lists),
            },
        )


_list_task_lists_tool_instance = ListTaskListsTool()


@connector_tool(
    name="list_task_lists",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="read",
)
async def list_task_lists_tool(
    max_results: Annotated[int, "Maximum number of results (default 20)"] = 20,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    List all task lists for the user.

    Args:
        max_results: Maximum task lists to return (default 20)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with list of task lists with id and title
    """
    return await _list_task_lists_tool_instance.execute(
        runtime=runtime,
        max_results=max_results,
    )


_rename_task_list_tool_instance = RenameTaskListTool()
_move_task_tool_instance = MoveTaskTool()


@connector_tool(
    name="rename_task_list",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="write",
)
async def rename_task_list_tool(
    task_list_id: Annotated[str, TASK_LIST_NAMED_DESCRIPTION],
    title: Annotated[str, "Its new name"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Rename a task list.

    Args:
        task_list_id: The list
        title: Its new name
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with confirmation message
    """
    return await _rename_task_list_tool_instance.execute(
        runtime=runtime, task_list_id=task_list_id, title=title
    )


@connector_tool(
    name="move_task",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="write",
)
async def move_task_tool(
    task_id: Annotated[str, "The task"],
    destination_list_id: Annotated[str, TASK_LIST_NAMED_DESCRIPTION],
    task_list_id: Annotated[str | None, TASK_LIST_OF_TASK_DESCRIPTION] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Move a task to another list.

    Args:
        task_id: The task
        destination_list_id: The list it goes to
        task_list_id: Its own list; omit when unknown
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with its id from now on
    """
    return await _move_task_tool_instance.execute(
        runtime=runtime,
        task_id=task_id,
        task_list_id=task_list_id,
        destination_list_id=destination_list_id,
    )


__all__ = [
    "ListTaskListsTool",
    "MoveTaskTool",
    "RenameTaskListTool",
    "list_task_lists_tool",
    "move_task_tool",
    "rename_task_list_tool",
]
