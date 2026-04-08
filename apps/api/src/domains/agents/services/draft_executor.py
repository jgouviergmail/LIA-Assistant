"""
Draft Executor Service - Data Registry LOT 5.4 Write Operations

Executes confirmed drafts after user approval via HITL.

Architecture:
    1. draft_critique_node sets draft_action_result in state (confirm/edit/cancel)
    2. response_node calls execute_draft_if_confirmed()
    3. Function routes to appropriate execute_*_draft() function
    4. Execution result added to agent_results for response synthesis

Flow:
    draft_critique_node → state["draft_action_result"] = {action: "confirm", ...}
    → response_node → execute_draft_if_confirmed()
    → execute_email_draft() / execute_contact_draft() / execute_event_draft()
    → result → agent_results["draft_execution"] = {...}

Dependency Injection:
    Uses ToolDependencies from config["configurable"]["__deps"] which provides
    access to ConnectorService and DB session (same as tools).

Generic Pattern:
    DraftExecutor uses a registry of executor functions per draft_type.
    This makes it easy to add new draft types (e.g., tasks, notes).

References:
    - draft_critique_node.py: Sets draft_action_result
    - calendar_tools.py: execute_event_draft()
    - emails_tools.py: execute_email_draft()
    - google_contacts_tools.py: execute_contact_draft()
    - command_api.py: DraftService.process_draft_action()
    - dependencies.py: ToolDependencies container

Created: 2025-11-26
Data Registry LOT 5.4: Write Operations
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

import structlog
from langchain_core.runnables import RunnableConfig

from src.core.field_names import FIELD_METADATA, FIELD_USER_ID
from src.domains.agents.drafts.models import DraftAction, DraftType
from src.infrastructure.observability.metrics_agents import (
    registry_drafts_executed_total,
)

logger = structlog.get_logger(__name__)

# Type alias for executor functions
ExecutorFn = Callable[[dict[str, Any], UUID, Any], Coroutine[Any, Any, dict[str, Any]]]

# Registry of executor functions per draft type
# Populated by register_executor() or lazily on first use
_EXECUTOR_REGISTRY: dict[str, ExecutorFn] = {}


def register_executor(draft_type: str, executor_fn: ExecutorFn) -> None:
    """
    Register an executor function for a draft type.

    Args:
        draft_type: Draft type string (email, event, contact, etc.)
        executor_fn: Async function(draft_content, user_id, deps) -> result_dict
    """
    _EXECUTOR_REGISTRY[draft_type] = executor_fn
    logger.debug(
        "draft_executor_registered",
        draft_type=draft_type,
        executor_fn=executor_fn.__name__,
    )


def _ensure_executors_registered() -> None:
    """
    Lazy-load executor functions to avoid circular imports.

    Called on first use of DraftExecutor.
    Registers all draft type executors for the HITL confirmation flow.
    """
    if _EXECUTOR_REGISTRY:
        return  # Already registered

    # Import and register all executor functions
    try:
        # Calendar executors
        from src.domains.agents.tools.calendar_tools import (
            execute_event_delete_draft,
            execute_event_draft,
            execute_event_update_draft,
        )

        # Drive executors
        from src.domains.agents.tools.drive_tools import execute_file_delete_draft

        # Email executors
        from src.domains.agents.tools.emails_tools import (
            execute_email_delete_draft,
            execute_email_draft,
            execute_email_forward_draft,
            execute_email_reply_draft,
        )

        # Contact executors
        from src.domains.agents.tools.google_contacts_tools import (
            execute_contact_delete_draft,
            execute_contact_draft,
            execute_contact_update_draft,
        )

        # Label executors
        from src.domains.agents.tools.labels_tools import execute_label_delete_draft

        # Reminder executors
        from src.domains.agents.tools.reminder_tools import execute_reminder_delete_draft

        # Task executors
        from src.domains.agents.tools.tasks_tools import (
            execute_task_delete_draft,
            execute_task_draft,
            execute_task_update_draft,
        )

        # Register all executors
        # Email
        register_executor(DraftType.EMAIL.value, execute_email_draft)
        register_executor(DraftType.EMAIL_REPLY.value, execute_email_reply_draft)
        register_executor(DraftType.EMAIL_FORWARD.value, execute_email_forward_draft)
        register_executor(DraftType.EMAIL_DELETE.value, execute_email_delete_draft)

        # Calendar events
        register_executor(DraftType.EVENT.value, execute_event_draft)
        register_executor(DraftType.EVENT_UPDATE.value, execute_event_update_draft)
        register_executor(DraftType.EVENT_DELETE.value, execute_event_delete_draft)

        # Contacts
        register_executor(DraftType.CONTACT.value, execute_contact_draft)
        register_executor(DraftType.CONTACT_UPDATE.value, execute_contact_update_draft)
        register_executor(DraftType.CONTACT_DELETE.value, execute_contact_delete_draft)

        # Tasks
        register_executor(DraftType.TASK.value, execute_task_draft)
        register_executor(DraftType.TASK_UPDATE.value, execute_task_update_draft)
        register_executor(DraftType.TASK_DELETE.value, execute_task_delete_draft)

        # Drive files
        register_executor(DraftType.FILE_DELETE.value, execute_file_delete_draft)

        # Labels
        register_executor(DraftType.LABEL_DELETE.value, execute_label_delete_draft)

        # Reminders
        register_executor(DraftType.REMINDER_DELETE.value, execute_reminder_delete_draft)

        logger.info(
            "draft_executors_initialized",
            registered_types=list(_EXECUTOR_REGISTRY.keys()),
            total_count=len(_EXECUTOR_REGISTRY),
        )
    except ImportError as e:
        logger.error(
            "draft_executor_import_error",
            error=str(e),
        )


class DraftExecutionResult:
    """
    Result of draft execution.

    Attributes:
        success: Whether execution succeeded
        draft_id: ID of the executed draft
        draft_type: Type of draft (email, event, contact)
        action: Action performed (confirm, edit, cancel)
        result_data: Execution result data (e.g., event_id, email_id)
        error: Error message if failed
        user_language: User's language for localized messages
    """

    def __init__(
        self,
        success: bool,
        draft_id: str,
        draft_type: str,
        action: str,
        result_data: dict[str, Any] | None = None,
        error: str | None = None,
        user_language: str = "fr",
    ) -> None:
        self.success = success
        self.draft_id = draft_id
        self.draft_type = draft_type
        self.action = action
        self.result_data = result_data or {}
        self.error = error
        self.user_language = user_language

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for state storage."""
        return {
            "success": self.success,
            "draft_id": self.draft_id,
            "draft_type": self.draft_type,
            "action": self.action,
            "result_data": self.result_data,
            "error": self.error,
        }

    def to_agent_result(self) -> dict[str, Any]:
        """
        Convert to agent result format for response synthesis.

        Returns format compatible with format_agent_results_for_prompt().
        """
        from src.core.i18n_drafts import get_draft_error_message

        if self.action == "cancel":
            status = "cancelled"
            message = self._get_cancel_message()
        elif self.action == DraftAction.CONFIRM_BATCH.value:
            # Batch execution: aggregate results from multiple drafts
            batch_results = self.result_data.get("batch_results", [])
            success_count = self.result_data.get("success_count", 0)
            total_count = self.result_data.get("total_count", 0)
            status = "success" if self.success else "partial_error"
            message = "\n".join(r.get("message", "") for r in batch_results if r.get("message"))
            return {
                "status": status,
                "data": self.result_data,
                "message": message,
                "draft_id": self.draft_id,
                "draft_type": self.draft_type,
                "action": self.action,
                "batch_size": total_count,
                "success_count": success_count,
            }
        elif self.success:
            status = "success"
            message = self._get_success_message()
        else:
            status = "error"
            message = self.error or get_draft_error_message(self.user_language)

        return {
            "status": status,
            "data": self.result_data,
            "message": message,
            "draft_id": self.draft_id,
            "draft_type": self.draft_type,
            "action": self.action,
        }

    def _get_success_message(self) -> str:
        """Get localized success message based on draft type and user language."""
        from src.core.i18n_drafts import get_draft_success_message

        # Extract dynamic values from result_data for placeholder substitution
        return get_draft_success_message(
            draft_type=self.draft_type,
            language=self.user_language,
            name=self.result_data.get("name", ""),
            summary=self.result_data.get("summary", ""),
            title=self.result_data.get("title", ""),
        )

    def _get_cancel_message(self) -> str:
        """Get localized cancellation message based on draft type and user language."""
        from src.core.i18n_drafts import get_draft_cancel_message

        return get_draft_cancel_message(
            draft_type=self.draft_type,
            language=self.user_language,
        )


