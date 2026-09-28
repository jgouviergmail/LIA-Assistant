"""
Destructive Confirm Interaction - Enhanced HITL for dangerous bulk operations.

This module implements HitlInteractionProtocol for destructive_confirm type.
It provides enhanced confirmation UX for operations that:
- Affect multiple items (bulk deletions)
- Cannot be undone (permanent operations)
- Have significant impact (all emails, all contacts, etc.)

Features:
    - Severity-based UI styling (CRITICAL level)
    - Affected item count display
    - Optional confirmation text requirement
    - Multi-language support via i18n_hitl
    - Registry IDs for preview of affected items

Use Cases:
    - "Delete all my e-mails from Jean"
    - "Remove every contact of group X"
    - "Cancel all my meetings this week"

Status (ADR-323): registered, and emitted by NO node. No production code
calls ``should_trigger_destructive_confirm`` (below) nor
``scope_detector.should_escalate_to_destructive_confirm`` — the one caller of
``detect_dangerous_scope`` in ``src/`` — and no node produces the ``destructive_confirm``
type: the flow these were written for (a scope detector deciding, the
planner triggering this dialog) was never wired. ADR-323 lists the chain
among those to delete together; only the title and three keys of its
translation table are read, by the draft critique.

References:
    - protocols.py: HitlInteractionProtocol definition
    - registry.py: Registration decorator
    - schemas.py: DestructiveConfirmContext
    - scope_detector.py: Danger scope detection

Created: 2026-01-11
Phase 3: HITL Safety Enrichment
"""

import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, SCOPE_BULK_THRESHOLD
from src.core.field_names import FIELD_CONVERSATION_ID
from src.core.i18n import resolve_language
from src.core.i18n_drafts import label_separator
from src.core.i18n_hitl import HitlMessages, HitlMessageType
from src.core.text_clip import one_line
from src.core.time_utils import format_value_if_datetime_string
from src.infrastructure.observability.logging import get_logger

from ..protocols import HitlInteractionType
from ..registry import HitlInteractionRegistry
from ..schemas import (
    STANDARD_DESTRUCTIVE_ACTIONS,
    DestructiveConfirmContext,
    HitlSeverity,
)
from .text_tokens import text_tokens

if TYPE_CHECKING:
    from langchain_core.callbacks.base import BaseCallbackHandler

    from ..question_generator import HitlQuestionGenerator

logger = get_logger(__name__)

#: The fields an item is named by, in priority order.
_READABLE_FIELDS = ("subject", "name", "summary", "title", "displayName")


# Use shared threshold from centralized constants
BULK_OPERATION_THRESHOLD = SCOPE_BULK_THRESHOLD


