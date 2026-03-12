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

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.connectors.clients.base_google_client import (
    BaseGoogleClient,
    apply_max_items_limit,
)
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
        self, max_results: int = settings.tasks_tool_default_max_results
    ) -> dict[str, Any]:
        """
        List all task lists for the user.

        Args:
            max_results: Maximum number of results (default: from settings)

        Returns:
            Dict with 'items' list containing task list metadata

        Example:
            >>> lists = await client.list_task_lists()
            >>> for lst in lists.get("items", []):
            ...     print(f"{lst['title']} ({lst['id']})")
        """
        max_results = apply_max_items_limit(max_results)

        response = await self._make_request(
            "GET",
            "/users/@me/lists",
            {"maxResults": max_results},
        )

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
        response = await self._make_request("GET", f"/users/@me/lists/{task_list_id}")

        logger.info(
            "tasks_get_task_list",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            title=response.get("title"),
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
            title=title,
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
        await self._make_request("DELETE", f"/users/@me/lists/{task_list_id}")

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
    ) -> dict[str, Any]:
        """
        List tasks in a task list.

        Args:
            task_list_id: Task list ID (default: "@default" for primary list)
            max_results: Maximum number of results (default: from settings)
            show_completed: Include completed tasks (default: False)
            show_hidden: Include hidden tasks (default: False)
            due_min: Filter tasks due after this RFC 3339 timestamp
            due_max: Filter tasks due before this RFC 3339 timestamp

        Returns:
            Dict with 'items' list containing task data

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

        response = await self._make_request(
            "GET",
            f"/lists/{task_list_id}/tasks",
            params,
        )

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
            f"/lists/{task_list_id}/tasks/{task_id}",
        )

        logger.info(
            "tasks_get_task",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            task_id=task_id,
            title=response.get("title"),
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
            f"/lists/{task_list_id}/tasks",
            params=params if params else None,
            json_data=task_data,
        )

        logger.info(
            "tasks_create_task",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            task_id=response.get("id"),
            title=title,
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
    ) -> dict[str, Any]:
        """
        Update an existing task.

        Args:
            task_list_id: Task list ID
            task_id: Task ID to update
            title: New title (optional)
            notes: New notes (optional)
            due: New due date in RFC 3339 format (optional)
            status: New status - "needsAction" or "completed" (optional)

        Returns:
            Updated task data
        """
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
        elif "due" in existing:
            task_data["due"] = existing["due"]

        if status is not None:
            task_data["status"] = status
            if status == "completed":
                task_data["completed"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        elif "status" in existing:
            task_data["status"] = existing["status"]

        response = await self._make_request(
            "PUT",
            f"/lists/{task_list_id}/tasks/{task_id}",
            json_data=task_data,
        )

        logger.info(
            "tasks_update_task",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            task_id=task_id,
            title=response.get("title"),
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
        await self._make_request("DELETE", f"/lists/{task_list_id}/tasks/{task_id}")

        logger.info(
            "tasks_delete_task",
            user_id=str(self.user_id),
            task_list_id=task_list_id,
            task_id=task_id,
        )

        return True

    # Note: Uses base class _make_request - no override needed