async def execute_draft_if_confirmed(
    draft_action_result: dict[str, Any] | None,
    config: RunnableConfig,
    run_id: str,
    user_language: str = "fr",
) -> DraftExecutionResult | None:
    """
    Execute draft if user confirmed via HITL.

    Data Registry LOT 5.4: Main entry point for draft execution.
    Called by response_node after draft_critique_node sets draft_action_result.

    Args:
        draft_action_result: State from draft_critique_node with:
            - action: "confirm" | "edit" | "cancel"
            - draft_id: Draft identifier
            - draft_type: Type of draft
            - draft_content: Draft content dict
        config: RunnableConfig with metadata (user_id) and __deps (ToolDependencies)
        run_id: Run ID for logging
        user_language: User's language for localized messages (default: "fr")

    Returns:
        DraftExecutionResult if action requires response, None if no action needed

    Note:
        - "confirm" → Execute draft via executor function
        - "edit" → Return result indicating edit in progress (re-critique)
        - "cancel" → Return result indicating cancellation
    """
    _ensure_executors_registered()

    if not draft_action_result:
        return None

    action = draft_action_result.get("action")
    draft_id = draft_action_result.get("draft_id", "unknown")
    draft_type = draft_action_result.get("draft_type", "unknown")

    logger.info(
        "draft_executor_processing",
        run_id=run_id,
        action=action,
        draft_id=draft_id,
        draft_type=draft_type,
    )

    if action == "confirm":
        return await _execute_confirmed_draft(draft_action_result, config, run_id, user_language)

    elif action == DraftAction.CONFIRM_BATCH.value:
        return await _execute_confirmed_batch(draft_action_result, config, run_id, user_language)

    elif action == "edit":
        # Edit means user wants to modify - this triggers re-critique
        # Return result so response_node knows what happened
        return DraftExecutionResult(
            success=True,
            draft_id=draft_id,
            draft_type=draft_type,
            action="edit",
            result_data={"needs_reconfirmation": True},
            user_language=user_language,
        )

    elif action == "cancel":
        # User cancelled - return cancellation result for response
        registry_drafts_executed_total.labels(
            draft_type=draft_type,
            outcome="cancelled",
        ).inc()

        return DraftExecutionResult(
            success=True,
            draft_id=draft_id,
            draft_type=draft_type,
            action="cancel",
            user_language=user_language,
        )

    else:
        logger.warning(
            "draft_executor_unknown_action",
            run_id=run_id,
            action=action,
            draft_id=draft_id,
        )
        return None


