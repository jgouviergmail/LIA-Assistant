"""
LangChain v1 tools for Tasks operations (Google Tasks + Microsoft To Do).

LOT 9: Tasks integration with list, create, update, and complete operations.

Pattern:
    @tool
    async def my_tool(
        arg: str,
        runtime: ToolRuntime,  # Unified access to runtime resources
    ) -> str:
        user_id = runtime.config.get("configurable", {}).get("user_id")
        # Use runtime.config, runtime.store, runtime.state, etc.

Data Registry Mode (LOT 5):
    - Tools support dual output: legacy JSON string or Data Registry UnifiedToolOutput
    - Data Registry mode enabled via registry_enabled=True class attribute
    - Uses ToolOutputMixin for registry item creation

Architecture (2025-12-30):
    Migrated from StandardToolOutput to UnifiedToolOutput.
    UnifiedToolOutput provides:
    - Explicit success/error status
    - message field for LLM response generation
    - structured_data for optional metadata
    - Compatibility with parallel_executor via summary_for_llm property

    All functions (including draft tools) now return UnifiedToolOutput directly.
"""

import json
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel

from src.core.config import get_settings, settings
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.constants import AGENT_TASK, CONTEXT_DOMAIN_TASKS
from src.domains.agents.context import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.exceptions import ConnectorNotEnabledError, ToolValidationError
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.validation_helpers import (
    require_field,
    validate_positive_int_or_default,
)
from src.domains.connectors.clients.google_tasks_client import GoogleTasksClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.resolver import resolve_task_list_name

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


async def _resolve_default_task_list(
    client: Any,
    user_id: UUID,
    task_list_id_input: str,
) -> str:
    """
    Resolve task list ID from user preferences if using @default.

    Supports both Google Tasks and Microsoft To Do clients.

    Args:
        client: Tasks client instance (GoogleTasksClient or MicrosoftTasksClient).
        user_id: User UUID.
        task_list_id_input: Input task list ID or @default.

    Returns:
        Resolved task list ID.
    """
    from src.domains.connectors.preferences.service import ConnectorPreferencesService
    from src.domains.connectors.provider_resolver import resolve_active_connector
    from src.domains.connectors.repository import ConnectorRepository

    # If not using @default, resolve the name directly
    if task_list_id_input != "@default":
        resolved_id = await resolve_task_list_name(
            client=client,
            name=task_list_id_input,
            fallback="@default",
        )
        logger.debug(
            "task_list_id_resolved",
            input=task_list_id_input,
            resolved=resolved_id,
        )
        return resolved_id

    # Try to get user's default preference (provider-aware)
    try:
        repo = ConnectorRepository(client.connector_service.db)
        connector_service = client.connector_service
        resolved_type = await resolve_active_connector(user_id, "tasks", connector_service)

        if resolved_type:
            connector = await repo.get_by_user_and_type(user_id, resolved_type)
            if connector and connector.preferences_encrypted:
                # Use provider-specific preference key
                pref_key = resolved_type.value  # "google_tasks" or "microsoft_tasks"
                default_name = ConnectorPreferencesService.get_preference_value(
                    pref_key,
                    connector.preferences_encrypted,
                    "default_task_list_name",
                )
                if default_name:
                    logger.debug(
                        "tasks_using_default_preference",
                        default_task_list_name=default_name,
                        user_id=str(user_id),
                        provider=pref_key,
                    )
                    resolved_id = await resolve_task_list_name(
                        client=client,
                        name=default_name,
                        fallback="@default",
                    )
                    logger.debug(
                        "task_list_id_resolved",
                        input=default_name,
                        resolved=resolved_id,
                    )
                    return resolved_id
    except Exception as e:
        logger.warning("tasks_preference_resolution_failed", error=str(e))

    # Fallback to @default
    return "@default"


# ============================================================================
# CONTEXT REGISTRATION
# ============================================================================


class TaskItem(BaseModel):
    """
    Standardized task item schema for context manager.

    Used for reference resolution (e.g., "the 2nd task", "the one due tomorrow").
    """

    id: str  # Google Tasks task ID
    title: str  # Task title
    status: str = "needsAction"  # Task status: needsAction or completed
    due: str | None = None  # Due date


# Register task context types for context manager
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_TASKS,
        agent_name=AGENT_TASK,
        item_schema=TaskItem,
        primary_id_field="id",
        display_name_field="title",
        reference_fields=[
            "title",
            "status",
        ],
        icon="✅",
    )
)


