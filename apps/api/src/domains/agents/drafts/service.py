"""
Draft Service.

Provides the API for creating and managing deferred commands (drafts).
Enables the Draft → Critique → Execute flow with HITL integration.

Architecture:
- DraftService: Main service class for draft operations
- create_draft(): Create a draft RegistryItem for user confirmation
- execute_draft(): Execute a confirmed draft
- update_draft(): Update draft content after user edit
- cancel_draft(): Cancel a draft

Integration Points:
- RegistryItem (type=DRAFT): Drafts stored as registry items
- UnifiedToolOutput: Drafts returned via unified tool output
- HITL draft_critique: User confirmation via streaming HITL
- Prometheus metrics: Track draft lifecycle

Usage:
    from src.domains.agents.drafts import DraftService, EmailDraftInput

    # In a tool that wants deferred execution:
    async def send_email_with_confirmation(...) -> UnifiedToolOutput:
        service = DraftService()

        draft_input = EmailDraftInput(
            to="john@example.com",
            subject="Meeting",
            body="...",
        )

        # Create draft (doesn't send yet)
        return service.create_email_draft(
            draft_input=draft_input,
            related_registry_ids=["contact_abc123"],
        )

    # Later, after user confirms:
    result = await service.process_draft_action(request, draft, user_id, execute_fn)

Created: 2025-11-27
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.i18n_drafts import get_draft_summary_label
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.drafts.models import (
    ContactDeleteDraftInput,
    ContactDraftInput,
    ContactUpdateDraftInput,
    Draft,
    DraftAction,
    DraftActionRequest,
    DraftActionResult,
    DraftStatus,
    DraftType,
    EmailDeleteDraftInput,
    EmailDraftInput,
    EmailForwardDraftInput,
    EmailReplyDraftInput,
    EventDeleteDraftInput,
    EventDraftInput,
    EventUpdateDraftInput,
    FileDeleteDraftInput,
    LabelDeleteDraftInput,
    ReminderDeleteDraftInput,
    TaskDeleteDraftInput,
    TaskDraftInput,
    TaskUpdateDraftInput,
)
from src.domains.agents.tools.output import UnifiedToolOutput

logger = structlog.get_logger(__name__)


class DraftService:
    """
    Service for creating and managing drafts.

    Provides a unified interface for deferred action execution.
    All drafts are returned as UnifiedToolOutput with DRAFT RegistryItems.

    Thread Safety:
        This class is stateless - all state is in registry items.
        Safe for concurrent use.

    Prometheus Metrics:
        drafts_created_total: Counter by draft_type
        drafts_executed_total: Counter by draft_type, outcome
        draft_lifecycle_seconds: Histogram from create to execute

    Example:
        >>> service = DraftService()
        >>> output = service.create_email_draft(
        ...     EmailDraftInput(to="john@example.com", subject="Hi", body="..."),
        ... )
        >>> print(output.message)
        "Brouillon email créé: Email à john@example.com: Hi"
    """

    def __init__(self) -> None:
        """Initialize the Draft Service."""
        # Stateless - no instance state needed
        pass

    # =========================================================================
    # Draft Creation Methods
    # =========================================================================

    def create_draft(
        self,
        draft_type: DraftType,
        content: dict[str, Any],
        related_registry_ids: list[str] | None = None,
        source_tool: str | None = None,
        source_step_id: str | None = None,
        user_language: str = "fr",
    ) -> UnifiedToolOutput:
        """
        Create a draft of any type.

        Generic method for creating drafts. Use type-specific methods
        (create_email_draft, create_event_draft) for better type safety.

        Args:
            draft_type: Type of draft to create
            content: Draft content (type-specific structure)
            related_registry_ids: Registry IDs this draft relates to
            source_tool: Tool creating this draft
            source_step_id: Execution step ID
            user_language: Language for HITL questions

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        # Create the Draft object
        draft = Draft(
            type=draft_type,
            content=content,
            related_registry_ids=related_registry_ids or [],
            source_tool=source_tool,
            source_step_id=source_step_id,
        )

        # Create RegistryItem for the draft (includes detailed preview for frontend)
        registry_item = self._draft_to_registry_item(
            draft=draft,
            source_tool=source_tool,
            user_language=user_language,
        )

        # Build summary for LLM (includes detailed preview for LLM response)
        summary = self._build_draft_summary(draft, user_language)

        # Track metrics
        self._track_draft_created(draft_type)

        logger.info(
            "draft_created",
            draft_id=draft.id,
            draft_type=draft_type.value,
            related_ids_count=len(draft.related_registry_ids),
            source_tool=source_tool,
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates={draft.id: registry_item},
            structured_data={
                "draft": {
                    "id": draft.id,
                    "type": draft_type.value,
                },
            },
            metadata={
                "draft_id": draft.id,
                "draft_type": draft_type.value,
                "requires_confirmation": True,
            },
        )

    def create_email_draft(
        self,
        draft_input: EmailDraftInput,
        source_tool: str = "send_email_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create an email draft.

        The email will NOT be sent until user confirms via HITL.

        Args:
            draft_input: Email draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.EMAIL,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_email_delete_draft(
        self,
        draft_input: "EmailDeleteDraftInput",
        source_tool: str = "delete_email_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create an email deletion draft.

        The email will NOT be deleted (trashed) until user confirms via HITL.

        Args:
            draft_input: Email delete draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.EMAIL_DELETE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_reminder_delete_draft(
        self,
        draft_input: "ReminderDeleteDraftInput",
        source_tool: str = "cancel_reminder_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """Create a reminder deletion draft.

        The reminder will NOT be cancelled until user confirms via HITL.

        Args:
            draft_input: Reminder delete draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.REMINDER_DELETE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_email_reply_draft(
        self,
        draft_input: EmailReplyDraftInput,
        source_tool: str = "reply_email_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create an email reply draft.

        The reply will NOT be sent until user confirms via HITL.
        Maintains the same thread as the original message.

        Args:
            draft_input: Email reply draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.EMAIL_REPLY,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_email_forward_draft(
        self,
        draft_input: EmailForwardDraftInput,
        source_tool: str = "forward_email_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create an email forward draft.

        The forward will NOT be sent until user confirms via HITL.
        Creates a new thread with the forwarded message.

        Args:
            draft_input: Email forward draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.EMAIL_FORWARD,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_event_draft(
        self,
        draft_input: EventDraftInput,
        source_tool: str = "create_event_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a calendar event draft.

        The event will NOT be created until user confirms via HITL.

        Args:
            draft_input: Event draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.EVENT,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_contact_draft(
        self,
        draft_input: ContactDraftInput,
        source_tool: str = "create_contact_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a contact draft.

        The contact will NOT be created until user confirms via HITL.

        Args:
            draft_input: Contact draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.CONTACT,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_event_update_draft(
        self,
        draft_input: EventUpdateDraftInput,
        source_tool: str = "update_event_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a calendar event update draft.

        The event will NOT be updated until user confirms via HITL.

        Args:
            draft_input: Event update draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.EVENT_UPDATE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_event_delete_draft(
        self,
        draft_input: EventDeleteDraftInput,
        source_tool: str = "delete_event_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a calendar event delete draft.

        The event will NOT be deleted until user confirms via HITL.

        Args:
            draft_input: Event delete draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.EVENT_DELETE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_contact_update_draft(
        self,
        draft_input: ContactUpdateDraftInput,
        source_tool: str = "update_contact_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a contact update draft.

        The contact will NOT be updated until user confirms via HITL.

        Args:
            draft_input: Contact update draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.CONTACT_UPDATE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_contact_delete_draft(
        self,
        draft_input: ContactDeleteDraftInput,
        source_tool: str = "delete_contact_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a contact delete draft.

        The contact will NOT be deleted until user confirms via HITL.

        Args:
            draft_input: Contact delete draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.CONTACT_DELETE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_task_create_draft(
        self,
        draft_input: TaskDraftInput,
        source_tool: str = "create_task_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a task creation draft.

        The task will NOT be created until user confirms via HITL.

        Args:
            draft_input: Task draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.TASK,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_task_update_draft(
        self,
        draft_input: TaskUpdateDraftInput,
        source_tool: str = "update_task_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a task update draft.

        The task will NOT be updated until user confirms via HITL.

        Args:
            draft_input: Task update draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.TASK_UPDATE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_task_delete_draft(
        self,
        draft_input: TaskDeleteDraftInput,
        source_tool: str = "delete_task_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a task delete draft.

        The task will NOT be deleted until user confirms via HITL.

        Args:
            draft_input: Task delete draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.TASK_DELETE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_file_delete_draft(
        self,
        draft_input: FileDeleteDraftInput,
        source_tool: str = "delete_file_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a file delete draft.

        The file will NOT be deleted until user confirms via HITL.

        Args:
            draft_input: File delete draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.FILE_DELETE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    def create_label_delete_draft(
        self,
        draft_input: LabelDeleteDraftInput,
        source_tool: str = "delete_label_tool",
        source_step_id: str | None = None,
    ) -> UnifiedToolOutput:
        """
        Create a label delete draft.

        The label will NOT be deleted until user confirms via HITL.

        Args:
            draft_input: Label delete draft input data
            source_tool: Tool creating this draft
            source_step_id: Execution step ID

        Returns:
            UnifiedToolOutput with DRAFT RegistryItem
        """
        return self.create_draft(
            draft_type=DraftType.LABEL_DELETE,
            content=draft_input.model_dump(),
            related_registry_ids=draft_input.related_registry_ids,
            source_tool=source_tool,
            source_step_id=source_step_id,
            user_language=draft_input.user_language,
        )

    # =========================================================================
    # Draft Action Methods
    # =========================================================================

    async def process_draft_action(
        self,
        request: DraftActionRequest,
        draft: Draft,
        user_id: UUID,
        execute_fn: Any | None = None,
    ) -> DraftActionResult:
        """
        Process a user action on a draft.

        Called by HITL resumption when user confirms/edits/cancels.

        Args:
            request: Action request from frontend
            draft: Current draft object
            user_id: User performing the action
            execute_fn: Async function to execute the draft (for CONFIRM)
                        Should have signature: async (draft, user_id) -> dict

        Returns:
            DraftActionResult with outcome

        Raises:
            ValueError: If draft status doesn't allow the action
        """
        logger.info(
            "draft_action_processing",
            draft_id=request.draft_id,
            action=request.action.value,
            current_status=draft.status.value,
        )

        if request.action == DraftAction.CONFIRM:
            return await self._execute_draft(draft, user_id, execute_fn)

        elif request.action == DraftAction.EDIT:
            return self._update_draft(draft, request.updated_content or {})

        elif request.action == DraftAction.CANCEL:
            return self._cancel_draft(draft)

        else:
            return DraftActionResult(
                draft_id=draft.id,
                action=request.action,
                success=False,
                new_status=draft.status,
                error_message=f"Unknown action: {request.action}",
            )

    async def _execute_draft(
        self,
        draft: Draft,
        user_id: UUID,
        execute_fn: Any | None,
    ) -> DraftActionResult:
        """
        Execute a confirmed draft.

        Args:
            draft: Draft to execute
            user_id: User performing execution
            execute_fn: Async function to execute

        Returns:
            DraftActionResult with execution outcome
        """
        if draft.status not in (DraftStatus.PENDING, DraftStatus.MODIFIED):
            return DraftActionResult(
                draft_id=draft.id,
                action=DraftAction.CONFIRM,
                success=False,
                new_status=draft.status,
                error_message=f"Cannot execute draft in status: {draft.status.value}",
            )

        if execute_fn is None:
            return DraftActionResult(
                draft_id=draft.id,
                action=DraftAction.CONFIRM,
                success=False,
                new_status=draft.status,
                error_message="No execution function provided",
            )

        try:
            # Execute the draft
            result = await execute_fn(draft, user_id)

            # Mark as executed
            executed_draft = draft.mark_executed(result)

            self._track_draft_executed(draft.type, "success")

            logger.info(
                "draft_executed",
                draft_id=draft.id,
                draft_type=draft.type.value,
            )

            return DraftActionResult(
                draft_id=draft.id,
                action=DraftAction.CONFIRM,
                success=True,
                new_status=DraftStatus.EXECUTED,
                execution_result=result,
                updated_draft=executed_draft,
            )

        except Exception as e:
            # Mark as failed
            failed_draft = draft.mark_failed(str(e))

            self._track_draft_executed(draft.type, "failed")

            logger.error(
                "draft_execution_failed",
                draft_id=draft.id,
                draft_type=draft.type.value,
                error=str(e),
                exc_info=True,
            )

            return DraftActionResult(
                draft_id=draft.id,
                action=DraftAction.CONFIRM,
                success=False,
                new_status=DraftStatus.FAILED,
                error_message=str(e),
                updated_draft=failed_draft,
            )

    def _update_draft(
        self,
        draft: Draft,
        new_content: dict[str, Any],
    ) -> DraftActionResult:
        """
        Update draft content after user edit.

        Args:
            draft: Draft to update
            new_content: New content from user

        Returns:
            DraftActionResult with updated draft
        """
        if draft.status not in (DraftStatus.PENDING, DraftStatus.MODIFIED):
            return DraftActionResult(
                draft_id=draft.id,
                action=DraftAction.EDIT,
                success=False,
                new_status=draft.status,
                error_message=f"Cannot edit draft in status: {draft.status.value}",
            )

        # Merge new content with existing
        merged_content = {**draft.content, **new_content}
        updated_draft = draft.mark_modified(merged_content)

        logger.info(
            "draft_updated",
            draft_id=draft.id,
            draft_type=draft.type.value,
            fields_updated=list(new_content.keys()),
        )

        return DraftActionResult(
            draft_id=draft.id,
            action=DraftAction.EDIT,
            success=True,
            new_status=DraftStatus.MODIFIED,
            updated_draft=updated_draft,
        )

    def _cancel_draft(self, draft: Draft) -> DraftActionResult:
        """
        Cancel a draft.

        Args:
            draft: Draft to cancel

        Returns:
            DraftActionResult confirming cancellation
        """
        if draft.status in (DraftStatus.EXECUTED, DraftStatus.CANCELLED):
            return DraftActionResult(
                draft_id=draft.id,
                action=DraftAction.CANCEL,
                success=False,
                new_status=draft.status,
                error_message=f"Cannot cancel draft in status: {draft.status.value}",
            )

        cancelled_draft = draft.mark_cancelled()

        self._track_draft_executed(draft.type, "cancelled")

        logger.info(
            "draft_cancelled",
            draft_id=draft.id,
            draft_type=draft.type.value,
        )

        return DraftActionResult(
            draft_id=draft.id,
            action=DraftAction.CANCEL,
            success=True,
            new_status=DraftStatus.CANCELLED,
            updated_draft=cancelled_draft,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _draft_to_registry_item(
        self,
        draft: Draft,
        source_tool: str | None = None,
        user_language: str = "fr",
    ) -> RegistryItem:
        """
        Convert a Draft to a RegistryItem.

        Args:
            draft: Draft to convert
            source_tool: Tool that created the draft
            user_language: Language for summary/preview labels

        Returns:
            RegistryItem with draft payload including detailed preview
        """
        # Extract user_timezone from draft content (set by BaseDraftInput)
        user_timezone = draft.content.get("user_timezone", "Europe/Paris")

        return RegistryItem(
            id=draft.id,
            type=RegistryItemType.DRAFT,
            payload={
                "draft_type": draft.type.value,
                "status": draft.status.value,
                "content": draft.content,
                "related_registry_ids": draft.related_registry_ids,
                "created_at": draft.created_at.isoformat(),
                "summary": draft.get_summary(user_language),
                # Detailed preview for user confirmation display
                "detailed_preview": draft.get_detailed_preview(user_language, user_timezone),
                # HITL metadata
                "actions": ["confirm", "edit", "cancel"],
                "requires_confirmation": True,
            },
            meta=RegistryItemMeta(
                source="draft_service",
                domain="drafts",
                tool_name=source_tool,
            ),
        )

    def _build_draft_summary(
        self,
        draft: Draft,
        user_language: str = "fr",
    ) -> str:
        """
        Build LLM summary for a draft with detailed content preview.

        Shows full draft content (e.g., email to/subject/body) for user verification.
        This enables the user to review exactly what will be executed before confirming.

        Args:
            draft: Draft to summarize
            user_language: Language for summary (fr, en, es, de, it, zh-CN)

        Returns:
            Human-readable summary string with full draft details
        """
        # Extract user_timezone from draft content (set by BaseDraftInput)
        user_timezone = draft.content.get("user_timezone", "Europe/Paris")

        # Get the brief title for the header
        draft_title = draft.get_summary(user_language)

        # Get the detailed preview with full content
        detailed_preview = draft.get_detailed_preview(user_language, user_timezone)

        # Build the full summary with header, content preview, and action prompt
        # Using centralized i18n for all 6 supported languages
        header = get_draft_summary_label(
            "draft_created",
            user_language,
            title=draft_title,
        )
        action_prompt = "<br/><br/>" + get_draft_summary_label(
            "action_required",
            user_language,
        )

        return f"{header}\n\n{detailed_preview}\n\n{action_prompt}"

    def _track_draft_created(self, draft_type: DraftType) -> None:
        """Track draft creation metric."""
        try:
            from src.infrastructure.observability.metrics_agents import (
                registry_drafts_created_total,
            )

            registry_drafts_created_total.labels(draft_type=draft_type.value).inc()
        except Exception:
            pass  # Metrics are non-critical

    def _track_draft_executed(self, draft_type: DraftType, outcome: str) -> None:
        """Track draft execution metric."""
        try:
            from src.infrastructure.observability.metrics_agents import (
                registry_drafts_executed_total,
            )

            registry_drafts_executed_total.labels(
                draft_type=draft_type.value,
                outcome=outcome,
            ).inc()
        except Exception:
            pass  # Metrics are non-critical


# ============================================================================
# Convenience Functions
# ============================================================================


def create_email_draft(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    is_html: bool = False,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "send_email_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create an email draft.

    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
        cc: CC recipients
        bcc: BCC recipients
        is_html: Whether body is HTML
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = EmailDraftInput(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        is_html=is_html,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_email_draft(draft_input, source_tool=source_tool)


def create_reminder_delete_draft(
    reminder_id: str,
    content: str = "",
    trigger_at: str = "",
    related_registry_ids: list[str] | None = None,
    source_tool: str = "cancel_reminder_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """Convenience function to create a reminder delete draft.

    Args:
        reminder_id: Reminder UUID to cancel
        content: Reminder content for confirmation display
        trigger_at: Trigger datetime for confirmation display
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    from src.domains.agents.drafts.models import ReminderDeleteDraftInput

    service = DraftService()
    draft_input = ReminderDeleteDraftInput(
        reminder_id=reminder_id,
        content=content,
        trigger_at=trigger_at,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_reminder_delete_draft(draft_input, source_tool=source_tool)


def create_email_delete_draft(
    message_id: str,
    subject: str = "(sans objet)",
    from_addr: str = "",
    date: str = "",
    thread_id: str | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "delete_email_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create an email delete draft.

    Args:
        message_id: Message ID to delete
        subject: Email subject for confirmation display
        from_addr: Sender email for confirmation display
        date: Email date for confirmation display
        thread_id: Thread ID
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    from src.domains.agents.drafts.models import EmailDeleteDraftInput

    service = DraftService()
    draft_input = EmailDeleteDraftInput(
        message_id=message_id,
        subject=subject,
        from_addr=from_addr,
        date=date,
        thread_id=thread_id,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_email_delete_draft(draft_input, source_tool=source_tool)


def create_email_reply_draft(
    message_id: str,
    to: str,
    subject: str,
    body: str,
    reply_all: bool = False,
    original_subject: str = "",
    original_from: str = "",
    thread_id: str | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "reply_email_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create an email reply draft.

    Args:
        message_id: Original message ID to reply to
        to: Recipient email (original sender)
        subject: Email subject (with Re: prefix)
        body: Reply message body
        reply_all: Reply to all recipients
        original_subject: Original email subject
        original_from: Original sender
        thread_id: Thread ID to maintain
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    from src.domains.agents.drafts.models import EmailReplyDraftInput

    service = DraftService()
    draft_input = EmailReplyDraftInput(
        message_id=message_id,
        to=to,
        subject=subject,
        body=body,
        reply_all=reply_all,
        original_subject=original_subject,
        original_from=original_from,
        thread_id=thread_id,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_email_reply_draft(draft_input, source_tool=source_tool)


def create_email_forward_draft(
    message_id: str,
    to: str,
    subject: str,
    body: str | None = None,
    cc: str | None = None,
    original_subject: str = "",
    original_from: str = "",
    attachments: list[dict[str, Any]] | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "forward_email_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create an email forward draft.

    Args:
        message_id: Original message ID to forward
        to: Forward recipient email
        subject: Email subject (with Fwd: prefix)
        body: Additional message to prepend
        cc: CC recipients
        original_subject: Original email subject
        original_from: Original sender
        attachments: Attachment info for preview
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    from src.domains.agents.drafts.models import EmailForwardDraftInput

    service = DraftService()
    draft_input = EmailForwardDraftInput(
        message_id=message_id,
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        original_subject=original_subject,
        original_from=original_from,
        attachments=attachments or [],
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_email_forward_draft(draft_input, source_tool=source_tool)


def create_event_draft(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone: str = "Europe/Paris",
    calendar_id: str | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "create_event_tool",
    user_language: str = "fr",
    user_timezone: str | None = None,
) -> UnifiedToolOutput:
    """
    Convenience function to create an event draft.

    Args:
        summary: Event title
        start_datetime: Start datetime (ISO)
        end_datetime: End datetime (ISO)
        description: Event description
        location: Event location
        attendees: Attendee emails
        timezone: Timezone
        calendar_id: Calendar ID. If None or "primary", uses user's default calendar preference.
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL
        user_timezone: User's IANA timezone for datetime display (defaults to timezone param)

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = EventDraftInput(
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        description=description,
        location=location,
        attendees=attendees or [],
        timezone=timezone,
        calendar_id=calendar_id,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
        user_timezone=user_timezone or timezone,
    )
    return service.create_event_draft(draft_input, source_tool=source_tool)


def create_contact_draft(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "create_contact_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create a contact draft.

    Args:
        name: Contact name
        email: Contact email
        phone: Contact phone
        organization: Company name
        notes: Additional notes
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = ContactDraftInput(
        name=name,
        email=email,
        phone=phone,
        organization=organization,
        notes=notes,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_contact_draft(draft_input, source_tool=source_tool)


def create_update_event_draft(
    event_id: str,
    summary: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone: str = "Europe/Paris",
    calendar_id: str | None = None,
    current_event: dict[str, Any] | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "update_event_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create an event update draft.

    Args:
        event_id: ID of event to update
        summary: New event title (optional)
        start_datetime: New start datetime (ISO format, optional)
        end_datetime: New end datetime (ISO format, optional)
        description: New event description (optional)
        location: New event location (optional)
        attendees: New attendee emails (optional)
        timezone: Timezone
        calendar_id: Calendar ID. If None or "primary", uses user's default calendar preference.
        current_event: Current event data for comparison
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = EventUpdateDraftInput(
        event_id=event_id,
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        description=description,
        location=location,
        attendees=attendees,
        timezone=timezone,
        calendar_id=calendar_id,
        current_event=current_event or {},
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_event_update_draft(draft_input, source_tool=source_tool)


def create_delete_event_draft(
    event_id: str,
    current_event: dict[str, Any] | None = None,
    summary: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone: str = "Europe/Paris",
    send_updates: str = "all",
    calendar_id: str | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "delete_event_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create an event delete draft.

    Homogenized with create_event_update_draft: carries flat fields + full event
    object to enable draft type changes (delete ↔ update) during HITL.

    Args:
        event_id: ID of event to delete.
        current_event: Full event object for display and type change.
        summary: Event title (extracted from current_event).
        start_datetime: Start datetime ISO (extracted from current_event).
        end_datetime: End datetime ISO (extracted from current_event).
        description: Event description.
        location: Event location.
        attendees: Attendee email list.
        timezone: Timezone.
        send_updates: How to notify attendees (all, externalOnly, none).
        calendar_id: Calendar ID.
        related_registry_ids: Related registry items.
        source_tool: Source tool name.
        user_language: Language for HITL.

    Returns:
        UnifiedToolOutput with draft.
    """
    service = DraftService()
    draft_input = EventDeleteDraftInput(
        event_id=event_id,
        current_event=current_event or {},
        summary=summary,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        description=description,
        location=location,
        attendees=attendees,
        timezone=timezone,
        send_updates=send_updates,
        calendar_id=calendar_id,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_event_delete_draft(draft_input, source_tool=source_tool)


def create_contact_update_draft(
    resource_name: str,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    address: str | None = None,
    current_contact: dict[str, Any] | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "update_contact_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create a contact update draft.

    Args:
        resource_name: Contact resource name (people/c...)
        name: New contact name (optional)
        email: New contact email (optional)
        phone: New contact phone (optional)
        organization: New company name (optional)
        notes: New notes (optional)
        address: New address (optional, e.g. '15 rue de la Paix, Paris 75001')
        current_contact: Current contact data for comparison
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = ContactUpdateDraftInput(
        resource_name=resource_name,
        name=name,
        email=email,
        phone=phone,
        organization=organization,
        notes=notes,
        address=address,
        current_contact=current_contact or {},
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_contact_update_draft(draft_input, source_tool=source_tool)


def create_contact_delete_draft(
    resource_name: str,
    current_contact: dict[str, Any] | None = None,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    address: str | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "delete_contact_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create a contact delete draft.

    Homogenized with create_contact_update_draft for draft type changes.

    Args:
        resource_name: Contact resource name (people/c...).
        current_contact: Full contact object for display and type change.
        name: Contact name.
        email: Contact email.
        phone: Contact phone.
        organization: Company name.
        notes: Notes.
        address: Address.
        related_registry_ids: Related registry items.
        source_tool: Source tool name.
        user_language: Language for HITL.

    Returns:
        UnifiedToolOutput with draft.
    """
    service = DraftService()
    draft_input = ContactDeleteDraftInput(
        resource_name=resource_name,
        current_contact=current_contact or {},
        name=name,
        email=email,
        phone=phone,
        organization=organization,
        notes=notes,
        address=address,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_contact_delete_draft(draft_input, source_tool=source_tool)


def create_task_draft(
    title: str,
    notes: str | None = None,
    due: str | None = None,
    task_list_id: str = "@default",
    related_registry_ids: list[str] | None = None,
    source_tool: str = "create_task_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create a task draft.

    Args:
        title: Task title
        notes: Task notes/description
        due: Due date (RFC 3339 format)
        task_list_id: Task list ID
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = TaskDraftInput(
        title=title,
        notes=notes,
        due=due,
        task_list_id=task_list_id,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_task_create_draft(draft_input, source_tool=source_tool)


def create_task_update_draft(
    task_id: str,
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
    status: str | None = None,
    task_list_id: str = "@default",
    current_task: dict[str, Any] | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "update_task_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create a task update draft.

    Args:
        task_id: Task ID to update
        title: New task title (optional)
        notes: New task notes (optional)
        due: New due date (RFC 3339 format, optional)
        status: New status - needsAction or completed (optional)
        task_list_id: Task list ID
        current_task: Current task data for comparison
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = TaskUpdateDraftInput(
        task_id=task_id,
        title=title,
        notes=notes,
        due=due,
        status=status,
        task_list_id=task_list_id,
        current_task=current_task or {},
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_task_update_draft(draft_input, source_tool=source_tool)


def create_task_delete_draft(
    task_id: str,
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
    status: str | None = None,
    task_list_id: str = "@default",
    current_task: dict[str, Any] | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "delete_task_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create a task delete draft.

    Homogenized with create_task_update_draft for draft type changes.

    Args:
        task_id: Task ID to delete.
        title: Task title.
        notes: Task notes.
        due: Due date (RFC 3339).
        status: Status (needsAction or completed).
        task_list_id: Task list ID.
        current_task: Full task object for type change.
        related_registry_ids: Related registry items.
        source_tool: Source tool name.
        user_language: Language for HITL.

    Returns:
        UnifiedToolOutput with draft.
    """
    service = DraftService()
    draft_input = TaskDeleteDraftInput(
        task_id=task_id,
        title=title,
        notes=notes,
        due=due,
        status=status,
        task_list_id=task_list_id,
        current_task=current_task or {},
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_task_delete_draft(draft_input, source_tool=source_tool)


def create_file_delete_draft(
    file_id: str,
    file: dict[str, Any] | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "delete_file_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create a file delete draft.

    Args:
        file_id: Drive file ID to delete
        file: File data for confirmation display
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = FileDeleteDraftInput(
        file_id=file_id,
        file=file or {},
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_file_delete_draft(draft_input, source_tool=source_tool)


def create_label_delete_draft(
    label_id: str,
    label_name: str,
    sublabels: list[dict[str, Any]] | None = None,
    children_only: bool = False,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "delete_label_tool",
    user_language: str = "fr",
) -> UnifiedToolOutput:
    """
    Convenience function to create a label delete draft.

    Args:
        label_id: Gmail label ID to delete
        label_name: Full label path (e.g., pro/capge/2024)
        sublabels: List of sublabels that will also be deleted
        children_only: If True, only delete sublabels, keep parent
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = LabelDeleteDraftInput(
        label_id=label_id,
        label_name=label_name,
        sublabels=sublabels or [],
        children_only=children_only,
        related_registry_ids=related_registry_ids or [],
        user_language=user_language,
    )
    return service.create_label_delete_draft(draft_input, source_tool=source_tool)


# ============================================================================
# Backward Compatibility Aliases (to be removed after migration)
# ============================================================================

# Alias for backward compatibility during migration
DraftService = DraftService
