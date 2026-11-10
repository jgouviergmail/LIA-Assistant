"""
Microsoft To Do (Graph API) client for task management.

Provides full CRUD access to Microsoft To Do task lists and tasks
via Microsoft Graph API v1.0. Implements the same interface as
GoogleTasksClient for transparent provider switching.

API Reference:
- https://learn.microsoft.com/en-us/graph/api/resources/todo-overview

Scopes required:
- Tasks.Read, Tasks.ReadWrite
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.exceptions import ConnectorAPIError, ResourceNotFoundError
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.base_microsoft_client import BaseMicrosoftClient
from src.domains.connectors.clients.normalizers.graph_paging import (
    graph_page_params,
    graph_page_token,
)
from src.domains.connectors.clients.normalizers.microsoft_tasks_normalizer import (
    build_task_body,
    graph_task_status,
    normalize_graph_task,
    normalize_graph_task_list,
    normalize_step,
    task_copy_body,
)
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.clients.task_details import (
    TaskDetails,
    TaskLeftBehindError,
    details_body,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)

#: A task's steps come with it: one read, none per task.
_WITH_STEPS: Final = {"$expand": "checklistItems"}


class MicrosoftTasksClient(BaseMicrosoftClient):
    """
    Microsoft To Do client via Graph API.

    Implements TasksClientProtocol (structural typing) for transparent
    provider switching with GoogleTasksClient.

    GOTCHA: Microsoft To Do has no "@default" task list concept.
    When task_list_id="@default", this client fetches the first
    task list and uses its ID.

    GOTCHA: Microsoft To Do has no subtask hierarchy (parent parameter).
    The parent parameter is accepted for interface compatibility but ignored;
    a task holds steps of its own instead (``add_task_step``).

    Example:
        >>> client = MicrosoftTasksClient(user_id, credentials, connector_service)
        >>> lists = await client.list_task_lists()
        >>> tasks = await client.list_tasks(lists["items"][0]["id"])
    """

    connector_type = ConnectorType.MICROSOFT_TASKS

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,
        cache_service: Any | None = None,
        rate_limit_per_second: int | None = None,
    ) -> None:
        """
        Initialize Microsoft To Do client.

        Args:
            user_id: User UUID.
            credentials: OAuth credentials.
            connector_service: ConnectorService instance for token refresh.
            cache_service: Optional cache service (unused, kept for interface parity).
            rate_limit_per_second: Max requests per second.
        """
        super().__init__(user_id, credentials, connector_service, rate_limit_per_second)
        self._default_list_id: str | None = None

    # =========================================================================
    # TASK LIST OPERATIONS
    # =========================================================================

    async def list_task_lists(
        self,
        max_results: int = settings.tasks_tool_default_max_results,
        *,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        List the user's task lists, one page at a time.

        Args:
            max_results: Maximum number of results.
            page_token: The ``next_page_token`` of the previous page (ADR-369).

        Returns:
            Dict with 'items' list containing task list metadata, and
            ``next_page_token`` (None on the last page).

        Raises:
            ValueError: ``page_token`` is not one this listing produced.
        """
        max_results = apply_max_items_limit(max_results)
        params: dict[str, Any] = {"$top": max_results, **graph_page_params(page_token)}

        response = await self._make_request("GET", "/me/todo/lists", params)

        items = [normalize_graph_task_list(tl) for tl in response.get("value", [])]

        # Cache default list ID for @default resolution
        if items and not self._default_list_id:
            self._default_list_id = items[0]["id"]

        logger.info(
            "microsoft_tasks_list_task_lists",
            user_id=str(self.user_id),
            results_count=len(items),
        )

        return {
            "items": items,
            "next_page_token": graph_page_token(response.get("@odata.nextLink")),
        }

    async def get_task_list(self, task_list_id: str) -> dict[str, Any]:
        """
        Get a specific task list by ID.

        Args:
            task_list_id: Task list ID (or "@default").

        Returns:
            Task list metadata.
        """
        resolved_id = await self._resolve_list_id(task_list_id)

        response = await self._make_request("GET", _list_path(resolved_id))

        logger.info(
            "microsoft_tasks_get_task_list",
            user_id=str(self.user_id),
            task_list_id=resolved_id,
        )

        return normalize_graph_task_list(response)

    async def create_task_list(self, title: str) -> dict[str, Any]:
        """
        Create a new task list.

        Args:
            title: Title for the new task list.

        Returns:
            Created task list metadata.
        """
        response = await self._make_request(
            "POST", "/me/todo/lists", json_data={"displayName": title}
        )

        logger.info(
            "microsoft_tasks_create_task_list",
            user_id=str(self.user_id),
            task_list_id=response.get("id"),
        )

        return normalize_graph_task_list(response)

    async def rename_task_list(self, task_list_id: str, title: str) -> dict[str, Any]:
        """
        Rename a task list.

        Args:
            task_list_id: Task list ID.
            title: Its new title.

        Returns:
            The list as it is now, in Google Tasks format.
        """
        resolved_id = await self._resolve_list_id(task_list_id)

        response = await self._make_request(
            "PATCH", _list_path(resolved_id), json_data={"displayName": title}
        )

        logger.info(
            "microsoft_tasks_rename_task_list",
            user_id=str(self.user_id),
            task_list_id=resolved_id,
        )

        return normalize_graph_task_list(response)

    async def delete_task_list(self, task_list_id: str) -> bool:
        """
        Delete a task list and all its tasks.

        Args:
            task_list_id: Task list ID to delete.

        Returns:
            True if successful.
        """
        resolved_id = await self._resolve_list_id(task_list_id)

        await self._make_request("DELETE", _list_path(resolved_id))

        logger.info(
            "microsoft_tasks_delete_task_list",
            user_id=str(self.user_id),
            task_list_id=resolved_id,
        )

        return True

    # =========================================================================
    # TASK OPERATIONS
    # =========================================================================

    async def list_tasks(
        self,
        task_list_id: str = "@default",
        max_results: int = settings.tasks_tool_default_max_results,
        show_completed: bool = False,
        show_hidden: bool = False,
        due_min: str | None = None,
        due_max: str | None = None,
        completed_min: str | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        List tasks in a task list, one page at a time.

        Args:
            task_list_id: Task list ID (or "@default").
            max_results: Maximum results.
            show_completed: Include completed tasks.
            show_hidden: Include hidden tasks (no-op for Microsoft).
            due_min: Filter tasks due after this RFC 3339 timestamp.
            due_max: Filter tasks due before this RFC 3339 timestamp.
            completed_min: Filter tasks completed after this RFC 3339 timestamp
                (the due filters' own shape; the radio's journal reads a day's).
            page_token: The ``next_page_token`` of the previous page (ADR-369).

        Returns:
            Dict with 'items' list containing task data, and ``next_page_token``
            (None on the last page).

        Raises:
            ValueError: ``page_token`` is not one this listing produced.
        """
        max_results = apply_max_items_limit(max_results)
        resolved_id = await self._resolve_list_id(task_list_id)

        params: dict[str, Any] = {"$top": max_results, **_WITH_STEPS}

        # Build $filter for completed status and due dates
        filters: list[str] = []
        if not show_completed:
            filters.append("status ne 'completed'")
        if due_min:
            filters.append(f"dueDateTime/dateTime ge '{due_min}'")
        if due_max:
            filters.append(f"dueDateTime/dateTime le '{due_max}'")
        if completed_min:
            filters.append(f"completedDateTime/dateTime ge '{completed_min}'")

        if filters:
            params["$filter"] = " and ".join(filters)
        params.update(graph_page_params(page_token))

        response = await self._make_request("GET", f"{_list_path(resolved_id)}/tasks", params)

        items = [normalize_graph_task(t) for t in response.get("value", [])]

        logger.info(
            "microsoft_tasks_list_tasks",
            user_id=str(self.user_id),
            task_list_id=resolved_id,
            results_count=len(items),
        )

        return {
            "items": items,
            "next_page_token": graph_page_token(response.get("@odata.nextLink")),
        }

    async def get_task(self, task_list_id: str, task_id: str) -> dict[str, Any]:
        """
        Get a specific task by ID.

        Args:
            task_list_id: Task list ID.
            task_id: Task ID.

        Returns:
            Task data in Google Tasks format.
        """
        resolved_id = await self._resolve_list_id(task_list_id)

        response = await self._make_request("GET", _task_path(resolved_id, task_id), _WITH_STEPS)

        logger.info(
            "microsoft_tasks_get_task",
            user_id=str(self.user_id),
            task_list_id=resolved_id,
            task_id=task_id,
        )

        return normalize_graph_task(response)

    async def create_task(
        self,
        task_list_id: str = "@default",
        title: str = "",
        notes: str | None = None,
        due: str | None = None,
        parent: str | None = None,
        *,
        details: TaskDetails | None = None,
        steps: Sequence[str] = (),
        due_zone: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new task.

        Args:
            task_list_id: Task list ID (or "@default").
            title: Task title.
            notes: Task notes/description.
            due: Due date in RFC 3339 format, or a wall time in ``due_zone``.
            parent: Parent task ID (IGNORED — Microsoft To Do has no subtask hierarchy).
            details: Its importance, reminder and repetition.
            steps: The steps it starts with.
            due_zone: The zone ``due`` is a wall time in; UTC when none is named.

        Returns:
            Created task data.
        """
        if parent:
            logger.warning(
                "microsoft_tasks_parent_ignored",
                user_id=str(self.user_id),
                parent=parent,
                reason="Microsoft To Do does not support subtask hierarchy",
            )

        resolved_id = await self._resolve_list_id(task_list_id)
        body = build_task_body(title=title, notes=notes, due=due, due_zone=due_zone) | (
            details_body(details)
        )
        if steps:
            body["checklistItems"] = [{"displayName": step} for step in steps]

        response = await self._make_request(
            "POST", f"{_list_path(resolved_id)}/tasks", json_data=body
        )

        logger.info(
            "microsoft_tasks_create_task",
            user_id=str(self.user_id),
            task_list_id=resolved_id,
            task_id=response.get("id"),
        )

        return normalize_graph_task(response)

    async def update_task(
        self,
        task_list_id: str,
        task_id: str,
        title: str | None = None,
        notes: str | None = None,
        due: str | None = None,
        status: str | None = None,
        *,
        clear_due: bool = False,
        details: TaskDetails | None = None,
        due_zone: str | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing task.

        Uses PATCH semantics — only provided fields are updated.

        Args:
            task_list_id: Task list ID.
            task_id: Task ID to update.
            title: New title.
            notes: New notes.
            due: New due date in RFC 3339 format, or a wall time in ``due_zone``.
            status: New status ("needsAction" or "completed").
            clear_due: Remove the due date (ADR-369).
            details: What changes of its importance, reminder and repetition.
            due_zone: The zone ``due`` is a wall time in; UTC when none is named.

        Returns:
            Updated task data.

        Raises:
            ValueError: A due date and its removal together.
        """
        if clear_due and due is not None:
            raise ValueError("a due date and its removal cannot be asked together")
        resolved_id = await self._resolve_list_id(task_list_id)

        body = details_body(details)
        if title is not None:
            body["title"] = title
        if notes is not None:
            body["body"] = {"content": notes, "contentType": "text"}
        if due is not None:
            body["dueDateTime"] = {"dateTime": due, "timeZone": due_zone or "UTC"}
        elif clear_due:
            body["dueDateTime"] = None
        if status is not None:
            ms_status = graph_task_status(status)
            body["status"] = ms_status
            if ms_status == "completed":
                body["completedDateTime"] = {
                    "dateTime": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                }

        response = await self._make_request(
            "PATCH", _task_path(resolved_id, task_id), json_data=body
        )

        logger.info(
            "microsoft_tasks_update_task",
            user_id=str(self.user_id),
            task_list_id=resolved_id,
            task_id=task_id,
        )

        return normalize_graph_task(response)

    async def move_task(
        self, task_list_id: str, task_id: str, destination_list_id: str
    ) -> dict[str, Any]:
        """
        Move a task to another list: a copy, then the original removed (``task_details``).

        Args:
            task_list_id: Its list.
            task_id: The task.
            destination_list_id: The list it goes to.

        Returns:
            The task where it is now, under the id To Do gave the copy.

        Raises:
            TaskLeftBehindError: It stands in both lists.
        """
        source = await self._resolve_list_id(task_list_id)
        destination = await self._resolve_list_id(destination_list_id)
        read = await self._make_request("GET", _task_path(source, task_id), _WITH_STEPS)
        copy = await self._make_request(
            "POST", f"{_list_path(destination)}/tasks", json_data=task_copy_body(read)
        )
        try:
            await self._make_request("DELETE", _task_path(source, task_id))
        except ConnectorAPIError as error:
            raise TaskLeftBehindError from error

        logger.info(
            "microsoft_tasks_move_task",
            user_id=str(self.user_id),
            task_list_id=source,
            task_id=task_id,
        )

        return normalize_graph_task(copy)

    async def add_task_step(self, task_list_id: str, task_id: str, title: str) -> dict[str, Any]:
        """
        Add a step to a task.

        Args:
            task_list_id: Its list.
            task_id: The task.
            title: What the step says.

        Returns:
            The step: ``id``, ``title``, ``checked``.
        """
        resolved_id = await self._resolve_list_id(task_list_id)
        response = await self._make_request(
            "POST",
            f"{_task_path(resolved_id, task_id)}/checklistItems",
            json_data={"displayName": title},
        )
        return normalize_step(response)

    async def change_task_step(
        self,
        task_list_id: str,
        task_id: str,
        step_id: str,
        *,
        title: str | None = None,
        checked: bool | None = None,
    ) -> dict[str, Any]:
        """
        Change a step: what is left out is kept.

        Args:
            task_list_id: Its list.
            task_id: The task.
            step_id: The step.
            title: What it says now.
            checked: Whether it is done.

        Returns:
            The step: ``id``, ``title``, ``checked``.
        """
        resolved_id = await self._resolve_list_id(task_list_id)
        body: dict[str, Any] = {}
        if title is not None:
            body["displayName"] = title
        if checked is not None:
            body["isChecked"] = checked
        response = await self._make_request(
            "PATCH", _step_path(resolved_id, task_id, step_id), json_data=body
        )
        return normalize_step(response)

    async def remove_task_step(self, task_list_id: str, task_id: str, step_id: str) -> None:
        """
        Remove a step.

        Args:
            task_list_id: Its list.
            task_id: The task.
            step_id: The step.
        """
        resolved_id = await self._resolve_list_id(task_list_id)
        await self._make_request("DELETE", _step_path(resolved_id, task_id, step_id))

    async def complete_task(self, task_list_id: str, task_id: str) -> dict[str, Any]:
        """
        Mark a task as completed.

        Args:
            task_list_id: Task list ID.
            task_id: Task ID to complete.

        Returns:
            Updated task data.
        """
        return await self.update_task(task_list_id, task_id, status="completed")

    async def delete_task(self, task_list_id: str, task_id: str) -> bool:
        """
        Delete a task.

        Args:
            task_list_id: Task list ID.
            task_id: Task ID to delete.

        Returns:
            True if successful.
        """
        resolved_id = await self._resolve_list_id(task_list_id)

        await self._make_request("DELETE", _task_path(resolved_id, task_id))

        logger.info(
            "microsoft_tasks_delete_task",
            user_id=str(self.user_id),
            task_list_id=resolved_id,
            task_id=task_id,
        )

        return True

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    async def _resolve_list_id(self, task_list_id: str) -> str:
        """
        Resolve "@default" to the actual default task list ID.

        Microsoft To Do has no "@default" concept. We use the first
        task list returned by list_task_lists() as the default.

        Args:
            task_list_id: Task list ID or "@default".

        Returns:
            Actual task list ID.
        """
        if task_list_id != "@default":
            return task_list_id

        if self._default_list_id:
            return self._default_list_id

        # Fetch task lists to find the default
        response = await self._make_request("GET", "/me/todo/lists", {"$top": 1})

        lists = response.get("value", [])
        if not lists:
            raise ResourceNotFoundError(
                resource_type="task_list",
                detail="No task lists found in Microsoft To Do.",
            )

        self._default_list_id = lists[0]["id"]
        return self._default_list_id


def _list_path(task_list_id: str) -> str:
    """A list's path, its id one quoted segment (a browser's or a model's id)."""
    segment = path_segment(task_list_id, connector_type=ConnectorType.MICROSOFT_TASKS)
    return f"/me/todo/lists/{segment}"


def _step_path(task_list_id: str, task_id: str, step_id: str) -> str:
    segment = path_segment(step_id, connector_type=ConnectorType.MICROSOFT_TASKS)
    return f"{_task_path(task_list_id, task_id)}/checklistItems/{segment}"


def _task_path(task_list_id: str, task_id: str) -> str:
    segment = path_segment(task_id, connector_type=ConnectorType.MICROSOFT_TASKS)
    return f"{_list_path(task_list_id)}/tasks/{segment}"