# ============================================================================
# TOOL 1: LIST TASKS
# ============================================================================


class ListTasksTool(ToolOutputMixin, ConnectorTool[GoogleTasksClient]):
    """
    List tasks tool using Phase 3.2 architecture with Data Registry support.

    Data Registry Mode:
    - registry_enabled=True: Returns UnifiedToolOutput with registry items
    - Registry items contain task data for frontend rendering
    """

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize list tasks tool with Data Registry support."""
        super().__init__(tool_name="get_tasks_tool", operation="list")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute list tasks API call - business logic only."""
        task_list_id_input: str = kwargs.get("task_list_id", "@default")
        settings = get_settings()

        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        raw_max_results = kwargs.get("max_results")
        default_max_results = settings.tasks_tool_default_max_results
        max_results = validate_positive_int_or_default(raw_max_results, default=default_max_results)
        # Cap at domain-specific limit (TASKS_TOOL_DEFAULT_MAX_RESULTS)
        security_cap = settings.tasks_tool_default_max_results
        if max_results > security_cap:
            logger.warning(
                "tasks_list_limit_capped",
                requested_max_results=raw_max_results,
                capped_max_results=security_cap,
                default_max_results=default_max_results,
            )
            max_results = security_cap
        show_completed: bool = kwargs.get("show_completed", False)
        only_completed: bool = kwargs.get("only_completed", False)
        fetch_limit = security_cap if only_completed else max_results
        due_min: str | None = kwargs.get("due_min")
        due_max: str | None = kwargs.get("due_max")

        # TOKEN EXPLOSION PREVENTION STRATEGY (Tasks):
        # Unlike Emails (where date filtering is essential), Tasks uses a different strategy:
        # 1. default_max_results=10 limits response size
        # 2. security_cap=50 hard limit
        # 3. show_completed=False excludes completed tasks (major source of volume)
        # We do NOT add default date filtering because:
        # - Many tasks have NO due date (would be excluded by date filter)
        # - Pending tasks rarely number in hundreds (unlike emails)
        # - Current protections are sufficient

        # Google Tasks API behavior:
        # - showCompleted=true INCLUDES completed tasks (doesn't filter)
        # - showHidden=true is REQUIRED to see completed tasks that became hidden
        # When requesting completed tasks, we need both flags
        show_hidden = show_completed or only_completed

        result = await client.list_tasks(
            task_list_id=task_list_id,
            max_results=fetch_limit,
            show_completed=show_completed or only_completed,
            show_hidden=show_hidden,
            due_min=due_min,
            due_max=due_max,
        )

        tasks = result.get("items", [])

        # If only_completed requested, filter to ONLY completed tasks
        if only_completed:
            tasks = [t for t in tasks if t.get("status") == "completed"]
            tasks = tasks[:max_results]  # Apply limit after filtering

        logger.info(
            "list_tasks_success",
            user_id=str(user_id),
            task_list_id=task_list_id,
            show_completed=show_completed,
            only_completed=only_completed,
            show_hidden=show_hidden,
            due_min=due_min,
            due_max=due_max,
            total_results=len(tasks),
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "tasks": tasks,
            "task_list_id": task_list_id,
            "show_completed": show_completed,
            "only_completed": only_completed,
            "user_timezone": user_timezone,
            "locale": locale,
        }

    def format_response(self, result: dict[str, Any]) -> str:
        """Format using JSON (legacy mode)."""
        tasks = result.get("tasks", [])
        formatted_tasks = []
        for t in tasks:
            formatted_tasks.append(
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "status": t.get("status"),
                    "due": t.get("due"),
                    "notes": t.get("notes"),
                }
            )

        return json.dumps(
            {
                "success": True,
                "data": {
                    "tasks": formatted_tasks,
                    "total": len(formatted_tasks),
                },
            },
            ensure_ascii=False,
        )

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with registry items.

        INTELLIA v10: Simplified - only builds registry_updates.
        Formatting is handled by response_node._simplify_task_payload() + fewshots.

        TIMEZONE: Dates are converted to user's timezone before storage.
        """
        tasks = result.get("tasks", [])
        task_list_id = result.get("task_list_id")
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)

        # Use ToolOutputMixin helper with timezone conversion
        # build_tasks_output returns UnifiedToolOutput directly
        return self.build_tasks_output(
            tasks=tasks,
            task_list_id=task_list_id,
            from_cache=False,
            user_timezone=user_timezone,
            locale=locale,
        )


_list_tasks_tool_instance = ListTasksTool()


@connector_tool(
    name="list_tasks",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="read",
)
async def list_tasks_tool(
    task_list_id: Annotated[
        str, "Task list ID (default: '@default' for primary list)"
    ] = "@default",
    max_results: Annotated[
        int | None, "Maximum number of results (defaults to settings, max 100)"
    ] = None,
    show_completed: Annotated[
        bool, "Include completed tasks along with pending tasks (default False)"
    ] = False,
    only_completed: Annotated[
        bool,
        "Return ONLY completed/finished tasks, excluding pending tasks (default False). Use this when user asks for 'tâches terminées', 'completed tasks', 'finished tasks'.",
    ] = False,
    due_min: Annotated[
        str | None, "Filter tasks due after this RFC 3339 timestamp (e.g., '2025-01-15T00:00:00Z')"
    ] = None,
    due_max: Annotated[
        str | None, "Filter tasks due before this RFC 3339 timestamp (e.g., '2025-01-15T23:59:59Z')"
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    List tasks from a Google Tasks list.

    Args:
        task_list_id: Task list ID, use '@default' for primary list
        max_results: Maximum tasks to return (default from settings)
        show_completed: Include completed tasks along with pending tasks (default False)
        only_completed: Return ONLY completed tasks, excluding pending ones (default False).
            Use this when user explicitly asks for completed/finished/done tasks only.
        due_min: Filter tasks due after this timestamp (RFC 3339)
        due_max: Filter tasks due before this timestamp (RFC 3339)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with list of tasks with title, status, due date, and notes
    """
    return await _list_tasks_tool_instance.execute(
        runtime=runtime,
        task_list_id=task_list_id,
        max_results=max_results,
        show_completed=show_completed,
        only_completed=only_completed,
        due_min=due_min,
        due_max=due_max,
    )


