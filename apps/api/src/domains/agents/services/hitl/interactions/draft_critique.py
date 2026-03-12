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

from src.core.field_names import FIELD_CONTENT, FIELD_CONVERSATION_ID
from src.core.i18n_hitl import HitlMessages, HitlMessageType
from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.prompts import format_with_current_datetime
from src.infrastructure.observability.logging import get_logger

from ..protocols import HitlInteractionType
from ..registry import HitlInteractionRegistry

if TYPE_CHECKING:
    from ..question_generator import HitlQuestionGenerator

logger = get_logger(__name__)


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

    def __init__(self, question_generator: "HitlQuestionGenerator") -> None:
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
        user_timezone: str = "Europe/Paris",
        tracker: Any | None = None,
    ) -> AsyncGenerator[str, None]:
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

        # Track metric
        registry_draft_critique_questions_total.labels(draft_type=draft_type).inc()

        logger.info(
            "draft_critique_question_streaming_started",
            draft_type=draft_type,
            draft_id=draft_id,
            content_keys=list(draft_content.keys()),
            user_language=user_language,
        )

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
            async for token in self._generate_critique_via_llm(
                draft_type=draft_type,
                draft_content=draft_content,
                user_language=user_language,
                tracker=tracker,
            ):
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
            # Yield fallback
            fallback = self._generate_fallback_critique(
                draft_type=draft_type,
                draft_content=draft_content,
                user_language=user_language,
                user_timezone=user_timezone,
            )
            for word in fallback.split():
                yield word + " "

    async def _generate_critique_via_llm(
        self,
        draft_type: str,
        draft_content: dict[str, Any],
        user_language: str,
        tracker: Any | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate critique question via LLM streaming.

        Args:
            draft_type: Type of draft
            draft_content: Draft content dict
            user_language: Language code
            tracker: Optional callback tracker

        Yields:
            str: Tokens from LLM
        """
        # Build prompt for LLM
        prompt = self._build_critique_prompt(draft_type, draft_content, user_language)

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
            content = chunk.content if chunk.content else ""
            yield content

    def _build_critique_prompt(
        self,
        draft_type: str,
        draft_content: dict[str, Any],
        user_language: str,
        personality_instruction: str | None = None,
    ) -> list[dict[str, str]]:
        """
        Build prompt for draft critique question generation.

        Args:
            draft_type: Type of draft (email, event, contact)
            draft_content: Draft content dict
            user_language: Target language
            personality_instruction: Optional LLM personality instruction

        Returns:
            List of message dicts for LLM invocation
        """
        from src.domains.agents.prompts import load_prompt

        # Get default personality in user's language if none provided (i18n)
        default_personality = HitlMessages.get_default_personality(user_language)

        # Load critique prompt
        try:
            system_prompt = format_with_current_datetime(
                load_prompt("hitl_draft_critique_prompt", version="v1")
            )
        except Exception:
            # Fallback to inline prompt if file not found
            system_prompt = self._get_inline_system_prompt()

        # Inject user_language and personality into system prompt
        system_prompt = system_prompt.replace("{user_language}", user_language).replace(
            "{personnalite}", personality_instruction or default_personality
        )

        # Serialize content for LLM
        content_json = json.dumps(draft_content, indent=2, ensure_ascii=False)

        user = f"""DraftType: {draft_type}
Content: {content_json}

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
        user_timezone: str = "Europe/Paris",
    ) -> str:
        """
        Generate fallback critique when LLM fails.

        Creates a simple summary from draft content without LLM.
        Uses centralized i18n_hitl translations for all 6 languages.

        Args:
            draft_type: Type of draft
            draft_content: Draft content dict
            user_language: Language code (fr, en, es, de, it, zh-CN)
            user_timezone: User's IANA timezone for datetime formatting

        Returns:
            Fallback critique question
        """
        from src.core.time_utils import format_datetime_for_display

        emoji = HitlMessages.get_draft_emoji(draft_type)

        # Extract variables based on draft type
        if draft_type == "email":
            to = draft_content.get("to", "?")
            subject = draft_content.get("subject", "?")
            summary = HitlMessages.get_draft_summary(
                draft_type, user_language, to=to, subject=subject
            )

        elif draft_type == "event":
            summary_text = draft_content.get("summary", "?")
            start = draft_content.get("start_datetime", "?")
            # Format datetime using user's timezone
            if isinstance(start, str) and "T" in start:
                start = format_datetime_for_display(
                    start, user_timezone, user_language, include_time=True
                )
            summary = HitlMessages.get_draft_summary(
                draft_type, user_language, summary=summary_text, start=start
            )

        elif draft_type == "event_update":
            summary_text = draft_content.get("summary") or draft_content.get(
                "current_event", {}
            ).get("summary", "?")
            summary = HitlMessages.get_draft_summary(
                draft_type, user_language, summary=summary_text
            )

        elif draft_type == "event_delete":
            event_data = draft_content.get("event", {})
            summary_text = event_data.get("summary", "?")
            summary = HitlMessages.get_draft_summary(
                draft_type, user_language, summary=summary_text
            )

        elif draft_type == "contact":
            name = draft_content.get("name", "?")
            email = draft_content.get("email", "")
            summary = HitlMessages.get_draft_summary(
                draft_type, user_language, name=name, email=email
            )

        elif draft_type == "contact_update":
            name = draft_content.get("name")
            if not name:
                current_contact = draft_content.get("current_contact", {})
                names = current_contact.get("names", [])
                name = names[0].get("displayName", "?") if names else "?"
            summary = HitlMessages.get_draft_summary(draft_type, user_language, name=name)

        elif draft_type == "contact_delete":
            contact = draft_content.get("contact", {})
            names = contact.get("names", [])
            name = names[0].get("displayName", "?") if names else "?"
            summary = HitlMessages.get_draft_summary(draft_type, user_language, name=name)

        elif draft_type == "task":
            title = draft_content.get("title", "?")
            summary = HitlMessages.get_draft_summary(draft_type, user_language, title=title)

        elif draft_type == "task_update":
            title = draft_content.get("title") or draft_content.get("current_task", {}).get(
                "title", "?"
            )
            summary = HitlMessages.get_draft_summary(draft_type, user_language, title=title)

        elif draft_type == "task_delete":
            title = draft_content.get("title", "?")
            summary = HitlMessages.get_draft_summary(draft_type, user_language, title=title)

        elif draft_type == "file_delete":
            file_data = draft_content.get("file", {})
            name = file_data.get("name", "?")
            summary = HitlMessages.get_draft_summary(draft_type, user_language, name=name)

        else:
            summary = HitlMessages.get_fallback(HitlMessageType.DRAFT_CRITIQUE, user_language)

        # Build action lines using centralized i18n
        actions = HitlMessages.format_draft_critique_actions(
            user_language, include_descriptions=False
        )

        return f"{emoji} {summary}<br/>{actions}"

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