@HitlInteractionRegistry.register(HitlInteractionType.DESTRUCTIVE_CONFIRM)
class DestructiveConfirmInteraction:
    """
    HITL interaction for dangerous bulk operations.

    Generates enhanced warning questions when operations affect multiple items
    or have irreversible consequences. Uses CRITICAL severity for UI styling.

    Attributes:
        question_generator: HitlQuestionGenerator instance for LLM calls

    Example:
        >>> generator = HitlQuestionGenerator()
        >>> interaction = DestructiveConfirmInteraction(question_generator=generator)
        >>> async for token in interaction.generate_question_stream(
        ...     context={
        ...         "operation_type": "delete_emails",
        ...         "affected_count": 15,
        ...         "affected_items": [{"subject": "Email 1"}, ...],
        ...     },
        ...     user_language="fr",
        ... ):
        ...     print(token, end="", flush=True)
    """

    def __init__(self, question_generator: HitlQuestionGenerator) -> None:
        """
        Initialize DestructiveConfirmInteraction.

        Args:
            question_generator: HitlQuestionGenerator instance for LLM calls
        """
        self._question_generator = question_generator

    @property
    def interaction_type(self) -> HitlInteractionType:
        """Get the interaction type."""
        return HitlInteractionType.DESTRUCTIVE_CONFIRM

    async def generate_question_stream(
        self,
        context: DestructiveConfirmContext | dict[str, Any],
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        tracker: BaseCallbackHandler | None = None,
    ) -> AsyncGenerator[str]:
        """
        Generate destructive confirmation warning via streaming.

        Creates a clear warning message about the operation's scope and
        impact, requiring explicit user confirmation.

        Args:
            context: Typed DestructiveConfirmContext or dict with:
                - operation_type: Type of destructive operation
                - affected_count: Number of items affected
                - affected_items: Preview of items (optional)
                - warning_message: Custom warning (optional)
            user_language: Language code (fr, en, es, de, it, zh-CN)
            user_timezone: User's IANA timezone
            tracker: Optional TokenTrackingCallback

        Yields:
            str: Tokens of the warning message

        Performance:
            - TTFT target: < 100ms (mostly static content)
            - Total duration: < 500ms
        """
        from src.infrastructure.observability.metrics_agents import (
            hitl_question_ttft_seconds,
        )

        # Extract values from typed context or dict (backwards compatible)
        custom_warning: str | None
        if isinstance(context, DestructiveConfirmContext):
            operation_type = context.operation_type
            affected_count = context.affected_count
            affected_items = context.affected_items
            custom_warning = context.warning_message
        else:
            operation_type = context.get("operation_type", "unknown")
            affected_count = context.get("affected_count", 1)
            affected_items = context.get("affected_items", [])
            custom_warning = context.get("warning_message")

        logger.debug(
            "destructive_confirm_question_started",
            operation_type=operation_type,
            affected_count=affected_count,
            user_language=user_language,
        )

        start_time = time.time()

        # Build the warning message
        warning = self._build_warning_message(
            operation_type=operation_type,
            affected_count=affected_count,
            affected_items=affected_items,
            custom_warning=custom_warning,
            user_language=user_language,
            user_timezone=user_timezone,
        )

        # Stream token by token, its lines and no-break spaces kept
        for token_index, token in enumerate(text_tokens(warning)):
            if token_index == 0:
                ttft = time.time() - start_time
                hitl_question_ttft_seconds.labels(type="destructive_confirm").observe(ttft)
            yield token

        logger.debug(
            "destructive_confirm_question_complete",
            operation_type=operation_type,
            affected_count=affected_count,
            duration_ms=int((time.time() - start_time) * 1000),
        )

    def _build_warning_message(
        self,
        operation_type: str,
        affected_count: int,
        affected_items: list[dict[str, Any]],
        custom_warning: str | None,
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    ) -> str:
        """
        Build structured warning message for destructive operation.

        Args:
            operation_type: Type of operation
            affected_count: Number of items
            affected_items: Item previews
            custom_warning: Custom warning text
            user_language: Language code
            user_timezone: User's IANA timezone for date formatting

        Returns:
            Formatted warning message
        """
        # Get localized strings
        translations = self._get_translations(user_language)

        # Map operation_type (e.g., "delete_emails") to draft_type (e.g., "email_delete")
        # for action-specific title lookup
        _OP_TO_DRAFT_TYPE = {
            "delete_emails": "email_delete",
            "delete_events": "event_delete",
            "delete_contacts": "contact_delete",
            "delete_tasks": "task_delete",
            "delete_files": "file_delete",
            "delete_labels": "label_delete",
        }
        draft_type_key = _OP_TO_DRAFT_TYPE.get(operation_type, "")
        specific_title = HitlMessages.get_destructive_confirm_title(draft_type_key, user_language)

        # Header with action-specific title
        header = f"⚠️ **{specific_title}**\n\n"

        # Operation description
        op_desc = self._get_operation_description(operation_type, affected_count, user_language)
        body = f"{op_desc}\n\n"

        # Item preview (max 5)
        if affected_items:
            body += (
                f"**{translations['affected_items']}{label_separator(user_language).rstrip()}**\n"
            )
            for item in affected_items[:5]:
                item_desc = self._format_item_preview(item, user_timezone, user_language)
                body += f"- {item_desc}\n"
            if affected_count > 5:
                body += f"- {translations['and_more'].format(count=affected_count - 5)}\n"
            body += "\n"

        # Warning
        warning_text = custom_warning or translations["default_warning"]
        body += f"🚨 {warning_text}\n\n"

        # Confirmation question
        body += f"**{translations['confirm_question']}**"

        return header + body

    def _get_operation_description(
        self,
        operation_type: str,
        affected_count: int,
        user_language: str,
    ) -> str:
        """Get localized operation description using centralized i18n_hitl."""
        return HitlMessages.get_destructive_operation_description(
            operation_type=operation_type,
            count=affected_count,
            language=user_language,
        )

    def _get_translations(self, user_language: str) -> dict[str, str]:
        """Get UI translations using centralized i18n_hitl."""
        return HitlMessages.get_destructive_confirm_translations(user_language)

    def _format_item_preview(
        self,
        item: dict[str, Any],
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        user_language: str | None = None,
    ) -> str:
        """
        Format a single item for preview display.

        Extracts the most relevant field and formats any datetime values
        using the user's timezone.

        Args:
            item: Item preview dict with domain-specific fields
            user_timezone: User's IANA timezone for date formatting
            user_language: User's locale for date formatting

        Returns:
            Formatted preview string
        """
        # The first readable field that says something, on one line (the
        # bullet stays one row): a field present with None, spaces, an empty
        # value or False says nothing — it read « None » or « False », in
        # English, in six languages. The reading ``item_label`` makes of a draft.
        preview = ""
        for key in _READABLE_FIELDS:
            value = item.get(key)
            preview = one_line(str(value)) if value else ""
            if preview:
                break
        if not preview:
            # Nothing a person reads: named in their language, never an id
            # cut in silence nor an English « item ».
            preview = self._get_translations(resolve_language(user_language))["unnamed_item"]

        # Format any datetime values in remaining fields for context
        for key in ("date", "start_datetime", "due", "dateTime"):
            value = item.get(key)
            if value and isinstance(value, str):
                formatted = format_value_if_datetime_string(
                    value,
                    user_timezone=user_timezone,
                    locale=resolve_language(user_language),
                    include_time=True,
                    include_day_name=False,
                )
                if formatted != value:
                    preview += f" ({formatted})"
                    break  # Only add one date for conciseness

        return preview

    def build_metadata_chunk(
        self,
        context: DestructiveConfirmContext | dict[str, Any],
        message_id: str,
        conversation_id: str,
        registry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Build metadata for the destructive confirmation HITL chunk.

        Uses CRITICAL severity for UI styling (red/warning theme).

        Args:
            context: Typed DestructiveConfirmContext or dict with operation details
            message_id: Unique message ID
            conversation_id: Conversation UUID string
            registry_ids: Registry IDs for affected items

        Returns:
            Metadata dict for hitl_interrupt_metadata chunk
        """
        # Extract values from typed context or dict (backwards compatible)
        if isinstance(context, DestructiveConfirmContext):
            operation_type = context.operation_type
            affected_count = context.affected_count
        else:
            operation_type = context.get("operation_type", "unknown")
            affected_count = context.get("affected_count", 1)

        if registry_ids is None:
            registry_ids = (
                []
                if isinstance(context, DestructiveConfirmContext)
                else context.get("registry_ids", [])
            )

        # Build action_requests with destructive styling
        action_requests = [
            {
                "type": "destructive_confirm",
                "operation_type": operation_type,
                "affected_count": affected_count,
                "available_actions": [
                    {"action": a.action, "label": a.label, "style": a.style.value}
                    for a in STANDARD_DESTRUCTIVE_ACTIONS
                ],
                "registry_ids": registry_ids,
            }
        ]

        return {
            "message_id": message_id,
            FIELD_CONVERSATION_ID: conversation_id,
            "action_requests": action_requests,
            "count": 1,
            "is_plan_approval": False,
            # Destructive-specific metadata
            "operation_type": operation_type,
            "affected_count": affected_count,
            "severity": HitlSeverity.CRITICAL.value,
            "registry_ids": registry_ids,
            "has_registry_items": len(registry_ids) > 0,
        }

    def get_fallback_question(self, user_language: str) -> str:
        """
        Get fallback question for error scenarios using centralized i18n_hitl.

        Returns a generic confirmation question.

        Args:
            user_language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Static fallback question string
        """
        return "⚠️ " + HitlMessages.get_fallback(HitlMessageType.DESTRUCTIVE_CONFIRM, user_language)


def should_trigger_destructive_confirm(
    operation_type: str,
    affected_count: int,
) -> bool:
    """
    Determine if an operation should trigger destructive confirmation.

    Args:
        operation_type: Type of operation being performed
        affected_count: Number of items affected

    Returns:
        True if destructive confirmation should be triggered
    """
    # Always trigger for delete operations with multiple items
    if operation_type.startswith("delete_") and affected_count >= BULK_OPERATION_THRESHOLD:
        return True

    # Trigger for any operation affecting many items (uses shared threshold)
    if affected_count >= BULK_OPERATION_THRESHOLD:
        return True

    return False
