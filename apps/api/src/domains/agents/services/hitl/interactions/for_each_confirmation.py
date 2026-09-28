"""
ForEach Confirmation Interaction - HITL for bulk iteration operations.

This module implements HitlInteractionProtocol for for_each_confirmation type.
It provides confirmation UX for for_each operations that iterate over collections
and apply mutations (send, create, update, delete) to multiple items.

Features:
    - Mutation type detection (send_email, create_event, etc.)
    - Iteration count display
    - Multi-language support via i18n_hitl
    - Streaming question generation

Use Cases:
    - "Send an e-mail to all my contacts"
    - "Create an event for each participant"
    - "Delete all the e-mails from Jean"

Architecture:
    ScopeDetector.detect_for_each_scope() → requires_approval=True
    → task_orchestrator_node triggers interrupt
    → ForEachConfirmationInteraction generates question
    → User confirms/cancels → Execution proceeds or aborts

References:
    - protocols.py: HitlInteractionProtocol definition
    - registry.py: Registration decorator
    - scope_detector.py: for_each scope detection
    - plan_planner.md Section 12: FOR_EACH HITL specification

Created: 2026-01-18
"""

import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.field_names import FIELD_CONVERSATION_ID
from src.core.i18n_drafts import format_hitl_item_preview, label_separator
from src.core.i18n_hitl import HitlMessages, HitlMessageType
from src.core.text_clip import clip_spelled, one_line, spell_unseen
from src.core.time_utils import format_value_if_iso_datetime
from src.domains.shared.markdown_literal import markdown_data_literal
from src.infrastructure.observability.logging import get_logger

from ..protocols import HitlInteractionType
from ..registry import HitlInteractionRegistry
from ..schemas import HitlSeverity
from .text_tokens import text_tokens

if TYPE_CHECKING:
    from langchain_core.callbacks.base import BaseCallbackHandler

    from ..question_generator import HitlQuestionGenerator

logger = get_logger(__name__)

#: The longest a value of the generic item preview may be, ellipsis included.
_PREVIEW_VALUE_MAX_CHARS = 50


