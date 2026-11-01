"""The « which of these? » interaction: a template, third parties drawn literally (ADR-367)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.domains.agents.services.hitl.interactions.entity_disambiguation import (
    EntityDisambiguationInteraction,
    disambiguation_question,
)

pytestmark = pytest.mark.unit

HOSTILE = {
    "descriptor": "Marc",
    "domain": "email",
    "candidates": [
        {"index": 1, "label": "Marc <m@example.com> · ![x](https://tracker.example/p.png)"},
        {"index": 2, "label": "Marc <m@example.com> · <img src=https://tracker.example/q>"},
    ],
}


async def _streamed(context: dict[str, Any], language: str = "en") -> str:
    interaction = EntityDisambiguationInteraction(question_generator=MagicMock())
    return "".join(
        [token async for token in interaction.generate_question_stream(context, language)]
    )


class TestTheQuestion:
    async def test_a_third_partys_subject_draws_no_markup(self) -> None:
        question = await _streamed(HOSTILE)

        # An image or an HTML tag in a subject is shown, never loaded.
        assert "![x](" not in question and "<img" not in question
        assert "**1.**" in question and "**2.**" in question

    async def test_the_streamed_question_is_the_drawn_one(self) -> None:
        # Token by token (a space after each word): the same words, in order.
        streamed = await _streamed(HOSTILE)
        assert streamed.split() == disambiguation_question(HOSTILE, "en").split()

    def test_asked_again_it_says_so(self) -> None:
        again = disambiguation_question({**HOSTILE, "reask": True}, "fr")
        assert again.startswith("Je n'ai pas compris lequel tu veux.")


class TestTheCardsMetadata:
    def test_it_carries_the_raw_options_and_the_other_answers(self) -> None:
        interaction = EntityDisambiguationInteraction(question_generator=MagicMock())
        chunk = interaction.build_metadata_chunk(HOSTILE, "msg-1", "conv-1")
        (request,) = chunk["action_requests"]

        # Raw: the card escapes what it draws.
        assert [c["label"] for c in request["candidates"]] == [
            c["label"] for c in HOSTILE["candidates"]
        ]
        assert request["type"] == "entity_disambiguation"
        assert [a["action"] for a in request["available_actions"]] == ["none", "cancel"]
        assert chunk["message_id"] == "msg-1" and chunk["is_plan_approval"] is False
