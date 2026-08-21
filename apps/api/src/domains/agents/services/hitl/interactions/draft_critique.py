"""
Draft Critique Interaction - HITL streaming for draft review before execution.

This module implements HitlInteractionProtocol for draft_critique type.
It provides true LLM streaming for draft review questions when users create
drafts (emails, events, contacts) that require confirmation before execution.

Features:
    - True LLM token streaming via astream()
    - Fallback to static question on error
    - Multi-language support (fr, en, es, de, it, zh-CN) via i18n_hitl
    - Draft type awareness (email, event, contact)
    - Data Registry integration: registry_ids for draft card rendering
    - Three action options: confirm, edit, cancel

Data Registry LOT 4.3 Integration:
    Draft critique is the final piece of the Command API flow:
    1. Tool creates draft via DraftService.create_*_draft()
    2. Draft stored in registry with type=DRAFT
    3. LIAToolNode detects requires_confirmation=True
    4. DraftCritiqueInteraction generates review question
    5. User chooses: confirm → execute, edit → replan, cancel → abort

Architecture:
    LIAToolNode detects draft → triggers __interrupt__
    → StreamingService creates DraftCritiqueInteraction via Registry
    → Streams review question with draft options
    → User response → DraftService.process_draft_action()

References:
    - protocols.py: HitlInteractionProtocol definition
    - registry.py: Registration decorator
    - lars/command_api.py: Draft creation and processing
    - lars/models/commands.py: Draft, DraftType, DraftAction
    - Data Registry LOT 4: HITL Integration docs

Created: 2025-11-26
Data Registry LOT 4.3: Draft/Critique Flow
Updated: 2025-12-06 (i18n centralization - 6 languages support)
"""

import json
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.field_names import FIELD_CONTENT, FIELD_CONVERSATION_ID
from src.core.i18n_drafts import format_hitl_item_preview
from src.core.i18n_hitl import HitlMessages, HitlMessageType
from src.core.time_utils import format_value_if_datetime_string
from src.domains.agents.drafts.display import get_draft_display_config
from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.prompts import format_with_current_datetime
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.logging import get_logger

from ..protocols import HitlInteractionType
from ..registry import HitlInteractionRegistry
from .draft_fallback_summary import build_fallback_critique

if TYPE_CHECKING:
    from ..question_generator import HitlQuestionGenerator

logger = get_logger(__name__)


async def _with_markdown_hard_breaks(
    stream: AsyncGenerator[str],
) -> AsyncGenerator[str]:
    """Convert single newlines of a token stream into explicit ``<br/>`` breaks.

    The critique question is rendered as markdown, where a bare ``\\n`` is a
    SOFT wrap — consecutive field lines end up glued on one line. Paragraph
    breaks (``\\n\\n`` runs) are preserved, and a line already ending with a
    ``<br>``/``<br/>`` tag is not doubled. Stream-safe: a trailing newline run
    is held back until the following chunk resolves whether it is a single
    break or a paragraph.
    """
    pending = ""
    # Tail of the text emitted so far: the already-a-break guard must also see
    # a "<br>" whose newline arrived in the NEXT chunk (token streams split
    # anywhere), not just the current segment.
    emitted_tail = ""
    async for chunk in stream:
        if not chunk:
            continue
        pending += chunk
        while True:
            i = pending.find("\n")
            if i == -1:
                yield pending
                emitted_tail = (emitted_tail + pending)[-8:]
                pending = ""
                break
            j = i
            while j < len(pending) and pending[j] == "\n":
                j += 1
            if j == len(pending):
                # Newline run touches the buffer end — unresolved, wait for more.
                if i > 0:
                    yield pending[:i]
                    emitted_tail = (emitted_tail + pending[:i])[-8:]
                    pending = pending[i:]
                break
            head, run = pending[:i], j - i
            already_break = (emitted_tail + head).rstrip().endswith(("<br>", "<br/>"))
            out = head + ("<br/>\n" if run == 1 and not already_break else "\n" * run)
            yield out
            emitted_tail = (emitted_tail + out)[-8:]
            pending = pending[j:]
    if pending:
        # Trailing text (possibly ending in newlines) — emit verbatim.
        yield pending


