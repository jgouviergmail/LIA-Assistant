"""
Entity Disambiguation Interaction - HITL streaming for entity resolution.

This module implements HitlInteractionProtocol for entity disambiguation.
It handles cases where a user mentions a name/reference that matches multiple
entities (contacts, events, etc.) or when multiple data fields are eligible
for the intended action.

Use Cases:
    1. Multiple contacts match "Jean Dupont" -> ask user to choose
    2. One contact has multiple emails -> ask which email to use for sending
    3. Ambiguous reference "le meeting" matches multiple events -> clarify

Features:
    - Generic entity disambiguation (contacts, emails, events, etc.)
    - Multi-field disambiguation (multiple emails for one contact)
    - Pre-formatted choice presentation with numbered options
    - Data Registry integration for rich item rendering
    - Multilingual support (fr, en, es, de, it, zh-CN)

Architecture:
    SearchTool returns multiple matches → EntityResolutionService detects ambiguity
    → DisambiguationInteraction generates question with choices
    → User selects option → Plan continues with resolved entity

References:
    - protocols.py: HitlInteractionProtocol definition
    - registry.py: Registration decorator
    - context/resolver.py: ReferenceResolver for base resolution logic
    - EntityResolutionService: Orchestrates resolution flow

Created: 2025-12-07
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


@HitlInteractionRegistry.register(HitlInteractionType.ENTITY_DISAMBIGUATION)
class EntityDisambiguationInteraction:
    """
    HITL interaction implementation for entity disambiguation.

    Generates disambiguation questions when entity resolution finds:
    - Multiple matching entities (contacts, events, files)
    - Multiple eligible data fields (emails, phones for one contact)
    - Ambiguous references requiring user clarification

    The interaction streams questions progressively with numbered choices.

    Attributes:
        question_generator: HitlQuestionGenerator instance for LLM calls

    Example:
        >>> generator = HitlQuestionGenerator()
        >>> interaction = EntityDisambiguationInteraction(question_generator=generator)
        >>> async for token in interaction.generate_question_stream(
        ...     context={
        ...         "disambiguation_type": "multiple_entities",
        ...         "domain": "contacts",
        ...         "original_query": "Jean Dupont",
        ...         "intended_action": "send_email",
        ...         "candidates": [
        ...             {"index": 1, "name": "Jean Dupont", "email": "jean@work.com"},
        ...             {"index": 2, "name": "Jean-Pierre Dupont", "email": "jp@home.com"},
        ...         ],
        ...     },
        ...     user_language="fr",
        ... ):
        ...     print(token, end="", flush=True)

    See Also:
        - HitlInteractionProtocol: Contract this class implements
        - EntityResolutionService: Triggers disambiguation
        - ReferenceResolver: Base resolution logic
    """

    def __init__(self, question_generator: "HitlQuestionGenerator") -> None:
        """
        Initialize EntityDisambiguationInteraction.

        Args:
            question_generator: HitlQuestionGenerator instance for LLM calls
        """
        self._question_generator = question_generator

    @property
    def interaction_type(self) -> HitlInteractionType:
        """Get the interaction type."""
        return HitlInteractionType.ENTITY_DISAMBIGUATION

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = "Europe/Paris",
        tracker: Any | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate disambiguation question via streaming.

        Formats a clear question with numbered choices for user selection.
        Supports two disambiguation types:
        1. multiple_entities: Multiple items match the query
        2. multiple_fields: One item has multiple eligible fields

        Args:
            context: Interrupt context with:
                - disambiguation_type: "multiple_entities" | "multiple_fields"
                - domain: "contacts" | "emails" | "events" | etc.
                - original_query: User's original search term
                - intended_action: What the user wants to do (send_email, etc.)
                - candidates: List of candidate items/fields with display info
                - target_field: For multiple_fields, which field type (email, phone)
            user_language: Language code (fr, en, es, de, it, zh-CN)
            user_timezone: User's IANA timezone for datetime context
            tracker: Optional TokenTrackingCallback

        Yields:
            str: Individual words for progressive display

        Performance:
            - TTFT target: < 100ms (pre-formatted, no LLM)
            - Total duration: < 500ms
        """
        from src.infrastructure.observability.metrics_agents import (
            hitl_question_tokens_per_second,
            hitl_question_ttft_seconds,
        )

        disambiguation_type = context.get("disambiguation_type", "multiple_entities")
        domain = context.get("domain", "items")
        original_query = context.get("original_query", "")
        intended_action = context.get("intended_action", "")
        candidates = context.get("candidates", [])
        target_field = context.get("target_field", "")

        logger.info(
            "disambiguation_question_streaming_started",
            disambiguation_type=disambiguation_type,
            domain=domain,
            candidates_count=len(candidates),
            intended_action=intended_action,
            user_language=user_language,
        )

        # Format the question with choices
        full_question = self._format_disambiguation_question(
            disambiguation_type=disambiguation_type,
            domain=domain,
            original_query=original_query,
            intended_action=intended_action,
            candidates=candidates,
            target_field=target_field,
            user_language=user_language,
        )

        start_time = time.time()
        token_count = 0

        # Stream line-by-line then word-by-word (preserves markdown newlines)
        for line in full_question.split("\n"):
            if line:
                for word in line.split():
                    if token_count == 0:
                        ttft = time.time() - start_time
                        hitl_question_ttft_seconds.labels(type="entity_disambiguation").observe(
                            ttft
                        )
                        logger.debug(
                            "disambiguation_question_first_token",
                            ttft_seconds=ttft,
                        )
                    token_count += 1
                    yield word + " "
            yield "\n"

        # Track completion metrics
        total_duration = time.time() - start_time
        if total_duration > 0:
            tokens_per_second = token_count / total_duration
            hitl_question_tokens_per_second.labels(type="entity_disambiguation").observe(
                tokens_per_second
            )

        logger.info(
            "disambiguation_question_streaming_complete",
            token_count=token_count,
            duration_seconds=total_duration,
            candidates_count=len(candidates),
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

        Creates metadata dict with disambiguation-specific fields.
        Includes candidate information for frontend choice rendering.

        Args:
            context: Interrupt context with disambiguation data
            message_id: Unique message ID
            conversation_id: Conversation UUID string
            registry_ids: Data registry IDs for candidate items

        Returns:
            Metadata dict for hitl_interrupt_metadata chunk with:
                - action_requests: Disambiguation action with candidates
                - registry_ids: Registry IDs for rich rendering
                - disambiguation details for frontend
        """
        candidates = context.get("candidates", [])
        disambiguation_type = context.get("disambiguation_type", "multiple_entities")
        domain = context.get("domain", "")
        intended_action = context.get("intended_action", "")

        # Extract registry_ids from context if not explicitly provided
        if registry_ids is None:
            registry_ids = context.get("registry_ids", [])

        # Build action_requests in expected format
        action_requests = [
            {
                "type": "entity_disambiguation",
                "disambiguation_type": disambiguation_type,
                "domain": domain,
                "intended_action": intended_action,
                "candidates": candidates,
                "registry_ids": registry_ids,
            }
        ]

        return {
            "message_id": message_id,
            FIELD_CONVERSATION_ID: conversation_id,
            "action_requests": action_requests,
            "count": 1,
            "is_plan_approval": False,
            # Disambiguation-specific metadata
            "disambiguation_type": disambiguation_type,
            "domain": domain,
            "intended_action": intended_action,
            "candidates_count": len(candidates),
            "registry_ids": registry_ids,
            "has_registry_items": len(registry_ids) > 0,
        }

    def get_fallback_question(self, user_language: str) -> str:
        """
        Get fallback question for error scenarios.

        Returns a static, pre-defined question when formatting fails.

        Args:
            user_language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Static fallback question string
        """
        return HitlMessages.get_fallback(HitlMessageType.ENTITY_DISAMBIGUATION, user_language)

    def _format_disambiguation_question(
        self,
        disambiguation_type: str,
        domain: str,
        original_query: str,
        intended_action: str,
        candidates: list[dict[str, Any]],
        target_field: str,
        user_language: str,
    ) -> str:
        """
        Format disambiguation question with numbered choices.

        Creates a user-friendly question with clear numbered options.

        Args:
            disambiguation_type: Type of disambiguation needed
            domain: Entity domain (contacts, emails, events)
            original_query: User's original search term
            intended_action: What action the user wants to perform
            candidates: List of candidate items with display info
            target_field: For multiple_fields, which field type
            user_language: Language code for i18n

        Returns:
            Formatted question string with numbered choices
        """
        return HitlMessages.format_disambiguation_question(
            disambiguation_type=disambiguation_type,
            domain=domain,
            original_query=original_query,
            intended_action=intended_action,
            candidates=candidates,
            target_field=target_field,
            language=user_language,
        )
