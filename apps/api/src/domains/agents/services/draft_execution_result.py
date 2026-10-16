"""Existing draft outcome serialization, kept apart from execution orchestration.

The legacy result_data ABI is preserved verbatim; native application results
are validated by ApplicationExecutionOutcome before reaching this boundary.
"""

from __future__ import annotations

from typing import Any

from src.core.application_interaction import pending_interaction_of
from src.core.i18n import resolve_language
from src.domains.agents.drafts.card_spec import shown_value
from src.domains.agents.drafts.models import DraftAction
from src.domains.shared.markdown_literal import markdown_data_literal


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
        user_language: str | None = None,
    ) -> None:
        self.success = success
        self.draft_id = draft_id
        self.draft_type = draft_type
        self.action = action
        self.result_data = result_data or {}
        self.error = error
        self.user_language = resolve_language(user_language)

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

        if self.action == "cancel" and self.success:
            status = "cancelled"
            message = self._get_cancel_message()
        elif self.action == DraftAction.CONFIRM_BATCH.value:
            # Batch execution: aggregate results from multiple drafts
            batch_results = self.result_data.get("batch_results", [])
            success_count = self.result_data.get("success_count", 0)
            total_count = self.result_data.get("total_count", 0)
            status = (
                "success"
                if self.success
                else (
                    "waiting"
                    if self.result_data.get("waiting_count", 0)
                    and not self.result_data.get("error_count", 0)
                    else "partial_error"
                )
            )
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
        elif interaction := pending_interaction_of(self.result_data):
            from src.core.i18n_application import APPLICATION_INTERACTION_WAIT

            status = "waiting"
            message = APPLICATION_INTERACTION_WAIT[self.user_language][interaction.kind]
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
        """Get localized success message based on draft type and user language.

        The message heads the result card, in Markdown: the draft's values are
        drawn as themselves (``markdown_data_literal`` over ``shown_value``) —
        an event summary « Point ![x](…) » drew an image in the headline, and
        a value holding ``**`` read as LIA's own emphasis (review 14).
        """
        from src.core.i18n_drafts import get_draft_success_message

        if self.draft_type == "application_action":
            values = self.result_data.get("values")
            if (
                isinstance(values, dict)
                and values.get("launch_reserved") is True
                and values.get("execution_completed") is False
            ):
                from src.core.i18n_application import APPLICATION_ROUTINE_RUN

                return APPLICATION_ROUTINE_RUN[self.user_language].title

        if self.draft_type == "application_action" and self.result_data.get("no_op") is True:
            from src.core.i18n_application import APPLICATION_NOOP_MESSAGES

            return APPLICATION_NOOP_MESSAGES[self.user_language]

        def _drawn(key: str) -> str:
            value = self.result_data.get(key)
            return markdown_data_literal(shown_value(value)) if value else ""

        message = get_draft_success_message(
            draft_type=self.draft_type,
            language=self.user_language,
            name=_drawn("name"),
            summary=_drawn("summary"),
            title=_drawn("title"),
        )
        if self.draft_type == "mailbox_draft_send":
            from src.core.i18n_mailbox_send import filing_notice

            notice = filing_notice(
                self.user_language,
                draft_kept=self.result_data.get("draft_kept") is True,
                copy_missing=self.result_data.get("sent_copy_filed") is False,
            )
            if notice:
                return f"{message} {notice}"
        return message

    def _get_cancel_message(self) -> str:
        """Get localized cancellation message based on draft type and user language."""
        from src.core.i18n_drafts import get_draft_cancel_message

        return get_draft_cancel_message(
            draft_type=self.draft_type,
            language=self.user_language,
        )
