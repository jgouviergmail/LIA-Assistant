"""
Clarification Interaction - HITL streaming for semantic validation clarification.

This module implements HitlInteractionProtocol for clarification type.
It provides true LLM streaming for clarification questions when semantic
validation detects ambiguities or issues requiring user input.

Features:
    - True LLM token streaming via astream()
    - Fallback to static question on error
    - Multi-language support (fr, en, es, de, it, zh-CN) via i18n_hitl
    - Context-aware question generation based on semantic issues
    - Data Registry integration: registry_ids for rich item rendering (LOT 4)

Data Registry LOT 4 Integration:
    Clarification questions can reference registry items from previous
    tool executions (e.g., "Which of these contacts did you mean?").
    The registry_ids are included in metadata for frontend rendering.

Architecture:
    SemanticValidator detects issues → ClarificationNode triggers interrupt
    → ClarificationInteraction generates questions via streaming
    → User responds → Planner regenerates plan with clarification

References:
    - protocols.py: HitlInteractionProtocol definition
    - registry.py: Registration decorator
    - semantic_validator.py: Issue detection
    - OPTIMPLAN/PLAN.md: Section 4 - Phase 2
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


@HitlInteractionRegistry.register(HitlInteractionType.CLARIFICATION)
class ClarificationInteraction:
    """
    HITL interaction implementation for semantic validation clarification.

    Generates clarification questions when semantic validator detects:
    - Ambiguous user intent
    - Cardinality mismatches
    - Missing dependencies
    - Implicit assumptions

    The interaction streams questions progressively for optimal TTFT.

    Attributes:
        question_generator: HitlQuestionGenerator instance for LLM calls

    Example:
        >>> generator = HitlQuestionGenerator()
        >>> interaction = ClarificationInteraction(question_generator=generator)
        >>> async for token in interaction.generate_question_stream(
        ...     context={
        ...         "clarification_questions": ["Voulez-vous envoyer à UN ou TOUS les contacts ?"],
        ...         "semantic_issues": [{"type": "cardinality_mismatch", ...}],
        ...     },
        ...     user_language="fr",
        ... ):
        ...     print(token, end="", flush=True)

    See Also:
        - HitlInteractionProtocol: Contract this class implements
        - SemanticValidator: Detects issues requiring clarification
        - clarification_node: Triggers clarification interrupt
    """

    def __init__(self, question_generator: "HitlQuestionGenerator") -> None:
        """
        Initialize ClarificationInteraction.

        Args:
            question_generator: HitlQuestionGenerator instance for LLM calls
        """
        self._question_generator = question_generator

    @property
    def interaction_type(self) -> HitlInteractionType:
        """Get the interaction type."""
        return HitlInteractionType.CLARIFICATION

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = "Europe/Paris",
        tracker: Any | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate clarification question via LLM streaming.

        Extracts clarification_questions and semantic_issues from context,
        then streams a consolidated question to the user.

        If clarification_questions are already provided by semantic validator,
        concatenates them. Otherwise, generates from semantic_issues.

        Args:
            context: Interrupt context with:
                - clarification_questions: list of pre-generated questions (optional)
                - semantic_issues: list of issue dicts (type, description, etc)
            user_language: Language code (fr, en, es)
            user_timezone: User's IANA timezone for datetime context
            tracker: Optional TokenTrackingCallback

        Yields:
            str: Individual tokens from LLM or pre-generated questions

        Raises:
            Exception: If LLM streaming fails (caught by caller)

        Performance:
            - TTFT target: < 500ms
            - Total duration: 1-3 seconds
        """
        # Import metrics locally to avoid circular imports
        from src.infrastructure.observability.metrics_agents import (
            hitl_question_tokens_per_second,
            hitl_question_ttft_seconds,
        )

        # Extract data from context
        clarification_questions = context.get("clarification_questions", [])
        semantic_issues = context.get("semantic_issues", [])

        logger.info(
            "clarification_question_streaming_started",
            question_count=len(clarification_questions),
            issue_count=len(semantic_issues),
            user_language=user_language,
        )

        # If validator already provided questions, stream them directly
        if clarification_questions:
            # Concatenate questions with formatting
            full_question = self._format_clarification_questions(
                clarification_questions, user_language
            )

            start_time = time.time()
            token_count = 0

            # Stream word by word for consistent interface
            # (simpler than implementing streaming for pre-generated text)
            words = full_question.split()
            for i, word in enumerate(words):
                # Track TTFT on first word
                if i == 0:
                    ttft = time.time() - start_time
                    hitl_question_ttft_seconds.labels(type="clarification").observe(ttft)
                    logger.debug(
                        "clarification_question_first_token",
                        ttft_seconds=ttft,
                    )

                token_count += 1
                yield word + " "

            # Track completion metrics
            total_duration = time.time() - start_time
            if total_duration > 0:
                tokens_per_second = token_count / total_duration
                hitl_question_tokens_per_second.labels(type="clarification").observe(
                    tokens_per_second
                )

            logger.info(
                "clarification_question_streaming_complete",
                token_count=token_count,
                duration_seconds=total_duration,
            )

        else:
            # No pre-generated questions: Generate from semantic_issues via LLM
            # (Future enhancement - Phase 2 iteration 2)
            # For now, yield fallback
            fallback = self.get_fallback_question(user_language)
            for word in fallback.split():
                yield word + " "

            logger.warning(
                "clarification_question_generated_from_fallback",
                issue_count=len(semantic_issues),
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

        Creates metadata dict with clarification-specific fields.

        Data Registry LOT 4 Integration:
            When registry_ids is provided, includes them in metadata so
            frontend can render <LARSCard> components for items being
            clarified (e.g., "Which of these contacts did you mean?").

        Args:
            context: Interrupt context with clarification_questions, semantic_issues
            message_id: Unique message ID
            conversation_id: Conversation UUID string
            registry_ids: data registry IDs for items needing clarification
                          (e.g., ["contact_abc123", "contact_def456"])

        Returns:
            Metadata dict for hitl_interrupt_metadata chunk with:
                - action_requests: Clarification action
                - registry_ids: Registry IDs for rich rendering
                - issue_types: Types of semantic issues detected
        """
        clarification_questions = context.get("clarification_questions", [])
        semantic_issues = context.get("semantic_issues", [])

        # Data Registry LOT 4: Extract registry_ids from context if not explicitly provided
        # Clarification often needs to reference items from previous searches
        if registry_ids is None:
            registry_ids = context.get("registry_ids", [])

        # Build action_requests in expected format
        action_requests = [
            {
                "type": "clarification",
                "clarification_questions": clarification_questions,
                "semantic_issues": semantic_issues,
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
            # Clarification-specific metadata
            "question_count": len(clarification_questions),
            "issue_count": len(semantic_issues),
            "issue_types": [issue.get("type", "unknown") for issue in semantic_issues],
            # Data Registry LOT 4: Registry IDs at top level for easy access
            "registry_ids": registry_ids,
            "has_registry_items": len(registry_ids) > 0,
        }

    def get_fallback_question(self, user_language: str) -> str:
        """
        Get fallback question for error scenarios.

        Returns a static, pre-defined question when LLM streaming fails
        or when no clarification questions are available.

        Args:
            user_language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Static fallback question string
        """
        return HitlMessages.get_fallback(HitlMessageType.CLARIFICATION, user_language)

    def _format_clarification_questions(
        self,
        questions: list[str],
        user_language: str,
    ) -> str:
        """
        Format multiple clarification questions into a single message.

        Args:
            questions: List of clarification questions
            user_language: Language code for formatting (fr, en, es, de, it, zh-CN)

        Returns:
            Formatted question string
        """
        return HitlMessages.format_clarification_questions(questions, user_language)