@HitlInteractionRegistry.register(HitlInteractionType.DRAFT_CRITIQUE)
class DraftCritiqueInteraction:
    """
    HITL interaction implementation for draft review before execution.

    Generates contextual review questions for drafts (emails, events, contacts)
    using LLM streaming. Presents three options: confirm, edit, cancel.

    This is the HITL integration point for the Draft Service.
    When a tool creates a draft via DraftService, the LIAToolNode detects
    requires_confirmation=True and triggers this interaction.

    Attributes:
        question_generator: HitlQuestionGenerator instance for LLM calls

    Example:
        >>> generator = HitlQuestionGenerator()
        >>> interaction = DraftCritiqueInteraction(question_generator=generator)
        >>> async for token in interaction.generate_question_stream(
        ...     context={
        ...         "draft_type": "email",
        ...         "draft_content": {"to": "jean@example.com", "subject": "RDV"},
        ...         "draft_id": "draft_abc123",
        ...     },
        ...     user_language="fr",
        ... ):
        ...     print(token, end="", flush=True)

    See Also:
        - HitlInteractionProtocol: Contract this class implements
        - DraftService: Creates drafts requiring confirmation
        - LIAToolNode: Triggers interrupt for drafts
    """

    def __init__(self, question_generator: HitlQuestionGenerator) -> None:
        """
        Initialize DraftCritiqueInteraction.

        Args:
            question_generator: HitlQuestionGenerator instance for LLM calls
        """
        self._question_generator = question_generator

    @property
    def interaction_type(self) -> HitlInteractionType:
        """Get the interaction type."""
        return HitlInteractionType.DRAFT_CRITIQUE

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        tracker: Any | None = None,
    ) -> AsyncGenerator[str]:
        """
        Generate draft review question via LLM streaming.

        Extracts draft_type, draft_content, and draft_id from context,
        then streams the review question token by token.

        Args:
            context: Interrupt context with:
                - draft_type: Type of draft (email, event, contact)
                - draft_content: Draft content dict
                - draft_id: Unique draft ID
                - draft_summary: Optional pre-generated summary
            user_language: Language code (fr, en, es)
            user_timezone: User's IANA timezone for datetime context
            tracker: Optional TokenTrackingCallback

        Yields:
            str: Individual tokens from LLM

        Raises:
            Exception: If LLM streaming fails (caught by caller)

        Performance:
            - TTFT target: < 400ms
            - Total duration: 1-2 seconds
        """
        # Import metrics locally to avoid circular imports
        from src.infrastructure.observability.metrics_agents import (
            hitl_question_tokens_per_second,
            hitl_question_ttft_seconds,
            registry_draft_critique_questions_total,
        )

        # Extract data from context
        draft_type = context.get("draft_type", "unknown")
        draft_content = context.get("draft_content", {})
        draft_id = context.get("draft_id", "unknown")
        draft_summary = context.get("draft_summary")  # Pre-generated summary if available
        batch_total = context.get("batch_total", 1)  # >1 if part of FOR_EACH batch
        batch_drafts = context.get("batch_drafts", [])  # All draft contents for batch
        # Clarify follow-up (replay-safe EDIT loop): a previous "clarify"
        # decision persisted its question — surface IT instead of the generic
        # critique question, so the user knows what to specify.
        clarification_question = context.get("clarification_question")

        # Track metric
        registry_draft_critique_questions_total.labels(draft_type=draft_type).inc()

        logger.info(
            "draft_critique_question_streaming_started",
            draft_type=draft_type,
            draft_id=draft_id,
            content_keys=list(draft_content.keys()),
            user_language=user_language,
            batch_total=batch_total,
            has_clarification_question=bool(clarification_question),
        )

        # Clarify path: stream the persisted clarification question verbatim
        # (static — no LLM call; the draft card itself is re-rendered via
        # registry_ids alongside this question).
        if clarification_question:
            start_time = time.time()
            for i, word in enumerate(str(clarification_question).split()):
                if i == 0:
                    ttft = time.time() - start_time
                    hitl_question_ttft_seconds.labels(type="draft_critique").observe(ttft)
                yield word + " "
            logger.info(
                "draft_critique_clarification_question_streamed",
                draft_id=draft_id,
                question_length=len(clarification_question),
            )
            return

        # Batch path: generate static confirmation listing ALL items (no LLM needed)
        if batch_total > 1 and batch_drafts:
            start_time = time.time()
            batch_message = self._generate_batch_critique(
                draft_type=draft_type,
                batch_drafts=batch_drafts,
                batch_total=batch_total,
                user_language=user_language,
                user_timezone=user_timezone,
            )
            # Stream line-by-line then word-by-word (preserves markdown newlines)
            # Pattern from for_each_confirmation.py
            token_index = 0
            for line in batch_message.split("\n"):
                if line:
                    for word in line.split():
                        if token_index == 0:
                            ttft = time.time() - start_time
                            hitl_question_ttft_seconds.labels(type="draft_critique").observe(ttft)
                        token_index += 1
                        yield word + " "
                yield "\n"
            logger.info(
                "draft_critique_batch_question_generated",
                draft_id=draft_id,
                batch_total=batch_total,
                duration_ms=int((time.time() - start_time) * 1000),
            )
            return

        # If we have a pre-generated summary, use it directly
        if draft_summary:
            start_time = time.time()
            token_count = 0

            # Stream the summary word by word
            formatted = self._format_critique_question(
                draft_type=draft_type,
                summary=draft_summary,
                user_language=user_language,
            )

            words = formatted.split()
            for i, word in enumerate(words):
                if i == 0:
                    ttft = time.time() - start_time
                    hitl_question_ttft_seconds.labels(type="draft_critique").observe(ttft)

                token_count += 1
                yield word + " "

            # Track metrics
            total_duration = time.time() - start_time
            if total_duration > 0:
                tokens_per_second = token_count / total_duration
                hitl_question_tokens_per_second.labels(type="draft_critique").observe(
                    tokens_per_second
                )

            logger.info(
                "draft_critique_question_streaming_complete_from_summary",
                draft_id=draft_id,
                token_count=token_count,
                duration_seconds=total_duration,
            )
            return

        # Otherwise, generate via LLM
        start_time = time.time()
        first_token_received = False
        token_count = 0

        try:
            llm_stream = self._generate_critique_via_llm(
                draft_type=draft_type,
                draft_content=draft_content,
                user_language=user_language,
                user_timezone=user_timezone,
                batch_total=batch_total,
                tracker=tracker,
            )
            # Deterministic layout: the renderer soft-wraps single newlines
            # (fields glued on one line) and the LLM does not reliably emit the
            # template's <br> tags — normalize in-stream instead of trusting it.
            async for token in _with_markdown_hard_breaks(llm_stream):
                # Track TTFT on first token
                if not first_token_received:
                    ttft = time.time() - start_time
                    hitl_question_ttft_seconds.labels(type="draft_critique").observe(ttft)
                    first_token_received = True
                    logger.debug(
                        "draft_critique_question_first_token",
                        ttft_seconds=ttft,
                        draft_id=draft_id,
                    )

                token_count += 1
                yield token

            # Track completion metrics
            total_duration = time.time() - start_time
            if total_duration > 0:
                tokens_per_second = token_count / total_duration
                hitl_question_tokens_per_second.labels(type="draft_critique").observe(
                    tokens_per_second
                )

            logger.info(
                "draft_critique_question_streaming_complete",
                draft_id=draft_id,
                draft_type=draft_type,
                token_count=token_count,
                duration_seconds=total_duration,
            )

        except Exception as e:
            logger.warning(
                "draft_critique_llm_failed_using_fallback",
                draft_id=draft_id,
                error=str(e),
            )
            # Yield fallback (preserve newlines for markdown)
            fallback = self._generate_fallback_critique(
                draft_type=draft_type,
                draft_content=draft_content,
                user_language=user_language,
                user_timezone=user_timezone,
            )
            for line in fallback.split("\n"):
                if line:
                    for word in line.split():
                        yield word + " "
                yield "\n"

    async def _generate_critique_via_llm(
        self,
        draft_type: str,
        draft_content: dict[str, Any],
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        batch_total: int = 1,
        tracker: Any | None = None,
    ) -> AsyncGenerator[str]:
        """
        Generate critique question via LLM streaming.

        Args:
            draft_type: Type of draft
            draft_content: Draft content dict
            user_language: Language code
            user_timezone: User's IANA timezone for date conversion
            batch_total: Total items in batch (>1 means FOR_EACH batch)
            tracker: Optional callback tracker

        Yields:
            str: Tokens from LLM
        """
        # Build prompt for LLM
        prompt = self._build_critique_prompt(
            draft_type,
            draft_content,
            user_language,
            user_timezone=user_timezone,
            batch_total=batch_total,
        )

        # Use question generator's LLM
        from src.infrastructure.llm.instrumentation import create_instrumented_config
        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

        config = create_instrumented_config(
            llm_type="hitl_question_generator",
            tags=["hitl", "draft_critique", "lars"],
            metadata={
                "draft_type": draft_type,
                "user_language": user_language,
                "content_keys": list(draft_content.keys()),
            },
        )

        # Merge tracker if provided
        if tracker:
            from langchain_core.callbacks.base import BaseCallbackHandler

            if isinstance(tracker, BaseCallbackHandler):
                existing_callbacks = config.get("callbacks", [])
                config["callbacks"] = existing_callbacks + [tracker]

        config = enrich_config_with_node_metadata(config, "hitl_draft_critique")

        # Stream from LLM
        async for chunk in self._question_generator.tool_question_llm.astream(
            prompt, config=config
        ):
            # Gemini 3.x streams list[dict] content blocks; normalize to text.
            content = coerce_content_to_text(chunk.content)
            yield content

    def _build_critique_prompt(
        self,
        draft_type: str,
        draft_content: dict[str, Any],
        user_language: str,
        personality_instruction: str | None = None,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        batch_total: int = 1,
    ) -> list[dict[str, str]]:
        """
        Build prompt for draft critique question generation.

        Args:
            draft_type: Type of draft (email, event, contact)
            draft_content: Draft content dict
            user_language: Target language
            personality_instruction: Optional LLM personality instruction
            user_timezone: User's IANA timezone for date conversion
            batch_total: Total items in batch (>1 means FOR_EACH batch)

        Returns:
            List of message dicts for LLM invocation
        """
        from src.domains.agents.prompts import load_prompt

        # Get default personality in user's language if none provided (i18n)
        default_personality = HitlMessages.get_default_personality(user_language)

        # Load critique prompt
        try:
            system_prompt = format_with_current_datetime(
                load_prompt("hitl_draft_critique_prompt", version="v1"),
                user_timezone=user_timezone,
                user_language=user_language,
            )
        except Exception:
            # Fallback to inline prompt if file not found
            system_prompt = self._get_inline_system_prompt()

        # Inject user_language and personality into system prompt
        system_prompt = system_prompt.replace("{user_language}", user_language).replace(
            "{personnalite}", personality_instruction or default_personality
        )

        # Inject localized two-block labels for UPDATE templates.
        # The LLM renders these verbatim, replacing any legacy "unchanged" framing.
        update_labels = HitlMessages.get_draft_update_labels(user_language)
        system_prompt = system_prompt.replace(
            "{L_Modifications}", update_labels["modifications"]
        ).replace("{L_Full_post_update}", update_labels["full_post_update"])

        # Pre-convert datetime values to user's local timezone for display
        # This ensures the LLM receives human-readable local dates instead of raw UTC
        display_content = self._preconvert_dates_for_display(
            draft_content, user_timezone, user_language
        )

        # Serialize content for LLM
        content_json = json.dumps(display_content, indent=2, ensure_ascii=False)

        # Batch context: tell the LLM this action applies to N items total
        batch_context = ""
        if batch_total > 1:
            batch_context = f"\nBatchTotal: {batch_total} (this action will apply to {batch_total} items total — mention this in the confirmation question)"

        user = f"""DraftType: {draft_type}
Content: {content_json}{batch_context}

Generate the review question:"""

        return [
            {"role": "system", FIELD_CONTENT: system_prompt},
            {"role": "user", FIELD_CONTENT: user},
        ]

    def _get_inline_system_prompt(self) -> str:
        """Get inline system prompt as fallback from external file."""
        from src.domains.agents.prompts import load_prompt

        return load_prompt("hitl_draft_critique_fallback_prompt")

    def _format_critique_question(
        self,
        draft_type: str,
        summary: str,
        user_language: str,
    ) -> str:
        """
        Format a critique question with the summary and actions.

        Args:
            draft_type: Type of draft
            summary: Pre-generated summary
            user_language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Formatted question string
        """
        emoji = HitlMessages.get_draft_emoji(draft_type)
        actions = HitlMessages.format_draft_critique_actions(
            user_language, include_descriptions=True
        )

        return f"{emoji} {summary}<br/>{actions}"

    def _generate_fallback_critique(
        self,
        draft_type: str,
        draft_content: dict[str, Any],
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    ) -> str:
        """Generate the critique shown when the LLM produced nothing.

        Delegates to :func:`build_fallback_critique` — see that module for the
        per-draft-type ladder and the reason it lives outside this class.
        """
        return build_fallback_critique(draft_type, draft_content, user_language, user_timezone)

    def _generate_batch_critique(
        self,
        draft_type: str,
        batch_drafts: list[dict[str, Any]],
        batch_total: int,
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    ) -> str:
        """
        Generate static batch confirmation message listing all items.

        Used when FOR_EACH produces multiple drafts. Shows each item with
        its key details in a bullet list, with a batch-level confirmation question.
        No LLM needed — deterministic, fast, and predictable.

        Args:
            draft_type: Type of all drafts in batch (e.g., "email_delete")
            batch_drafts: List of all draft dicts (model_dump of PendingDraftInfo)
            batch_total: Total number of items
            user_language: Language code for localization
            user_timezone: User's IANA timezone for date formatting

        Returns:
            Formatted batch confirmation message
        """

        # Destructive (delete) batches keep the irreversible-delete warning and
        # the "confirm deletion?" question. Non-destructive batches (send /
        # create / update / reply / forward) MUST NOT inherit that deletion
        # wording — the draft display registry (ADR-085) is the single source of
        # truth for a draft type's mutation nature (verb_past_key == "deleted").
        cfg = get_draft_display_config(draft_type)
        is_destructive = cfg is not None and cfg.verb_past_key == "deleted"

        destructive_ui = HitlMessages.get_destructive_confirm_translations(user_language)
        specific_title = HitlMessages.get_destructive_confirm_title(draft_type, user_language)

        # Header with action-specific title (e.g., "Confirmation d'envoi").
        header = f"⚠️ **{specific_title}**\n\n"

        # Build item list — unified rendering via the draft display registry
        # (ADR-085). Send-type rows include the recipient:
        # "{emoji} {Noun}[ à {recipient}] : {label}[ - {date_with_day}]".
        items_section = f"**{destructive_ui['affected_items']} :**\n"
        for draft_data in batch_drafts:
            content = draft_data.get("draft_content", {})
            row = format_hitl_item_preview(
                draft_type=draft_type,
                content=content,
                language=user_language,
                user_timezone=user_timezone,
            )
            if row is None:
                # Defensive fallback for unknown draft types. Startup assertion
                # (assert_registry_completeness) makes this unreachable for
                # registered DraftType values, but the chain mirrors the field
                # priority of the legacy renderer to preserve behavior if the
                # invariant is ever broken at runtime.
                emoji = HitlMessages.get_draft_emoji(draft_type)
                label = (
                    content.get("subject")
                    or content.get("summary")
                    or content.get("title")
                    or content.get("name")
                    or content.get("content")
                    or content.get("label_name")
                    or "?"
                )
                row = f"{emoji} {label}".strip()
            items_section += f"- {row}\n"

        items_section += "\n"

        # Warning + question — action-appropriate. Deletes get the strong
        # irreversible warning + the deletion question; other mutations get NO
        # irreversible-delete warning and the neutral FOR_EACH confirmation
        # question (localized, consistent with the pipeline FOR_EACH
        # send/create/update flow).
        if is_destructive:
            warning = f"⚠️ {destructive_ui['default_warning']}\n\n"
            question = f"**{destructive_ui['confirm_question']}**"
        else:
            for_each_ui = HitlMessages.get_for_each_confirm_translations(user_language)
            warning = ""
            question = f"**{for_each_ui['confirm_question']}**"

        return header + items_section + warning + question

    @staticmethod
    def _preconvert_dates_for_display(
        draft_content: dict[str, Any],
        user_timezone: str,
        user_language: str,
    ) -> dict[str, Any]:
        """
        Pre-convert datetime values in draft_content for human display.

        Recursively walks the draft_content dict and converts any datetime
        string (ISO 8601 or RFC 2822) to the user's local timezone format.
        This ensures the LLM receives human-readable local dates instead of
        raw UTC strings.

        Args:
            draft_content: Draft content dict (not modified in-place)
            user_timezone: User's IANA timezone (e.g., "Europe/Paris")
            user_language: User's locale for formatting (e.g., "fr")

        Returns:
            New dict with datetime values converted to display format
        """
        # Fields known to contain datetime values across draft types
        datetime_fields = {
            "date",  # email Date header (RFC 2822)
            "start_datetime",  # event start
            "end_datetime",  # event end
            "due",  # task due date
            "start",  # event start (alternative key)
            "end",  # event end (alternative key)
            "created",  # creation date
            "updated",  # update date
            "completed",  # task completion date
            "dateTime",  # Google Calendar API format
        }

        def _convert_value(key: str, value: Any) -> Any:
            if isinstance(value, str) and key in datetime_fields:
                converted = format_value_if_datetime_string(
                    value,
                    user_timezone=user_timezone,
                    locale=user_language,
                    include_time=True,
                    include_day_name=True,
                )
                return converted
            elif isinstance(value, dict):
                return {k: _convert_value(k, v) for k, v in value.items()}
            elif isinstance(value, list):
                return [
                    (
                        {k: _convert_value(k, v) for k, v in item.items()}
                        if isinstance(item, dict)
                        else item
                    )
                    for item in value
                ]
            return value

        return {k: _convert_value(k, v) for k, v in draft_content.items()}

    def build_metadata_chunk(
        self,
        context: dict[str, Any],
        message_id: str,
        conversation_id: str,
        registry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Build metadata for the initial HITL chunk.

        Creates metadata dict with draft critique specific fields.

        Data Registry LOT 4.3 Integration:
            The registry_ids should include the draft_id so frontend
            can render the draft card alongside the critique question.
            Frontend displays <LARSCard> for the draft with edit capability.

        Args:
            context: Interrupt context with draft_type, draft_content, draft_id
            message_id: Unique message ID
            conversation_id: Conversation UUID string
            registry_ids: data registry IDs (should include draft_id)

        Returns:
            Metadata dict for hitl_interrupt_metadata chunk with:
                - action_requests: Draft critique action with options
                - registry_ids: Registry IDs (including draft)
                - draft_type: Type of draft
                - draft_id: Draft identifier
                - available_actions: List of valid actions
        """
        draft_type = context.get("draft_type", "unknown")
        draft_content = context.get("draft_content", {})
        draft_id = context.get("draft_id", "unknown")

        # Data Registry LOT 4.3: Extract registry_ids from context if not explicitly provided
        # Should include the draft itself for rendering
        if registry_ids is None:
            registry_ids = context.get("registry_ids", [])

        # Ensure draft_id is in registry_ids
        if draft_id and draft_id not in registry_ids:
            registry_ids = [draft_id] + list(registry_ids)

        # Build action_requests in expected format
        # Include available actions for frontend button rendering
        available_actions = [
            {
                "action": DraftAction.CONFIRM.value,
                "label": "confirm",
                "style": "primary",
            },
            {
                "action": DraftAction.EDIT.value,
                "label": "edit",
                "style": "secondary",
            },
            {
                "action": DraftAction.CANCEL.value,
                "label": "cancel",
                "style": "destructive",
            },
        ]

        action_requests = [
            {
                "type": "draft_critique",
                "draft_type": draft_type,
                "draft_id": draft_id,
                "draft_content": draft_content,
                "available_actions": available_actions,
                # Data Registry LOT 4: Include registry_ids in action_request
                "registry_ids": registry_ids,
            }
        ]

        return {
            "message_id": message_id,
            FIELD_CONVERSATION_ID: conversation_id,
            "action_requests": action_requests,
            "count": 1,
            "is_plan_approval": False,
            # Draft-specific metadata
            "draft_type": draft_type,
            "draft_id": draft_id,
            "available_actions": [a["action"] for a in available_actions],
            # Data Registry LOT 4: Registry IDs at top level for easy access
            "registry_ids": registry_ids,
            "has_registry_items": len(registry_ids) > 0,
        }

    def get_fallback_question(self, user_language: str) -> str:
        """
        Get fallback question for error scenarios.

        Returns a static, pre-defined question when LLM streaming fails.

        Args:
            user_language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Static fallback question string
        """
        return HitlMessages.get_fallback(HitlMessageType.DRAFT_CRITIQUE, user_language)