# ============================================================================
# TOOL 2: GET TASK DETAILS (Read Operation)
# ============================================================================


class GetTaskDetailsTool(ToolOutputMixin, ConnectorTool[GoogleTasksClient]):
    """
    Get task details tool with Data Registry support.

    Returns extended task information including:
    - Full notes/description
    - Parent task info (for subtasks)
    - Links
    - Completion date
    - Position in list

    This provides more detail than list_tasks for a single task.

    MULTI-ORDINAL FIX (2026-01-01): Supports batch mode for multi-reference queries.
    - Single mode: task_id="abc123" → fetch one task
    - Batch mode: task_ids=["abc123", "def456"] → fetch multiple tasks in parallel
    """

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize get task details tool with Data Registry support."""
        super().__init__(tool_name="get_tasks_tool", operation="details")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute get task details API call.

        MULTI-ORDINAL FIX (2026-01-01): Routes to single or batch mode based on parameters.
        - If task_ids is provided (non-empty list) → batch mode
        - If task_id is provided → single mode
        - Both provided → batch mode takes precedence
        """
        task_id: str | None = kwargs.get("task_id")
        task_ids: list[str] | None = kwargs.get("task_ids")
        task_list_id_input: str = kwargs.get("task_list_id", "@default")

        # Determine mode: batch takes precedence
        if task_ids and len(task_ids) > 0:
            return await self._execute_batch(client, user_id, task_ids, task_list_id_input)
        elif task_id:
            return await self._execute_single(client, user_id, task_id, task_list_id_input)
        else:
            raise ValueError("Either task_id or task_ids must be provided")

    async def _execute_single(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        task_id: str,
        task_list_id_input: str,
    ) -> dict[str, Any]:
        """Execute single task details fetch."""
        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        result = await client.get_task(task_list_id, task_id)

        logger.info(
            "get_task_details_success",
            user_id=str(user_id),
            task_id=task_id,
            title=result.get("title", ""),
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "task": result,
            "task_id": task_id,
            "task_list_id": task_list_id,
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "single",
        }

    async def _execute_batch(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        task_ids: list[str],
        task_list_id_input: str,
    ) -> dict[str, Any]:
        """Execute batch task details fetch using asyncio.gather for parallelism.

        MULTI-ORDINAL FIX (2026-01-01): Added for multi-reference queries.
        """
        import asyncio

        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        # Fetch all tasks in parallel
        async def fetch_single(tid: str) -> tuple[str, dict[str, Any] | None, str | None]:
            """Fetch single task, return (task_id, task_data, error)."""
            try:
                result = await client.get_task(task_list_id, tid)
                return (tid, result, None)
            except Exception as e:
                logger.warning("get_task_details_batch_item_failed", task_id=tid, error=str(e))
                return (tid, None, str(e))

        results = await asyncio.gather(*[fetch_single(tid) for tid in task_ids])

        # Collect successful tasks and errors
        tasks: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for tid, task_data, error in results:
            if task_data:
                tasks.append(task_data)
            if error:
                errors.append({"task_id": tid, "error": error})

        logger.info(
            "get_task_details_batch_success",
            user_id=str(user_id),
            requested_count=len(task_ids),
            success_count=len(tasks),
            error_count=len(errors),
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "tasks": tasks,
            "task_ids": task_ids,
            "task_list_id": task_list_id,
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "batch",
            "errors": errors if errors else None,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with task registry items.

        INTELLIA v10: Simplified - only builds registry_updates.
        Formatting is handled by response_node._simplify_task_payload() + fewshots.

        TIMEZONE: Dates are converted to user's timezone before storage.

        MULTI-ORDINAL FIX (2026-01-01): Handles both single and batch modes.
        - Single mode: One task in registry with full details
        - Batch mode: Multiple tasks in registry, errors in metadata
        """
        mode = result.get("mode", "single")
        task_list_id = result.get("task_list_id")
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)

        if mode == "batch":
            # Batch mode
            tasks = result.get("tasks", [])
            task_ids = result.get("task_ids", [])
            errors = result.get("errors")

            # build_tasks_output returns UnifiedToolOutput directly
            output = self.build_tasks_output(
                tasks=tasks,
                task_list_id=task_list_id,
                from_cache=False,
                user_timezone=user_timezone,
                locale=locale,
            )

            # Build batch summary
            summary_lines = [f"Task details retrieved: {len(tasks)} task(s)"]
            for i, t in enumerate(tasks[:5], 1):
                title = t.get("title", "Untitled")[:40]
                status = t.get("status", "needsAction")
                icon = "✅" if status == "completed" else "📋"
                summary_lines.append(f'{i}. {icon} "{title}"')
            if len(tasks) > 5:
                summary_lines.append(f"... and {len(tasks) - 5} more")

            output.message = "\n".join(summary_lines)
            output.metadata["task_ids"] = task_ids
            output.metadata["mode"] = "batch"
            if errors:
                output.metadata["errors"] = errors

            return output

        # Single mode
        task = result.get("task", {})
        task_id = result.get("task_id", "")

        if not task:
            return UnifiedToolOutput.failure(
                message="[details] Task not found",
                error_code="NOT_FOUND",
                metadata={"tool_name": "get_task_details_tool", "task_id": task_id},
            )

        # Wrap single task in list for build_tasks_output
        tasks = [task]

        # build_tasks_output returns UnifiedToolOutput directly
        output = self.build_tasks_output(
            tasks=tasks,
            task_list_id=task_list_id,
            from_cache=False,
            user_timezone=user_timezone,
            locale=locale,
        )

        # Add task_id to metadata
        output.metadata["task_id"] = task_id
        output.metadata["mode"] = "single"

        return output


_get_task_details_tool_instance = GetTaskDetailsTool()


@connector_tool(
    name="get_task_details",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="read",
)
async def get_task_details_tool(
    task_id: Annotated[str | None, "Task ID to retrieve details for (single mode)"] = None,
    task_ids: Annotated[
        list[str] | None,
        "List of Task IDs to retrieve (batch mode for multi-ordinal queries)",
    ] = None,
    task_list_id: Annotated[str, "Task list ID (default: '@default')"] = "@default",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get detailed information for one or more tasks.

    Supports both single and batch modes:
    - Single: task_id="abc123" → fetch one task
    - Batch: task_ids=["abc123", "def456"] → fetch multiple tasks in parallel

    MULTI-ORDINAL FIX (2026-01-01): Added batch mode for multi-reference queries.
    Example: "detail du 1 et du 2" → task_ids=["id1", "id2"]

    Returns complete task data including:
    - Title and status
    - Due date and completion date
    - Full notes/description
    - Parent task (if this is a subtask)
    - Attached links
    - Position in list

    Use this after list_tasks_tool to get full details of specific tasks.

    Args:
        task_id: Google Tasks task ID for single mode (from list_tasks_tool results)
        task_ids: List of Google Tasks task IDs for batch mode
        task_list_id: Task list ID (default: '@default')
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with TASK registry items containing full task data
    """
    return await _get_task_details_tool_instance.execute(
        runtime=runtime,
        task_id=task_id,
        task_ids=task_ids,
        task_list_id=task_list_id,
    )


# ============================================================================
# TOOL 3: CREATE TASK (with HITL Draft)
# ============================================================================


class CreateTaskDraftTool(ToolOutputMixin, ConnectorTool[GoogleTasksClient]):
    """
    Create task tool with Draft/HITL integration.

    Data Registry LOT 5.4: Write operations with confirmation flow.
    This tool creates a DRAFT that requires user confirmation before creating.
    """

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize create task draft tool."""
        super().__init__(tool_name="create_task_tool", operation="create_draft")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare task draft data (no API call yet).

        The actual creation happens after user confirms via HITL.
        """
        title: str = require_field(kwargs, "title")
        notes: str | None = kwargs.get("notes")
        due: str | None = kwargs.get("due")
        task_list_id_input: str = kwargs.get("task_list_id", "@default")

        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        logger.info(
            "create_task_draft_prepared",
            user_id=str(user_id),
            title=title,
            has_due=due is not None,
        )

        return {
            "title": title,
            "notes": notes,
            "due": due,
            "task_list_id": task_list_id,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create task draft via DraftService.

        Returns UnifiedToolOutput with HITL draft data in metadata.
        """
        from src.domains.agents.drafts import create_task_draft

        # create_task_draft returns UnifiedToolOutput directly
        return create_task_draft(
            title=result["title"],
            notes=result.get("notes"),
            due=result.get("due"),
            task_list_id=result.get("task_list_id", "@default"),
            source_tool="create_task_tool",
            user_language=self.get_user_language(),
        )


# Direct create tool for execute_fn callback
class CreateTaskDirectTool(ConnectorTool[GoogleTasksClient]):
    """Create task that executes immediately (for HITL callback)."""

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"

    def __init__(self) -> None:
        super().__init__(tool_name="create_task_direct_tool", operation="create")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute create task API call - business logic only."""
        title: str = kwargs["title"]
        notes: str | None = kwargs.get("notes")
        due: str | None = kwargs.get("due")
        task_list_id_input: str = kwargs.get("task_list_id", "@default")

        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        result = await client.create_task(
            task_list_id=task_list_id,
            title=title,
            notes=notes,
            due=due,
        )

        logger.info(
            "task_created_via_tool",
            user_id=str(user_id),
            task_id=result.get("id"),
            title=title,
        )

        return {
            "success": True,
            "task_id": result.get("id"),
            "title": title,
            "message": APIMessages.task_created_successfully(title),
        }


_create_task_draft_tool_instance = CreateTaskDraftTool()


@connector_tool(
    name="create_task",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="write",
)
async def create_task_tool(
    title: Annotated[str, "Task title (required)"],
    notes: Annotated[str | None, "Task notes/description (optional)"] = None,
    due: Annotated[str | None, "Due date in RFC 3339 format (e.g., '2025-01-15T00:00:00Z')"] = None,
    task_list_id: Annotated[str, "Task list ID (default: '@default')"] = "@default",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Create a new task in Google Tasks (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The task is NOT created until the user confirms via HITL.

    Args:
        title: Task title (required)
        notes: Task notes/description (optional)
        due: Due date in RFC 3339 format (optional)
        task_list_id: Task list ID (default: '@default')
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and HITL metadata
    """
    return await _create_task_draft_tool_instance.execute(
        runtime=runtime,
        title=title,
        notes=notes,
        due=due,
        task_list_id=task_list_id,
    )


# ============================================================================
# TOOL 3: COMPLETE TASK
# ============================================================================


class CompleteTaskTool(ConnectorTool[GoogleTasksClient]):
    """Mark a task as completed."""

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"

    def __init__(self) -> None:
        super().__init__(tool_name="complete_task_tool", operation="complete")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute complete task API call."""
        task_id: str = require_field(kwargs, "task_id")
        task_list_id_input: str = kwargs.get("task_list_id", "@default")

        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        result = await client.complete_task(task_list_id, task_id)

        logger.info(
            "task_completed",
            user_id=str(user_id),
            task_id=task_id,
            title=result.get("title"),
        )

        return {
            "success": True,
            "task_id": task_id,
            "title": result.get("title"),
            "message": f"Tâche '{result.get('title')}' marquée comme terminée",
        }


_complete_task_tool_instance = CompleteTaskTool()


@connector_tool(
    name="complete_task",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="write",
)
async def complete_task_tool(
    task_id: Annotated[str, "Task ID to mark as complete"],
    task_list_id: Annotated[str, "Task list ID (default: '@default')"] = "@default",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Mark a task as completed in Google Tasks.

    Args:
        task_id: Task ID to complete
        task_list_id: Task list ID (default: '@default')
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with confirmation message
    """
    return await _complete_task_tool_instance.execute(
        runtime=runtime,
        task_id=task_id,
        task_list_id=task_list_id,
    )


# ============================================================================
# TOOL 4: LIST TASK LISTS
# ============================================================================


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
        max_results: int = kwargs.get("max_results", get_settings.tasks_tool_default_max_results)

        result = await client.list_task_lists(max_results=max_results)

        task_lists = result.get("items", [])

        logger.info(
            "list_task_lists_success",
            user_id=str(user_id),
            total_results=len(task_lists),
        )

        return {"task_lists": task_lists}

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

        Note: Task lists don't go through fewshots (no display in response).
        They're used for internal reference only.
        """
        task_lists = result.get("task_lists", [])
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
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
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


# ============================================================================
# TOOL 5: UPDATE TASK (with HITL Draft)
# ============================================================================


class UpdateTaskDraftTool(ToolOutputMixin, ConnectorTool[GoogleTasksClient]):
    """
    Update task tool with Draft/HITL integration.

    Data Registry LOT 5.4: Write operations with confirmation flow.
    This tool creates a DRAFT that requires user confirmation before updating.
    """

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize update task draft tool."""
        super().__init__(tool_name="update_task_tool", operation="update_draft")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare task update draft data (no API call yet).

        The actual update happens after user confirms via HITL.
        """
        task_id: str = require_field(kwargs, "task_id")
        title: str | None = kwargs.get("title")
        notes: str | None = kwargs.get("notes")
        due: str | None = kwargs.get("due")
        status: str | None = kwargs.get("status")
        task_list_id_input: str = kwargs.get("task_list_id", "@default")

        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        logger.info(
            "update_task_draft_prepared",
            user_id=str(user_id),
            task_id=task_id,
            has_title=title is not None,
            has_notes=notes is not None,
            has_due=due is not None,
            has_status=status is not None,
        )

        return {
            "task_id": task_id,
            "title": title,
            "notes": notes,
            "due": due,
            "status": status,
            "task_list_id": task_list_id,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create task update draft via DraftService.

        Returns UnifiedToolOutput with HITL draft data in metadata.
        """
        from src.domains.agents.drafts import create_task_update_draft

        # create_task_update_draft returns UnifiedToolOutput directly
        return create_task_update_draft(
            task_id=result["task_id"],
            title=result.get("title"),
            notes=result.get("notes"),
            due=result.get("due"),
            status=result.get("status"),
            task_list_id=result.get("task_list_id", "@default"),
            source_tool="update_task_tool",
            user_language=self.get_user_language(),
        )


# Direct update tool for execute_fn callback
class UpdateTaskDirectTool(ConnectorTool[GoogleTasksClient]):
    """Update task that executes immediately (for HITL callback)."""

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"

    def __init__(self) -> None:
        super().__init__(tool_name="update_task_direct_tool", operation="update")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute update task API call - business logic only."""
        task_id: str = require_field(kwargs, "task_id")
        title: str | None = kwargs.get("title")
        notes: str | None = kwargs.get("notes")
        due: str | None = kwargs.get("due")
        status: str | None = kwargs.get("status")
        task_list_id_input: str = kwargs.get("task_list_id", "@default")

        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        result = await client.update_task(
            task_list_id=task_list_id,
            task_id=task_id,
            title=title,
            notes=notes,
            due=due,
            status=status,
        )

        logger.info(
            "task_updated_via_tool",
            user_id=str(user_id),
            task_id=task_id,
            title=result.get("title"),
        )

        return {
            "success": True,
            "task_id": task_id,
            "title": result.get("title"),
            "message": APIMessages.task_updated_successfully(result.get("title", "")),
        }


_update_task_draft_tool_instance = UpdateTaskDraftTool()


@connector_tool(
    name="update_task",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="write",
)
async def update_task_tool(
    task_id: Annotated[str, "Task ID to update (required)"],
    title: Annotated[str | None, "New task title (optional)"] = None,
    notes: Annotated[str | None, "New task notes/description (optional)"] = None,
    due: Annotated[str | None, "New due date in RFC 3339 format (optional)"] = None,
    status: Annotated[str | None, "New status: 'needsAction' or 'completed' (optional)"] = None,
    task_list_id: Annotated[str, "Task list ID (default: '@default')"] = "@default",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Update an existing task in Google Tasks (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The task is NOT updated until the user confirms via HITL.

    Args:
        task_id: Task ID to update (required)
        title: New task title (optional)
        notes: New task notes/description (optional)
        due: New due date in RFC 3339 format (optional)
        status: New status - 'needsAction' or 'completed' (optional)
        task_list_id: Task list ID (default: '@default')
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and HITL metadata
    """
    return await _update_task_draft_tool_instance.execute(
        runtime=runtime,
        task_id=task_id,
        title=title,
        notes=notes,
        due=due,
        status=status,
        task_list_id=task_list_id,
    )


# ============================================================================
# TOOL 6: DELETE TASK (with HITL confirmation)
# ============================================================================


class DeleteTaskDraftTool(ToolOutputMixin, ConnectorTool[GoogleTasksClient]):
    """
    Delete task tool with Draft/HITL integration.

    Data Registry LOT 5.4: Destructive operations require explicit confirmation.
    """

    functional_category = "tasks"

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize delete task draft tool."""
        super().__init__(tool_name="delete_task_tool", operation="delete_draft")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare task deletion draft data.

        First fetches task details to show user what will be deleted.
        """
        task_id: str = require_field(kwargs, "task_id")
        task_list_id_input: str = kwargs.get("task_list_id", "@default")

        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        if not task_id:
            raise ToolValidationError(APIMessages.field_required("task_id"), field="task_id")

        # Fetch task details to show user what will be deleted
        task = await client.get_task(task_list_id, task_id)

        logger.info(
            "delete_task_draft_prepared",
            user_id=str(user_id),
            task_id=task_id,
            title=task.get("title"),
        )

        return {
            "task_id": task_id,
            "title": task.get("title"),
            "notes": task.get("notes"),
            "due": task.get("due"),
            "status": task.get("status"),
            "task_list_id": task_list_id,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create task deletion draft via DraftService.

        Returns UnifiedToolOutput with HITL draft data in metadata.
        """
        from src.domains.agents.drafts import create_task_delete_draft

        # create_task_delete_draft returns UnifiedToolOutput directly
        return create_task_delete_draft(
            task_id=result["task_id"],
            title=result.get("title"),
            task_list_id=result.get("task_list_id", "@default"),
            source_tool="delete_task_tool",
            user_language=self.get_user_language(),
        )


# Direct delete tool for execute_fn callback
class DeleteTaskDirectTool(ConnectorTool[GoogleTasksClient]):
    """Delete task that executes immediately (for HITL callback)."""

    connector_type = ConnectorType.GOOGLE_TASKS
    client_class = GoogleTasksClient
    functional_category = "tasks"

    def __init__(self) -> None:
        super().__init__(tool_name="delete_task_direct_tool", operation="delete")

    async def execute_api_call(
        self,
        client: GoogleTasksClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute delete task API call - business logic only."""
        task_id: str = require_field(kwargs, "task_id")
        task_list_id_input: str = kwargs.get("task_list_id", "@default")

        # BugFix 2025-12-19: Resolve default task list from user preferences
        task_list_id = await _resolve_default_task_list(client, user_id, task_list_id_input)

        await client.delete_task(task_list_id, task_id)

        logger.info(
            "task_deleted_via_tool",
            user_id=str(user_id),
            task_id=task_id,
        )

        return {
            "success": True,
            "task_id": task_id,
            "message": APIMessages.task_deleted_successfully(),
        }


_delete_task_draft_tool_instance = DeleteTaskDraftTool()


@connector_tool(
    name="delete_task",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="write",
)
async def delete_task_tool(
    task_id: Annotated[str, "Task ID to delete (required)"],
    task_list_id: Annotated[str, "Task list ID (default: '@default')"] = "@default",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Delete a task from Google Tasks (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The task is NOT deleted until the user confirms via HITL.

    This is a destructive operation that cannot be undone.

    Args:
        task_id: Task ID to delete (required)
        task_list_id: Task list ID (default: '@default')
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and HITL metadata
    """
    return await _delete_task_draft_tool_instance.execute(
        runtime=runtime,
        task_id=task_id,
        task_list_id=task_list_id,
    )


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
    from src.domains.connectors.provider_resolver import resolve_active_connector

    connector_service = await deps.get_connector_service()
    resolved_type = await resolve_active_connector(user_id, "tasks", connector_service)

    if resolved_type is None:
        raise ConnectorNotEnabledError(
            APIMessages.connector_not_enabled("Tasks"),
            connector_name="Tasks",
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
        title=draft_content["title"],
        html_link=html_link,
    )

    return {
        "success": True,
        "task_id": task_id,
        "html_link": html_link,
        "title": draft_content["title"],
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
    )

    title = result.get("title", draft_content.get("title", ""))
    task_id = draft_content["task_id"]
    html_link = _build_task_url(task_id)

    logger.info(
        "task_update_draft_executed",
        user_id=str(user_id),
        task_id=task_id,
        title=title,
        html_link=html_link,
    )

    return {
        "success": True,
        "task_id": task_id,
        "html_link": html_link,
        "title": title,
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


# ============================================================================
# UNIFIED TOOL: GET TASKS (v2.0 - replaces list + details)
# ============================================================================


@connector_tool(
    name="get_tasks",
    agent_name=AGENT_TASK,
    context_domain=CONTEXT_DOMAIN_TASKS,
    category="read",
)
async def get_tasks_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    task_id: str | None = None,
    task_ids: list[str] | None = None,
    task_list_id: str | None = None,
    max_results: int | None = None,
    show_completed: bool = False,
    only_completed: bool = False,
) -> UnifiedToolOutput:
    """
    Get tasks with full details - unified list and retrieval.

    Architecture Simplification (2026-01):
    - Replaces list_tasks_tool + get_task_details_tool
    - Always returns FULL task details (title, notes, due date, status)
    - Supports ID mode (direct fetch) OR list mode

    Modes:
    - ID mode: get_tasks_tool(task_id="abc123") → fetch specific task
    - Batch mode: get_tasks_tool(task_ids=["abc", "def"]) → fetch multiple
    - List mode: get_tasks_tool() → return pending tasks with full details
    - Filter mode: get_tasks_tool(only_completed=True) → completed tasks only

    Args:
        runtime: Runtime dependencies injected automatically.
        task_id: Single task ID for direct fetch.
        task_ids: Multiple task IDs for batch fetch.
        task_list_id: Target task list (default: primary).
        max_results: Maximum results (default 10, max 50).
        show_completed: Include completed tasks (default False).
        only_completed: Only completed tasks (default False).

    Returns:
        UnifiedToolOutput with registry items containing task data.
    """
    # Route to appropriate implementation based on parameters
    if task_id or task_ids:
        # ID mode: direct fetch with full details
        return await _get_task_details_tool_instance.execute(
            runtime=runtime,
            task_id=task_id,
            task_ids=task_ids,
            task_list_id=task_list_id,
        )
    else:
        # List mode: return tasks with full details
        return await _list_tasks_tool_instance.execute(
            runtime=runtime,
            task_list_id=task_list_id,
            max_results=max_results,
            show_completed=show_completed,
            only_completed=only_completed,
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Unified tool (v2.0 - replaces list + details)
    "get_tasks_tool",
    # Action tools
    "create_task_tool",
    "complete_task_tool",
    "update_task_tool",
    "delete_task_tool",
    # Metadata tools (list containers)
    "list_task_lists_tool",
    # Tool classes
    "ListTasksTool",
    "GetTaskDetailsTool",
    "CreateTaskDraftTool",
    "CreateTaskDirectTool",
    "CompleteTaskTool",
    "ListTaskListsTool",
    "UpdateTaskDraftTool",
    "UpdateTaskDirectTool",
    "DeleteTaskDraftTool",
    "DeleteTaskDirectTool",
    # Draft execution
    "execute_task_draft",
    "execute_task_update_draft",
    "execute_task_delete_draft",
]
