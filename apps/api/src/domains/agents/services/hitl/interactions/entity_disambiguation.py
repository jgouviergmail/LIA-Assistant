"""Which shown item a description designates: the question, drawn without a model (ADR-367).

The person designated an item by WHAT it is (« reply to Marc's email ») and
several of the items the assistant showed fit those words. The
reference-disambiguation node interrupts with the options; this interaction
draws the question the person answers — a template in six languages, numbered
options, how to answer — and the metadata the web card reads its buttons from.

The options quote third parties (a sender, a subject), so each one is drawn
literally (:func:`markdown_data_literal`, ADR-316/323): a subject cannot load a
tracking image or draw markup in the chat. The metadata keeps them raw — the
card escapes what it draws.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.field_names import FIELD_CONVERSATION_ID
from src.core.i18n_hitl import HitlMessages, HitlMessageType
from src.domains.shared.markdown_literal import markdown_data_literal, markdown_literal
from src.infrastructure.observability.logging import get_logger

from ..protocols import HitlInteractionType
from ..registry import HitlInteractionRegistry
from .text_tokens import text_tokens

if TYPE_CHECKING:
    from ..question_generator import HitlQuestionGenerator

logger = get_logger(__name__)

#: The answers the card offers beside the options, in the resume vocabulary
#: (``context/choice_answer.py``); an option is chosen by its own button.
_CARD_ACTIONS: tuple[dict[str, str], ...] = (
    {"action": "none", "label": "none", "style": "secondary"},
    {"action": "cancel", "label": "cancel", "style": "destructive"},
)


def disambiguation_question(context: dict[str, Any], user_language: str) -> str:
    """The question asking which option the person meant.

    Args:
        context: The interrupt's action request (``descriptor``, ``candidates``
            each carrying its ``label``, ``reask``, ``found`` for items a
            plan's lookup found).
        user_language: Language code.

    Returns:
        The question, its options drawn literally.
    """
    options = [
        markdown_data_literal(str(c.get("label", ""))) for c in context.get("candidates", [])
    ]
    return HitlMessages.format_disambiguation_question(
        markdown_literal(str(context.get("descriptor", ""))),
        options,
        user_language,
        reask=bool(context.get("reask")),
        found=bool(context.get("found")),
    )


@HitlInteractionRegistry.register(HitlInteractionType.ENTITY_DISAMBIGUATION)
class EntityDisambiguationInteraction:
    """Streams « which of these did you mean? » with numbered options.

    Attributes:
        question_generator: Kept for the protocol's constructor; the question
            is a template and calls no model.
    """

    def __init__(self, question_generator: HitlQuestionGenerator) -> None:
        """Initialize the interaction.

        Args:
            question_generator: The shared HITL question generator.
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
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        tracker: Any | None = None,
    ) -> AsyncGenerator[str]:
        """Stream the question token by token, its lines kept.

        Args:
            context: The interrupt's action request.
            user_language: Language code (fr, en, es, de, it, zh-CN).
            user_timezone: Unused: the options carry their dates already drawn.
            tracker: Unused: no model is called.

        Yields:
            str: The question's tokens.
        """
        from src.infrastructure.observability.metrics_agents import hitl_question_ttft_seconds

        start_time = time.time()
        for index, token in enumerate(text_tokens(disambiguation_question(context, user_language))):
            if index == 0:
                hitl_question_ttft_seconds.labels(type="entity_disambiguation").observe(
                    time.time() - start_time
                )
            yield token
        logger.info(
            "disambiguation_question_streamed",
            candidates_count=len(context.get("candidates", [])),
            reask=bool(context.get("reask")),
        )

    def build_metadata_chunk(
        self,
        context: dict[str, Any],
        message_id: str,
        conversation_id: str,
        registry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """The metadata the web card draws its options and buttons from.

        Args:
            context: The interrupt's action request.
            message_id: Unique message ID.
            conversation_id: Conversation UUID string.
            registry_ids: Unused: the options are described by their labels.

        Returns:
            The ``hitl_interrupt_metadata`` chunk.
        """
        candidates = [
            {"index": c.get("index"), "label": c.get("label", "")}
            for c in context.get("candidates", [])
        ]
        return {
            "message_id": message_id,
            FIELD_CONVERSATION_ID: conversation_id,
            "action_requests": [
                {
                    "type": HitlInteractionType.ENTITY_DISAMBIGUATION.value,
                    "domain": context.get("domain", ""),
                    "candidates": candidates,
                    "reask": bool(context.get("reask")),
                    "available_actions": list(_CARD_ACTIONS),
                }
            ],
            "count": 1,
            "is_plan_approval": False,
            "available_actions": [action["action"] for action in _CARD_ACTIONS],
        }

    def get_fallback_question(self, user_language: str) -> str:
        """The static question when the template cannot be drawn.

        Args:
            user_language: Language code (fr, en, es, de, it, zh-CN).

        Returns:
            The fallback question.
        """
        return HitlMessages.get_fallback(HitlMessageType.ENTITY_DISAMBIGUATION, user_language)
