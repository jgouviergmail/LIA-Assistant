"""
Google Tasks API client.

Provides full CRUD access to Google Tasks for task management.
Uses the Google Tasks API v1.

API Reference:
- https://developers.google.com/tasks/reference/rest

Scopes required:
- https://www.googleapis.com/auth/tasks (full access)
- https://www.googleapis.com/auth/tasks.readonly (read-only access)
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.time_utils import now_utc
from src.domains.connectors.clients.base_google_client import (
    BaseGoogleClient,
    apply_max_items_limit,
)
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.cache.redis import CacheService

logger = structlog.get_logger(__name__)


class GoogleTasksClient(BaseGoogleClient):
    """
    Client for Google Tasks API.

    Provides full CRUD access to:
    - Task lists (containers for tasks)
    - Tasks (individual items with due dates, notes, etc.)

    Example:
        >>> client = GoogleTasksClient(user_id, credentials, connector_service)
        >>> lists = await client.list_task_lists()
        >>> tasks = await client.list_tasks(lists["items"][0]["id"])
        >>> print(f"Found {len(tasks['items'])} tasks")
    """

    connector_type = ConnectorType.GOOGLE_TASKS
    api_base_url = "https://tasks.googleapis.com/tasks/v1"

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,
        cache_service: CacheService | None = None,
        rate_limit_per_second: int = 10,
    ) -> None:
        """
        Initialize Google Tasks client.

        Args:
            user_id: User UUID
            credentials: OAuth credentials
            connector_service: ConnectorService instance for token refresh
            cache_service: Optional cache service for caching results
            rate_limit_per_second: Max requests per second (default: 10)
        """
        super().__init__(user_id, credentials, connector_service, rate_limit_per_second)
        self._cache_service = cache_service

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
            max_results: Maximum number of results (default: from settings)
            page_token: The ``next_page_token`` of the previous page (ADR-369)

        Returns:
            Dict with 'items' list containing task list metadata, and
            ``next_page_token`` (None on the last page)

        Example:
            >>> lists = await client.list_task_lists()
            >>> for lst in lists.get("items", []):
            ...     print(f"{lst['title']} ({lst['id']})")
        """
        max_results = apply_max_items_limit(max_results)

        params: dict[str, Any] = {"maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        response = await self._make_request("GET", "/users/@me/lists", params)
        response["next_page_token"] = response.get("nextPageToken")

        logger.info(
            "tasks_list_task_lists_completed",
            user_id=str(self.user_id),
            results_count=len(response.get("items", [])),
        )

        return response

    async def get_task_list(self, task_list_id: str) -> dict[str, Any]:
        """
        Get a specific task list by ID.

        Args:
            task_list_id: Task list ID (or "@default" for default list)

        Returns:
            Task list metadata including id, title, updated timestamp
        """
        response = await self._make_request("GET", f"/users/@me/lists/{_segment(task_list_id)}")

        logger.info(
            "tasks_get_task_list",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
        )

        return response

    async def create_task_list(self, title: str) -> dict[str, Any]:
        """
        Create a new task list.

        Args:
            title: Title for the new task list

        Returns:
            Created task list metadata
        """
        response = await self._make_request(
            "POST",
            "/users/@me/lists",
            json_data={"title": title},
        )

        logger.info(
            "tasks_create_task_list",
            user_id=str(self.user_id),
            task_list_id=response.get("id"),
        )

        return response

    async def delete_task_list(self, task_list_id: str) -> bool:
        """
        Delete a task list and all its tasks.

        Args:
            task_list_id: Task list ID to delete

        Returns:
            True if successful
        """
        await self._make_request("DELETE", f"/users/@me/lists/{_segment(task_list_id)}")

        logger.info(
            "tasks_delete_task_list",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
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
            task_list_id: Task list ID (default: "@default" for primary list)
            max_results: Maximum number of results (default: from settings)
            show_completed: Include completed tasks (default: False)
            show_hidden: Include hidden tasks (default: False)
            due_min: Filter tasks due after this RFC 3339 timestamp
            due_max: Filter tasks due before this RFC 3339 timestamp
            completed_min: Filter tasks completed after this RFC 3339 timestamp
                (with ``show_completed``; the radio's journal reads a day's)
            page_token: The ``next_page_token`` of the previous page (ADR-369)

        Returns:
            Dict with 'items' list containing task data, and ``next_page_token``
            (None on the last page)

        Example:
            >>> tasks = await client.list_tasks()
            >>> for task in tasks.get("items", []):
            ...     print(f"[{task.get('status')}] {task['title']}")
        """
        max_results = apply_max_items_limit(max_results)

        params: dict[str, Any] = {
            "maxResults": max_results,
            "showCompleted": show_completed,
            "showHidden": show_hidden,
        }

        if due_min:
            params["dueMin"] = due_min
        if due_max:
            params["dueMax"] = due_max
        if completed_min:
            params["completedMin"] = completed_min
        if page_token:
            params["pageToken"] = page_token

        response = await self._make_request(
            "GET",
            f"{_list_path(task_list_id)}/tasks",
            params,
        )
        response["next_page_token"] = response.get("nextPageToken")

        logger.info(
            "tasks_list_tasks_completed",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            results_count=len(response.get("items", [])),
        )

        return response

    async def get_task(self, task_list_id: str, task_id: str) -> dict[str, Any]:
        """
        Get a specific task by ID.

        Args:
            task_list_id: Task list ID
            task_id: Task ID

        Returns:
            Task data including title, notes, due date, status, etc.
        """
        response = await self._make_request(
            "GET",
            _task_path(task_list_id, task_id),
        )

        logger.info(
            "tasks_get_task",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            task_id=task_id,
        )

        return response

    async def create_task(
        self,
        task_list_id: str = "@default",
        title: str = "",
        notes: str | None = None,
        due: str | None = None,
        parent: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new task.

        Args:
            task_list_id: Task list ID (default: "@default")
            title: Task title (required)
            notes: Task notes/description (optional)
            due: Due date in RFC 3339 format (e.g., "2025-01-15T00:00:00Z")
            parent: Parent task ID for creating subtasks (optional)

        Returns:
            Created task data

        Example:
            >>> task = await client.create_task(
            ...     title="Buy groceries",
            ...     notes="Milk, bread, eggs",
            ...     due="2025-01-15T00:00:00Z"
            ... )
            >>> print(f"Created task: {task['id']}")
        """
        task_data: dict[str, Any] = {"title": title}

        if notes:
            task_data["notes"] = notes
        if due:
            task_data["due"] = due

        params = {}
        if parent:
            params["parent"] = parent

        response = await self._make_request(
            "POST",
            f"{_list_path(task_list_id)}/tasks",
            params=params if params else None,
            json_data=task_data,
        )

        logger.info(
            "tasks_create_task",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            task_id=response.get("id"),
        )

        return response

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
    ) -> dict[str, Any]:
        """
        Update an existing task.

        The task is read first and written back WHOLE (a PUT): a field left
        out of the body is a field removed, so what is not changed is
        carried — the completion date of a completed task included.

        Args:
            task_list_id: Task list ID
            task_id: Task ID to update
            title: New title (optional)
            notes: New notes (optional)
            due: New due date in RFC 3339 format (optional)
            status: New status - "needsAction" or "completed" (optional)
            clear_due: Remove the due date (ADR-369)

        Returns:
            Updated task data

        Raises:
            ValueError: A due date and its removal together.
        """
        if clear_due and due is not None:
            raise ValueError("a due date and its removal cannot be asked together")
        # Get existing task to preserve unchanged fields
        existing = await self.get_task(task_list_id, task_id)

        # Build update body
        task_data: dict[str, Any] = {
            "id": task_id,
            "title": title if title is not None else existing.get("title", ""),
        }

        if notes is not None:
            task_data["notes"] = notes
        elif "notes" in existing:
            task_data["notes"] = existing["notes"]

        if due is not None:
            task_data["due"] = due
        elif "due" in existing and not clear_due:
            task_data["due"] = existing["due"]

        if status is not None:
            task_data["status"] = status
            if status == "completed":
                task_data["completed"] = now_utc().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        elif "status" in existing:
            task_data["status"] = existing["status"]
            if "completed" in existing:
                task_data["completed"] = existing["completed"]

        response = await self._make_request(
            "PUT",
            _task_path(task_list_id, task_id),
            json_data=task_data,
        )

        logger.info(
            "tasks_update_task",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            task_id=task_id,
            status=response.get("status"),
        )

        return response

    async def complete_task(self, task_list_id: str, task_id: str) -> dict[str, Any]:
        """
        Mark a task as completed.

        Args:
            task_list_id: Task list ID
            task_id: Task ID to complete

        Returns:
            Updated task data
        """
        return await self.update_task(task_list_id, task_id, status="completed")

    async def delete_task(self, task_list_id: str, task_id: str) -> bool:
        """
        Delete a task.

        Args:
            task_list_id: Task list ID
            task_id: Task ID to delete

        Returns:
            True if successful
        """
        await self._make_request("DELETE", _task_path(task_list_id, task_id))

        logger.info(
            "tasks_delete_task",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            task_id=task_id,
        )

        return True

    # Note: Uses base class _make_request - no override needed


def _segment(value: str) -> str:
    """One path segment of a Google Tasks URL (``@default`` keeps its name)."""
    return path_segment(value, connector_type=ConnectorType.GOOGLE_TASKS, safe="@")


def _list_path(task_list_id: str) -> str:
    return f"/lists/{_segment(task_list_id)}"


def _task_path(task_list_id: str, task_id: str) -> str:
    return f"{_list_path(task_list_id)}/tasks/{_segment(task_id)}"
