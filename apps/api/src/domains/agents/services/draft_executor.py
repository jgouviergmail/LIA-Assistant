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
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

import structlog
from langchain_core.runnables import RunnableConfig

from src.core.field_names import FIELD_METADATA, FIELD_USER_ID
from src.domains.agents.context.access import get_tcm_session
from src.domains.agents.drafts.models import DraftAction, DraftType
from src.infrastructure.observability.metrics_agents import (
    registry_drafts_executed_total,
)

if TYPE_CHECKING:
    from src.domains.agents.context.access import TcmSession

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


# Canonical per-domain id-key convention. Single source of truth: adding a new
# domain here + one draft type → tcm_domain row below is enough.
_DOMAIN_ID_KEYS: dict[str, tuple[str, ...]] = {
    "events": ("event_id",),
    "contacts": ("resource_name",),
    "tasks": ("task_id",),
    "emails": ("message_id", "id"),
}

# Draft type → TCM domain (plural key used by namespace).
_DRAFT_TYPE_TO_TCM_DOMAIN: dict[str, str] = {
    # Create
    "event": "events",
    "contact": "contacts",
    "task": "tasks",
    "email": "emails",
    "email_reply": "emails",
    "email_forward": "emails",
    # Update
    "event_update": "events",
    "contact_update": "contacts",
    "task_update": "tasks",
    # Delete
    "event_delete": "events",
    "contact_delete": "contacts",
    "task_delete": "tasks",
    "email_delete": "emails",
}

# Derived from _DOMAIN_ID_KEYS — never edit by hand.
_DRAFT_TYPE_TO_ID_KEYS: dict[str, tuple[str, ...]] = {
    draft_type: _DOMAIN_ID_KEYS[domain] for draft_type, domain in _DRAFT_TYPE_TO_TCM_DOMAIN.items()
}


DraftFamily = Literal["create", "update", "delete"]


def _classify_draft_type(draft_type: str) -> DraftFamily:
    """Return the draft family.

    Args:
        draft_type: Canonical draft type string (e.g. "event_update").

    Returns:
        "delete" for `*_delete`, "update" for `*_update`, else "create".
    """
    if draft_type.endswith("_delete"):
        return "delete"
    if draft_type.endswith("_update"):
        return "update"
    return "create"


def _extract_item_id(
    draft_type: str,
    draft_content: dict[str, Any],
    result_data: dict[str, Any] | None,
) -> str | None:
    """Extract the canonical item id for a draft type.

    Prefers result_data (post-execution fresh id) over draft_content.

    Args:
        draft_type: Canonical draft type string (e.g. "event_delete").
        draft_content: Original draft content payload.
        result_data: Executor return value, may be None.

    Returns:
        The first non-empty value found among the id keys declared for the
        draft type, stringified. None when no id can be found.
    """
    keys = _DRAFT_TYPE_TO_ID_KEYS.get(draft_type, ())
    sources = (result_data or {}, draft_content)
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value:
                return str(value)
    return None


async def _set_current_from_merged(
    session: TcmSession,
    domain: str,
    merged_item: dict[str, Any],
) -> None:
    """Write merged_item as the current_item for the given domain.

    Shared by create and update handlers. Uses set_by="auto" since the write
    is triggered by HITL approval, not an explicit user "focus" action.

    Args:
        session: Active TCM session (manager + store + identifiers).
        domain: TCM domain (plural key, e.g. "events").
        merged_item: Full post-execution item payload.
    """
    await session.manager.set_current_item(
        user_id=session.user_id,
        session_id=session.session_id,
        domain=domain,
        item=merged_item,
        set_by="auto",
        turn_id=0,
        store=session.store,
    )


async def _sync_create(
    session: TcmSession,
    domain: str,
    merged_item: dict[str, Any],
    draft_type: str,
    run_id: str,
) -> None:
    """CREATE family → set current only. List is untouched (item wasn't in it).

    Args:
        session: Active TCM session.
        domain: TCM domain (plural key).
        merged_item: Post-execution item payload.
        draft_type: Draft type, for logging correlation.
        run_id: Run ID, for logging correlation.
    """
    await _set_current_from_merged(session, domain, merged_item)
    logger.info(
        "tcm_sync_after_create",
        run_id=run_id,
        draft_type=draft_type,
        domain=domain,
    )


