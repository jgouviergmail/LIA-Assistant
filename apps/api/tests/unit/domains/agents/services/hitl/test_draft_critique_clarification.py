"""Unit tests for the clarify follow-up path of DraftCritiqueInteraction.

A "clarify" decision in the replay-safe draft EDIT loop persists its
question in the state; the next interrupt payload carries it as
``clarification_question`` and the question stream must surface IT
verbatim (no LLM call) instead of the generic critique question.
"""

from unittest.mock import AsyncMock

from src.domains.agents.services.hitl.interactions.draft_critique import (
    DraftCritiqueInteraction,
)


def _make_interaction() -> DraftCritiqueInteraction:
    return DraftCritiqueInteraction(question_generator=AsyncMock())


async def _collect_stream(interaction: DraftCritiqueInteraction, context: dict) -> str:
    tokens = []
    async for token in interaction.generate_question_stream(context, user_language="fr"):
        tokens.append(token)
    return "".join(tokens)


class TestClarificationQuestionPath:
    """clarification_question in context short-circuits question generation."""

    async def test_clarification_question_streamed_verbatim(self):
        interaction = _make_interaction()
        question = "Peux-tu préciser quelle partie du message tu veux changer ?"

        streamed = await _collect_stream(
            interaction,
            {
                "draft_type": "email",
                "draft_id": "draft-1",
                "draft_content": {"subject": "Hi"},
                "clarification_question": question,
            },
        )

        assert streamed.split() == question.split()

    async def test_no_llm_call_on_clarification_path(self):
        generator = AsyncMock()
        interaction = DraftCritiqueInteraction(question_generator=generator)

        await _collect_stream(
            interaction,
            {
                "draft_type": "email",
                "draft_id": "draft-1",
                "draft_content": {"subject": "Hi"},
                "clarification_question": "Que veux-tu modifier ?",
            },
        )

        generator.assert_not_called()