@HitlInteractionRegistry.register(HitlInteractionType.FOR_EACH_CONFIRMATION)
class ForEachConfirmationInteraction:
    """
    HITL interaction for for_each bulk iteration operations.

    Generates confirmation questions when for_each operations will apply
    mutations (send, create, update, delete) to multiple items.

    Attributes:
        question_generator: HitlQuestionGenerator instance for LLM calls

    Example:
        >>> generator = HitlQuestionGenerator()
        >>> interaction = ForEachConfirmationInteraction(question_generator=generator)
        >>> async for token in interaction.generate_question_stream(
        ...     context={
        ...         "steps": [{"tool_name": "send_email_tool", "for_each_max": 10}],
        ...         "total_affected": 10,
        ...     },
        ...     user_language="fr",
        ... ):
        ...     print(token, end="", flush=True)
    """

    def __init__(self, question_generator: HitlQuestionGenerator) -> None:
        """
        Initialize ForEachConfirmationInteraction.

        Args:
            question_generator: HitlQuestionGenerator instance for LLM calls
        """
        self._question_generator = question_generator

    @property
    def interaction_type(self) -> HitlInteractionType:
        """Get the interaction type."""
        return HitlInteractionType.FOR_EACH_CONFIRMATION

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        tracker: BaseCallbackHandler | None = None,
    ) -> AsyncGenerator[str]:
        """
        Generate for_each confirmation question via streaming.

        Creates a clear confirmation message about the iteration scope
        and the type of mutation that will be applied.

        Args:
            context: Dict with:
                - steps: List of for_each steps requiring confirmation
                - total_affected: Total number of items to be affected
                - plan_id: Plan identifier
            user_language: Language code (fr, en, es, de, it, zh-CN)
            user_timezone: User's IANA timezone
            tracker: Optional TokenTrackingCallback

        Yields:
            str: Tokens of the confirmation message

        Performance:
            - TTFT target: < 100ms (mostly static content)
            - Total duration: < 500ms
        """
        from src.infrastructure.observability.metrics_agents import (
            hitl_question_ttft_seconds,
        )

        steps = context.get("steps", [])
        total_affected = context.get("total_affected", 0)
        plan_id = context.get("plan_id", "unknown")
        # FIX 2026-01-30: Get item_previews for "Informed HITL"
        item_previews = context.get("item_previews", [])

        logger.debug(
            "for_each_confirmation_question_started",
            plan_id=plan_id,
            steps_count=len(steps),
            total_affected=total_affected,
            user_language=user_language,
            item_previews_count=len(item_previews),
        )

        start_time = time.time()

        # Build the confirmation message with item previews
        message = self._build_confirmation_message(
            steps=steps,
            total_affected=total_affected,
            user_language=user_language,
            user_timezone=user_timezone,
            item_previews=item_previews,
        )

        # Stream token by token, its lines and no-break spaces kept
        for token_index, token in enumerate(text_tokens(message)):
            if token_index == 0:
                ttft = time.time() - start_time
                hitl_question_ttft_seconds.labels(type="for_each_confirmation").observe(ttft)
            yield token

        logger.debug(
            "for_each_confirmation_question_complete",
            plan_id=plan_id,
            total_affected=total_affected,
            duration_ms=int((time.time() - start_time) * 1000),
        )

    @staticmethod
    def _items_suffix(translations: dict[str, str], count: int) -> str:
        """Pick the grammatical number for an item count.

        Args:
            translations: FOR_EACH confirm UI strings for the user's language.
            count: The exact count being displayed next to the suffix.

        Returns:
            The singular form for a count of one, the plural otherwise.
        """
        return translations["items_suffix_one" if count == 1 else "items_suffix"]

    def _build_confirmation_message(
        self,
        steps: list[dict[str, Any]],
        total_affected: int,
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        item_previews: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Build structured confirmation message for for_each operation.

        Args:
            steps: List of for_each steps
            total_affected: Total items affected
            user_language: Language code
            user_timezone: User's IANA timezone for datetime formatting
            item_previews: Optional list of item preview dicts for "Informed HITL"

        Returns:
            Formatted confirmation message
        """
        translations = self._get_translations(user_language)

        # Header
        header = f"⚠️ **{translations['title']}**\n\n"

        # Detect mutation type from first step
        mutation_type = self._detect_mutation_type(steps, user_language)

        # Build body — a count of one reads in the singular ("1 élément",
        # never "1 éléments"; prod 2026-08-17).
        body = (
            f"{translations['operation_prefix']} {mutation_type} "
            f"**{total_affected}** {self._items_suffix(translations, total_affected)}.\n\n"
        )

        # FIX 2026-01-30: Add item previews section for "Informed HITL"
        # Shows users exactly what items will be affected
        if item_previews:
            body += self._build_item_previews_section(
                item_previews=item_previews,
                total_affected=total_affected,
                translations=translations,
                user_language=user_language,
                user_timezone=user_timezone,
                steps=steps,
            )

        # Add step details if multiple
        if len(steps) > 1:
            separator = label_separator(user_language)
            body += f"**{translations['operations_header']}{separator.rstrip()}**\n"
            for step in steps[:5]:  # Max 5 steps displayed
                # A tool's name may be a third party's (an MCP server's): data.
                tool_name = markdown_data_literal(
                    spell_unseen(one_line(str(step.get("tool_name") or "?")))
                )
                # `item_count` is the MEASURED count, stamped by the
                # orchestrator after pre-execution (ADR-185: a count shown is
                # a claim — exact, or absent); for_each_max is only the cap,
                # kept as fallback for steps that never got a measurement.
                count = step.get("item_count", step.get("for_each_max", 0))
                body += (
                    f"- {tool_name}{separator}{count} {self._items_suffix(translations, count)}\n"
                )
            if len(steps) > 5:
                body += f"- {translations['and_more'].format(count=len(steps) - 5)}\n"
            body += "\n"

        # Confirmation question
        body += f"**{translations['confirm_question']}**"

        return header + body

    def _build_item_previews_section(
        self,
        item_previews: list[dict[str, Any]],
        total_affected: int,
        translations: dict[str, str],
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        steps: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Build the item previews section for "Informed HITL".

        Uses the unified rendering helper :func:`format_hitl_item_preview`
        (ADR-085) whenever the steps' tool name can be resolved to a known
        ``DraftType``. For non-draft domains (places, weather, routes, etc.)
        or unresolvable tool names, falls back to the legacy generic
        rendering that joins preview-dict values with a localized connector.

        Args:
            item_previews: List of preview dicts with key fields per item.
            total_affected: Total number of items targeted by the operation.
            translations: Localized UI strings for the FOR_EACH dialog.
            user_language: The reader's language — the rows' nouns, dates and
                label punctuation.
            user_timezone: User's IANA timezone for date formatting.
            steps: Optional FOR_EACH step descriptors — used to synthesize a
                ``DraftType`` candidate from the first step's ``tool_name``.

        Returns:
            Formatted previews section string.
        """
        section = f"**{translations['affected_items']}{label_separator(user_language).rstrip()}**\n"

        # Try to resolve the operation to a known DraftType so the unified
        # registry-driven renderer applies. Returns ``None`` when the tool
        # name does not map to a draft (e.g. for places/weather queries).
        draft_type_candidate = self._steps_to_draft_type(steps or [])

        # Show ALL items - no artificial limit since API already bounds results
        for preview in item_previews:
            row: str | None = None

            # Preferred path: unified registry-driven rendering.
            if draft_type_candidate:
                row = format_hitl_item_preview(
                    draft_type=draft_type_candidate,
                    content=preview,
                    language=user_language,
                    user_timezone=user_timezone,
                )

            # Fallback path: legacy generic rendering for non-draft domains.
            if row is None:
                preview_parts: list[str] = []
                for _key, value in preview.items():
                    if value is None:
                        continue
                    str_value = one_line(str(value))
                    # Format ISO datetime strings for display.
                    str_value = format_value_if_iso_datetime(
                        str_value,
                        user_timezone=user_timezone,
                        locale=user_language,
                        include_time=True,
                        include_day_name=False,
                    )
                    # The item's own data, on a Markdown row: drawn as itself,
                    # spelled before it is cut so the bound holds.
                    clipped = clip_spelled(str_value, _PREVIEW_VALUE_MAX_CHARS)
                    preview_parts.append(markdown_data_literal(clipped))

                if not preview_parts:
                    continue

                if len(preview_parts) >= 2:
                    # Every language declares its connector (Chinese: none).
                    connector = translations["item_date_connector"]
                    if connector:
                        row = f"{preview_parts[0]} {connector} {preview_parts[1]}"
                    else:
                        row = f"{preview_parts[0]} {preview_parts[1]}"
                else:
                    row = preview_parts[0]

            section += f"- {row}\n"

        # Show "and N more" only if total_affected > previews received
        # (can happen if provider returns more items than extracted previews)
        remaining = total_affected - len(item_previews)
        if remaining > 0:
            and_more_text = translations["and_more"]
            section += f"- *{and_more_text.format(count=remaining)}*\n"

        section += "\n"
        return section

    @staticmethod
    def _steps_to_draft_type(steps: list[dict[str, Any]]) -> str | None:
        """Synthesize a ``DraftType``-compatible string from FOR_EACH steps.

        Inspects the first step's ``tool_name`` to identify a target domain
        (reminder / email / event / contact / task / file / label) and a
        mutation verb (delete / send / create / update). The combination is
        mapped to the canonical ``DraftType`` string consumed by the draft
        display registry (ADR-085).

        Mapping rules:
            - ``cancel_reminder`` → ``"reminder_delete"``
            - ``delete_event`` / ``remove_event`` → ``"event_delete"``
            - ``update_contact`` / ``modify_contact`` → ``"contact_update"``
            - ``send_email`` → ``"email"`` (DraftType.EMAIL has no suffix)
            - ``create_event`` → ``"event"`` (base DraftType)
            - Unrecognized tool name → ``None`` (caller falls back).

        Args:
            steps: FOR_EACH step descriptors. Only the first is inspected
                — a FOR_EACH executes a single tool per iteration.

        Returns:
            A draft-type string accepted by
            :func:`src.domains.agents.drafts.display.get_draft_display_config`,
            or ``None`` when no mapping can be inferred.
        """
        if not steps:
            return None

        tool_name = str(steps[0].get("tool_name", "")).lower()
        if not tool_name:
            return None

        domain = next(
            (
                d
                for d in ("reminder", "email", "event", "contact", "task", "file", "label")
                if d in tool_name
            ),
            None,
        )
        if domain is None:
            return None

        if any(v in tool_name for v in ("delete", "cancel", "remove", "trash")):
            return f"{domain}_delete"
        if any(v in tool_name for v in ("update", "modify", "edit")):
            return f"{domain}_update"
        if any(v in tool_name for v in ("reply",)) and domain == "email":
            return "email_reply"
        if any(v in tool_name for v in ("forward",)) and domain == "email":
            return "email_forward"
        # Default for send / create / unknown verbs → base DraftType (e.g. "email", "event")
        return domain

    def _detect_mutation_type(
        self,
        steps: list[dict[str, Any]],
        user_language: str,
    ) -> str:
        """
        Detect mutation type from tool names.

        Args:
            steps: List of for_each steps
            user_language: Language code

        Returns:
            Localized mutation verb
        """
        translations = self._get_translations(user_language)

        if not steps:
            return translations["mutation_default"]

        tool_name = steps[0].get("tool_name", "").lower()

        if "send" in tool_name:
            return translations["mutation_send"]
        if "create" in tool_name:
            return translations["mutation_create"]
        if "update" in tool_name or "modify" in tool_name:
            return translations["mutation_update"]
        if "delete" in tool_name or "remove" in tool_name:
            return translations["mutation_delete"]

        return translations["mutation_default"]

    def _get_translations(self, user_language: str) -> dict[str, str]:
        """Get UI translations for the specified language using centralized i18n."""
        return HitlMessages.get_for_each_confirm_translations(user_language)

    def build_metadata_chunk(
        self,
        context: dict[str, Any],
        message_id: str,
        conversation_id: str,
        registry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Build metadata for the for_each confirmation HITL chunk.

        Uses WARNING severity for UI styling.

        Args:
            context: Dict with steps and total_affected
            message_id: Unique message ID
            conversation_id: Conversation UUID string
            registry_ids: Registry IDs for affected items (optional)

        Returns:
            Metadata dict for hitl_interrupt_metadata chunk
        """
        steps = context.get("steps", [])
        total_affected = context.get("total_affected", 0)
        plan_id = context.get("plan_id", "unknown")
        # FIX 2026-01-30: Include item_previews for frontend display
        item_previews = context.get("item_previews", [])

        if registry_ids is None:
            registry_ids = context.get("registry_ids", [])

        # Build action_requests
        action_requests = [
            {
                "type": "for_each_confirmation",
                "plan_id": plan_id,
                "steps": steps,
                "total_affected": total_affected,
                "available_actions": [
                    {"action": "confirm", "label": "Confirm", "style": "primary"},
                    {"action": "cancel", "label": "Cancel", "style": "secondary"},
                ],
                "registry_ids": registry_ids,
                "item_previews": item_previews,
            }
        ]

        return {
            "message_id": message_id,
            FIELD_CONVERSATION_ID: conversation_id,
            "action_requests": action_requests,
            "count": 1,
            "is_plan_approval": False,
            # ForEach-specific metadata
            "plan_id": plan_id,
            "total_affected": total_affected,
            "steps_count": len(steps),
            "severity": HitlSeverity.WARNING.value,
            "registry_ids": registry_ids,
            "has_registry_items": len(registry_ids) > 0,
            "item_previews": item_previews,
        }

    def get_fallback_question(self, user_language: str) -> str:
        """
        Get fallback question for error scenarios using centralized i18n_hitl.

        Args:
            user_language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Static fallback question string
        """
        return "⚠️ " + HitlMessages.get_fallback(
            HitlMessageType.FOR_EACH_CONFIRMATION, user_language
        )