async def _sync_update(
    session: TcmSession,
    domain: str,
    item_id: str | None,
    merged_item: dict[str, Any],
    draft_type: str,
    run_id: str,
) -> None:
    """UPDATE family → set current AND propagate merged payload to list in place.

    Args:
        session: Active TCM session.
        domain: TCM domain (plural key).
        item_id: Canonical item id; required for list propagation.
        merged_item: Post-execution item payload.
        draft_type: Draft type, for logging correlation.
        run_id: Run ID, for logging correlation.
    """
    await _set_current_from_merged(session, domain, merged_item)
    updated_in_list = False
    if item_id:
        updated_in_list = await session.manager.update_item_in_list(
            user_id=session.user_id,
            session_id=session.session_id,
            domain=domain,
            item_id=item_id,
            updated_item=merged_item,
            store=session.store,
        )
    logger.info(
        "tcm_sync_after_update",
        run_id=run_id,
        draft_type=draft_type,
        domain=domain,
        item_id=item_id,
        propagated_to_list=updated_in_list,
    )


async def _sync_delete(
    session: TcmSession,
    domain: str,
    item_id: str | None,
    draft_type: str,
    run_id: str,
) -> None:
    """DELETE family → remove from list; clear current if the deleted item was focused.

    Args:
        session: Active TCM session.
        domain: TCM domain (plural key).
        item_id: Canonical item id; no-op if None.
        draft_type: Draft type, used for logging and current-item matching.
        run_id: Run ID, for logging correlation.
    """
    if not item_id:
        logger.debug(
            "tcm_sync_delete_skipped_no_item_id",
            run_id=run_id,
            draft_type=draft_type,
        )
        return

    removed = await session.manager.remove_item_from_list(
        user_id=session.user_id,
        session_id=session.session_id,
        domain=domain,
        item_id=item_id,
        store=session.store,
    )

    # Safety net: if the item wasn't in the list but was current (direct-fetch
    # flow with no prior search), explicitly clear current.
    if not removed:
        current = await session.manager.get_current_item(
            user_id=session.user_id,
            session_id=session.session_id,
            domain=domain,
            store=session.store,
        )
        if current and _current_matches_id(current, item_id, draft_type):
            await session.manager.clear_current_item(
                user_id=session.user_id,
                session_id=session.session_id,
                domain=domain,
                store=session.store,
            )

    logger.info(
        "tcm_sync_after_delete",
        run_id=run_id,
        draft_type=draft_type,
        domain=domain,
        item_id=item_id,
        list_had_item=removed,
    )


def _current_matches_id(current: dict[str, Any], item_id: str, draft_type: str) -> bool:
    """Check whether current_item points at the given item id.

    Matching uses the draft type's canonical id keys plus a generic "id"
    fallback, to tolerate both raw API payloads and TCM-enriched items.

    Args:
        current: current_item payload from TCM.
        item_id: Canonical id string to compare against.
        draft_type: Draft type used to look up the id keys.

    Returns:
        True if any id key on ``current`` matches ``item_id``.
    """
    keys = _DRAFT_TYPE_TO_ID_KEYS.get(draft_type, ())
    return any(str(current.get(k, "")) == item_id for k in keys) or (
        str(current.get("id", "")) == item_id
    )


async def _sync_tcm_after_draft_execution(
    draft_type: str,
    draft_content: dict[str, Any],
    result_data: dict[str, Any] | None,
    config: RunnableConfig,
    run_id: str,
) -> None:
    """Propagate draft execution to the TCM (list + current) per draft family.

    Dispatches to a family-specific handler (create / update / delete) and
    enforces the invariant "current = last manipulated/searched/evoked".
    Failures are caught and logged — this side-effect never blocks draft
    execution.

    Args:
        draft_type: Draft type (e.g., "event_update", "task_delete").
        draft_content: Original draft content (contains canonical ids).
        result_data: Execution result with enriched item data.
        config: RunnableConfig with user_id and thread_id in configurable.
        run_id: Run ID for logging correlation.
    """
    domain = _DRAFT_TYPE_TO_TCM_DOMAIN.get(draft_type)
    if not domain:
        return

    try:
        session = await get_tcm_session(config)
        if session is None:
            return

        item_id = _extract_item_id(draft_type, draft_content, result_data or {})
        family = _classify_draft_type(draft_type)

        if family == "delete":
            await _sync_delete(session, domain, item_id, draft_type, run_id)
        else:
            if not result_data:
                return
            merged_item = {**draft_content, **result_data}
            if family == "update":
                await _sync_update(session, domain, item_id, merged_item, draft_type, run_id)
            else:  # create
                await _sync_create(session, domain, merged_item, draft_type, run_id)

    except Exception:
        logger.exception(
            "tcm_sync_after_draft_failed",
            run_id=run_id,
            draft_type=draft_type,
        )


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

        # Propagate execution to TCM (list + current) per draft family.
        # Create/update → set current + update list in place.
        # Delete → remove from list + clear current if match.
        await _sync_tcm_after_draft_execution(
            draft_type, draft_content, result_data, config, run_id
        )

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
