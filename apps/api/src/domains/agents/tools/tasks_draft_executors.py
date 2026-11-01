"""What a confirmed task draft does (LOT 5.4) — moved verbatim out of tasks_tools.py.

The three executors a confirmed create, update or delete draft runs, and the two
helpers only they read. Their own module since ADR-369 L6: ``tasks_tools.py`` is
frozen at its audited size, and the ``clear_due`` gesture it gained had to be
paid for by a cohesive move rather than a raised cap. Google Tasks and
Microsoft To Do alike, through dynamic provider resolution.
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.i18n_api_messages import APIMessages
from src.domains.agents.tools.exceptions import ConnectorNotEnabledError

logger = structlog.get_logger(__name__)


# ============================================================================
# URL HELPERS
# ============================================================================


def _build_task_url(task_id: str | None) -> str | None:
    """
    Build Google Tasks URL from task_id.

    Google Tasks URL format: https://tasks.google.com/task/{task_id}

    Args:
        task_id: Task ID from Google Tasks API

    Returns:
        Google Tasks URL or None if task_id is invalid

    Example:
        >>> _build_task_url("abc123xyz")
        "https://tasks.google.com/task/abc123xyz"
    """
    if not task_id:
        return None

    return f"https://tasks.google.com/task/{task_id}"


# ============================================================================
# DRAFT EXECUTION HELPERS (LOT 5.4)
# ============================================================================


async def _resolve_tasks_client(
    user_id: UUID,
    deps: Any,
) -> Any:
    """
    Resolve the active tasks client (Google Tasks or Microsoft To Do).

    Uses provider_resolver to find the active "tasks" connector and
    instantiate the appropriate client.

    Args:
        user_id: User UUID.
        deps: Runtime dependencies.

    Returns:
        Instantiated tasks client (GoogleTasksClient or MicrosoftTasksClient).

    Raises:
        ConnectorNotEnabledError: If no tasks connector is active.
    """
    from src.domains.connectors.clients.registry import ClientRegistry
    from src.domains.connectors.provider_resolver import (
        build_connector_not_enabled_error,
        resolve_active_connector,
    )

    connector_service = await deps.get_connector_service()
    resolved_type = await resolve_active_connector(user_id, "tasks", connector_service)

    if resolved_type is None:
        # Enriched with the category's ERROR-status connector (if any) so the
        # central handler can surface the "Reconnect" banner (ADR-134 V2).
        raise await build_connector_not_enabled_error(
            APIMessages.connector_not_enabled("Tasks"),
            connector_name="Tasks",
            functional_category="tasks",
            user_id=user_id,
            connector_service=connector_service,
        )

    credentials = await connector_service.get_connector_credentials(user_id, resolved_type)
    if not credentials:
        raise ConnectorNotEnabledError(
            APIMessages.connector_not_enabled("Tasks"),
            connector_name="Tasks",
        )

    client_class = ClientRegistry.get_client_class(resolved_type)
    if client_class is None:
        raise ConnectorNotEnabledError(
            APIMessages.connector_not_enabled("Tasks"),
            connector_name="Tasks",
        )

    return client_class(user_id, credentials, connector_service)


async def execute_task_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a task draft: actually create the task.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    Supports both Google Tasks and Microsoft To Do via dynamic provider resolution.
    """
    from src.core.time_utils import normalize_to_rfc3339

    client = await _resolve_tasks_client(user_id, deps)

    # Normalize due date to RFC 3339 format required by Google Tasks API
    # Planner may output "2026-01-27" but API requires "2026-01-27T00:00:00Z"
    due_rfc3339 = normalize_to_rfc3339(draft_content.get("due"))

    result = await client.create_task(
        task_list_id=draft_content.get("task_list_id", "@default"),
        title=draft_content["title"],
        notes=draft_content.get("notes"),
        due=due_rfc3339,
    )

    task_id = result.get("id")
    html_link = _build_task_url(task_id)

    logger.info(
        "task_draft_executed",
        user_id=str(user_id),
        task_id=task_id,
        html_link=html_link,
    )

    return {
        "success": True,
        "task_id": task_id,
        "html_link": html_link,
        "title": draft_content["title"],
        "task_list_id": draft_content.get("task_list_id", "@default"),
        "message": APIMessages.task_created_successfully(draft_content["title"]),
    }


async def execute_task_update_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a task update draft: actually update the task.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    Supports both Google Tasks and Microsoft To Do via dynamic provider resolution.
    """
    from src.core.time_utils import normalize_to_rfc3339

    client = await _resolve_tasks_client(user_id, deps)

    # Normalize due date to RFC 3339 format required by Google Tasks API
    due_rfc3339 = normalize_to_rfc3339(draft_content.get("due"))

    result = await client.update_task(
        task_list_id=draft_content.get("task_list_id", "@default"),
        task_id=draft_content["task_id"],
        title=draft_content.get("title"),
        notes=draft_content.get("notes"),
        due=due_rfc3339,
        status=draft_content.get("status"),
        clear_due=bool(draft_content.get("clear_due", False)),
    )

    title = result.get("title", draft_content.get("title", ""))
    task_id = draft_content["task_id"]
    html_link = _build_task_url(task_id)

    logger.info(
        "task_update_draft_executed",
        user_id=str(user_id),
        task_id=task_id,
        html_link=html_link,
    )

    return {
        "success": True,
        "task_id": task_id,
        "html_link": html_link,
        "title": title,
        "task_list_id": draft_content.get("task_list_id", "@default"),
        "message": APIMessages.task_updated_successfully(title),
    }


async def execute_task_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a task delete draft: actually delete the task.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    Supports both Google Tasks and Microsoft To Do via dynamic provider resolution.
    """
    client = await _resolve_tasks_client(user_id, deps)

    await client.delete_task(
        task_list_id=draft_content.get("task_list_id", "@default"),
        task_id=draft_content["task_id"],
    )

    title = draft_content.get("title", "")

    logger.info(
        "task_delete_draft_executed",
        user_id=str(user_id),
        task_id=draft_content["task_id"],
    )

    return {
        "success": True,
        "task_id": draft_content["task_id"],
        "title": title,
        "message": APIMessages.task_deleted_successfully(title),
    }
