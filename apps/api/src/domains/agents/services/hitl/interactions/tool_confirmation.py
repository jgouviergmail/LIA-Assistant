"""
Tool Confirmation Interaction - HITL streaming for tool-level confirmation.

This module implements HitlInteractionProtocol for tool_confirmation type.
It provides true LLM streaming for tool confirmation questions.

Note: Tool-level HITL already has streaming support in question_generator.py
via generate_confirmation_question_stream(). This interaction wraps that
method to provide a consistent interface via the registry.

Features:
    - True LLM token streaming via astream()
    - Fallback to static question on error
    - Multi-language support (fr, en, es, de, it, zh-CN) via i18n_hitl
    - Parameter enrichment for user-friendly display
    - Data Registry integration: registry_ids for rich item rendering (LOT 4)

Data Registry LOT 4 Integration:
    When tools return StandardToolOutput with registry items, the
    registry_ids are included in HITL metadata. Frontend can then
    display <LARSCard> components alongside the confirmation question.

References:
    - protocols.py: HitlInteractionProtocol definition
    - registry.py: Registration decorator
    - question_generator.py: Existing streaming implementation
    - Data Registry LOT 4: HITL Integration docs

Created: 2025-11-25
Updated: 2025-11-26 (Data Registry LOT 4 - registry_ids support)
Updated: 2025-12-06 (i18n centralization - 6 languages support)
"""

import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.core.field_names import FIELD_CONVERSATION_ID
from src.core.i18n_hitl import HitlMessages, HitlMessageType
from src.infrastructure.observability.logging import get_logger

from ..protocols import HitlInteractionType
from ..registry import HitlInteractionRegistry

if TYPE_CHECKING:
    from ..question_generator import HitlQuestionGenerator

logger = get_logger(__name__)


@HitlInteractionRegistry.register(HitlInteractionType.TOOL_CONFIRMATION)
class ToolConfirmationInteraction:
    """
    HITL interaction implementation for tool-level confirmation.

    Generates contextual confirmation questions for individual tool executions
    using LLM streaming.

    Note: This wraps the existing generate_confirmation_question_stream() method
    to provide consistency with the registry pattern.

    Attributes:
        question_generator: HitlQuestionGenerator instance for LLM calls

    Example:
        >>> generator = HitlQuestionGenerator()
        >>> interaction = ToolConfirmationInteraction(question_generator=generator)
        >>> async for token in interaction.generate_question_stream(
        ...     context={"tool_name": "delete_email", "tool_args": {...}},
        ...     user_language="fr",
        ... ):
        ...     print(token, end="", flush=True)

    See Also:
        - HitlInteractionProtocol: Contract this class implements
        - HitlQuestionGenerator.generate_confirmation_question_stream()
    """

    def __init__(self, question_generator: "HitlQuestionGenerator") -> None:
        """
        Initialize ToolConfirmationInteraction.

        Args:
            question_generator: HitlQuestionGenerator instance for LLM calls
        """
        self._question_generator = question_generator

    @property
    def interaction_type(self) -> HitlInteractionType:
        """Get the interaction type."""
        return HitlInteractionType.TOOL_CONFIRMATION

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = "Europe/Paris",
        tracker: Any | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate tool confirmation question via LLM streaming.

        Extracts tool_name and tool_args from context, then streams
        the confirmation question token by token.

        Args:
            context: Interrupt context with:
                - tool_name: Name of the tool
                - tool_args: Tool arguments dict
            user_language: Language code (fr, en, es)
            user_timezone: User's IANA timezone for datetime context
            tracker: Optional TokenTrackingCallback

        Yields:
            str: Individual tokens from LLM

        Raises:
            Exception: If LLM streaming fails (caught by caller)

        Performance:
            - TTFT target: < 300ms (tool questions are shorter)
            - Total duration: 0.5-2 seconds
        """
        # Import metrics locally to avoid circular imports
        from src.infrastructure.observability.metrics_agents import (
            hitl_question_tokens_per_second,
            hitl_question_ttft_seconds,
        )

        # Extract data from context
        tool_name = context.get("tool_name", "unknown")
        tool_args = context.get("tool_args", {})

        # Stream question tokens using existing method
        start_time = time.time()
        first_token_received = False
        token_count = 0

        logger.info(
            "tool_confirmation_question_streaming_started",
            tool_name=tool_name,
            args_count=len(tool_args),
            user_language=user_language,
        )

        async for token in self._question_generator.generate_confirmation_question_stream(
            tool_name=tool_name,
            tool_args=tool_args,
            user_language=user_language,
            user_timezone=user_timezone,
            tracker=tracker,
        ):
            # Track TTFT on first token
            if not first_token_received:
                ttft = time.time() - start_time
                hitl_question_ttft_seconds.labels(type="tool_confirmation").observe(ttft)
                first_token_received = True
                logger.debug(
                    "tool_confirmation_question_first_token",
                    ttft_seconds=ttft,
                    tool_name=tool_name,
                )

            token_count += 1
            yield token

        # Track completion metrics
        total_duration = time.time() - start_time
        if total_duration > 0:
            tokens_per_second = token_count / total_duration
            hitl_question_tokens_per_second.labels(type="tool_confirmation").observe(
                tokens_per_second
            )

        logger.info(
            "tool_confirmation_question_streaming_complete",
            tool_name=tool_name,
            token_count=token_count,
            duration_seconds=total_duration,
            tokens_per_second=tokens_per_second if total_duration > 0 else 0,
        )

    def build_metadata_chunk(
        self,
        context: dict[str, Any],
        message_id: str,
        conversation_id: str,
        registry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Build metadata for the initial HITL chunk.

        Creates metadata dict with tool confirmation specific fields.

        Data Registry LOT 4 Integration:
            When registry_ids is provided, includes them in metadata so
            frontend can render <LARSCard> components for the items
            being confirmed (e.g., contact cards, email previews).

        Args:
            context: Interrupt context with tool_name, tool_args, etc.
            message_id: Unique message ID
            conversation_id: Conversation UUID string
            registry_ids: data registry IDs for items related to this tool
                          (e.g., ["contact_abc123"] for send_email to contact)

        Returns:
            Metadata dict for hitl_interrupt_metadata chunk with:
                - action_requests: Tool confirmation action
                - registry_ids: Registry IDs for rich rendering
                - tool_name: Tool being confirmed
        """
        tool_name = context.get("tool_name", "unknown")
        tool_args = context.get("tool_args", {})

        # Data Registry LOT 4: Extract registry_ids from context if not explicitly provided
        # Tools can pass registry_ids in their interrupt context
        if registry_ids is None:
            registry_ids = context.get("registry_ids", [])

        # Build action_requests in expected format
        action_requests = [
            {
                "type": "tool_confirmation",
                "tool_name": tool_name,
                "tool_args": tool_args,
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
            # Tool-specific metadata
            "tool_name": tool_name,
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
        return HitlMessages.get_fallback(HitlMessageType.TOOL_CONFIRMATION, user_language)