async def _execute_confirmed_draft(
    draft_action_result: dict[str, Any],
    config: RunnableConfig,
    run_id: str,
    user_language: str = "fr",
) -> DraftExecutionResult:
    """
    Execute a confirmed draft using ToolDependencies from config.

    Args:
        draft_action_result: Confirmation result from draft_critique_node
        config: RunnableConfig with __deps containing ToolDependencies
        run_id: Run ID for logging
        user_language: User's language for localized messages

    Returns:
        DraftExecutionResult with execution outcome
    """
    draft_id = draft_action_result.get("draft_id", "unknown")
    draft_type = draft_action_result.get("draft_type", "unknown")
    draft_content = draft_action_result.get("draft_content", {})

    logger.info(
        "draft_executor_executing",
        run_id=run_id,
        draft_id=draft_id,
        draft_type=draft_type,
        content_keys=list(draft_content.keys()),
    )

    # Get executor for this draft type
    executor_fn = _EXECUTOR_REGISTRY.get(draft_type)

    if not executor_fn:
        error_msg = f"No executor registered for draft type: {draft_type}"
        logger.error(
            "draft_executor_no_executor",
            run_id=run_id,
            draft_type=draft_type,
            available_types=list(_EXECUTOR_REGISTRY.keys()),
        )
        registry_drafts_executed_total.labels(
            draft_type=draft_type,
            outcome="failed",
        ).inc()

        return DraftExecutionResult(
            success=False,
            draft_id=draft_id,
            draft_type=draft_type,
            action="confirm",
            error=error_msg,
            user_language=user_language,
        )

    # Extract ToolDependencies from config
    deps = config.get("configurable", {}).get("__deps")
    if not deps:
        error_msg = "ToolDependencies not found in config"
        logger.error(
            "draft_executor_no_deps",
            run_id=run_id,
            draft_id=draft_id,
            config_keys=list(config.get("configurable", {}).keys()),
        )
        registry_drafts_executed_total.labels(
            draft_type=draft_type,
            outcome="failed",
        ).inc()

        return DraftExecutionResult(
            success=False,
            draft_id=draft_id,
            draft_type=draft_type,
            action="confirm",
            error=error_msg,
            user_language=user_language,
        )

    # Extract user_id from config
    # LOT 6 FIX: LangGraph may not preserve metadata through node execution,
    # but configurable is always passed. Try configurable first, then metadata.
    user_id_str = config.get("configurable", {}).get(FIELD_USER_ID)
    if not user_id_str:
        # Fallback to metadata (older path, may not work in all cases)
        user_id_str = config.get(FIELD_METADATA, {}).get("user_id")
    if not user_id_str:
        error_msg = "user_id not found in config (checked configurable and metadata)"
        logger.error(
            "draft_executor_no_user_id",
            run_id=run_id,
            draft_id=draft_id,
            configurable_keys=list(config.get("configurable", {}).keys()),
            metadata_keys=list(config.get(FIELD_METADATA, {}).keys()),
        )
        registry_drafts_executed_total.labels(
            draft_type=draft_type,
            outcome="failed",
        ).inc()

        return DraftExecutionResult(
            success=False,
            draft_id=draft_id,
            draft_type=draft_type,
            action="confirm",
            error=error_msg,
            user_language=user_language,
        )

    try:
        user_id = UUID(user_id_str) if isinstance(user_id_str, str) else user_id_str

        # Execute draft using the registered executor
        # Executor functions have signature: (draft_content, user_id, deps) -> result_dict
        result_data = await executor_fn(draft_content, user_id, deps)

        registry_drafts_executed_total.labels(
            draft_type=draft_type,
            outcome="success",
        ).inc()

        logger.info(
            "draft_executor_success",
            run_id=run_id,
            draft_id=draft_id,
            draft_type=draft_type,
            result_keys=list(result_data.keys()) if result_data else [],
        )

        # Enrich result_data with draft_content for comprehensive post-HITL display
        # This allows _format_draft_execution_result to show ALL attributes
        if result_data and isinstance(result_data, dict):
            result_data["_draft_content"] = draft_content

        return DraftExecutionResult(
            success=True,
            draft_id=draft_id,
            draft_type=draft_type,
            action="confirm",
            result_data=result_data,
            user_language=user_language,
        )

    except Exception as e:
        registry_drafts_executed_total.labels(
            draft_type=draft_type,
            outcome="failed",
        ).inc()

        logger.error(
            "draft_executor_failed",
            run_id=run_id,
            draft_id=draft_id,
            draft_type=draft_type,
            error=str(e),
            exc_info=True,
        )

        return DraftExecutionResult(
            success=False,
            draft_id=draft_id,
            draft_type=draft_type,
            action="confirm",
            error=str(e),
            user_language=user_language,
        )


async def _execute_confirmed_batch(
    draft_action_result: dict[str, Any],
    config: RunnableConfig,
    run_id: str,
    user_language: str = "fr",
) -> DraftExecutionResult:
    """
    Execute a batch of confirmed drafts from FOR_EACH approval.

    When a FOR_EACH HITL confirms a batch operation, all drafts in the batch
    are executed sequentially. Returns a composite result.

    Args:
        draft_action_result: Batch result with {"action": "confirm_batch", "batch": [...]}
        config: RunnableConfig with __deps containing ToolDependencies
        run_id: Run ID for logging
        user_language: User's language for localized messages

    Returns:
        DraftExecutionResult with batch execution outcome
    """
    batch = draft_action_result.get("batch", [])
    if not batch:
        return DraftExecutionResult(
            success=False,
            draft_id="batch",
            draft_type="batch",
            action=DraftAction.CONFIRM_BATCH.value,
            error="Empty batch",
            user_language=user_language,
        )

    logger.info(
        "draft_executor_batch_started",
        run_id=run_id,
        batch_size=len(batch),
        draft_types=[d.get("draft_type") for d in batch],
    )

    results: list[dict[str, Any]] = []
    success_count = 0
    error_count = 0

    for i, single_draft in enumerate(batch):
        try:
            single_result = await _execute_confirmed_draft(
                single_draft, config, run_id, user_language
            )
            if single_result.success:
                success_count += 1
            else:
                error_count += 1
            results.append(single_result.to_agent_result())
        except Exception as e:
            error_count += 1
            logger.error(
                "draft_executor_batch_item_failed",
                run_id=run_id,
                batch_index=i,
                draft_id=single_draft.get("draft_id"),
                error=str(e),
            )
            results.append(
                {
                    "status": "error",
                    "draft_id": single_draft.get("draft_id", "unknown"),
                    "draft_type": single_draft.get("draft_type", "unknown"),
                    "message": str(e),
                }
            )

    logger.info(
        "draft_executor_batch_completed",
        run_id=run_id,
        batch_size=len(batch),
        success_count=success_count,
        error_count=error_count,
    )

    # Return composite result
    return DraftExecutionResult(
        success=error_count == 0,
        draft_id="batch",
        draft_type=batch[0].get("draft_type", "batch"),
        action=DraftAction.CONFIRM_BATCH.value,
        result_data={
            "batch_results": results,
            "success_count": success_count,
            "error_count": error_count,
            "total_count": len(batch),
        },
        user_language=user_language,
    )


__all__ = [
    "execute_draft_if_confirmed",
    "DraftExecutionResult",
    "register_executor",
]
