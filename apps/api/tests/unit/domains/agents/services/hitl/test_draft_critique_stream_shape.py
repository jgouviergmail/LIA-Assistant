"""What the person reads is the card, a rule, then the model's question (lot 14).

The order is the contract: the renderer's card streams BEFORE the first model
token, so the chat and the ticket show the same fields in the same shape
whatever the model writes next — and the model is asked for the question
alone. Everything here runs against a fake question generator: the shape
must hold with no provider at all.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.preview_renderer import render_confirmation_card
from src.domains.agents.services.hitl.interactions.draft_critique import (
    CARD_SEPARATOR,
    DraftCritiqueInteraction,
)

pytestmark = pytest.mark.unit

EMAIL = {"to": "paul@example.org", "subject": "Réunion de lundi", "body": "On se voit lundi ?"}


def _generator(*tokens: str, fail: bool = False) -> Any:
    """A question generator whose model streams the given tokens, or breaks."""

    async def astream(_prompt: Any, config: Any = None) -> AsyncGenerator[Any]:
        if fail:
            raise RuntimeError("provider down")
        for token in tokens:
            yield SimpleNamespace(content=token)

    llm = MagicMock()
    llm.astream = astream
    return SimpleNamespace(tool_question_llm=llm)


async def _collect(interaction: DraftCritiqueInteraction, context: dict[str, Any]) -> str:
    return "".join(
        [
            token
            async for token in interaction.generate_question_stream(
                context, user_language="fr", user_timezone="Europe/Paris"
            )
        ]
    )


def _context(**overrides: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "draft_id": "d-1",
        "draft_type": "email",
        "draft_content": EMAIL,
    }
    context.update(overrides)
    return context


class TestTheOrder:
    async def test_the_card_comes_first_then_the_rule_then_the_question(self) -> None:
        interaction = DraftCritiqueInteraction(
            question_generator=_generator("Souhaitez-vous ", "envoyer cet e-mail ?")
        )

        text = await _collect(interaction, _context())

        card = render_confirmation_card(
            Draft(type=DraftType.EMAIL, content=EMAIL), "fr", "Europe/Paris"
        )
        assert text.startswith(card + CARD_SEPARATOR)
        assert text.endswith("Souhaitez-vous envoyer cet e-mail ?")

    async def test_the_model_never_repeats_the_fields(self) -> None:
        """The prompt asks for the question alone; the stream shape shows it
        was obeyed once: one recipient, one subject, one body."""
        interaction = DraftCritiqueInteraction(question_generator=_generator("Je l'envoie ?"))

        text = await _collect(interaction, _context())

        assert text.count("paul@example.org") == 1
        assert text.count("Réunion de lundi") == 2  # the title, then the subject row
        assert text.count("On se voit lundi ?") == 1

    async def test_the_rule_is_a_real_rule(self) -> None:
        """A `---` between two blank lines is a thematic break; the same three
        dashes glued to a line are three characters — what capture 1 showed."""
        interaction = DraftCritiqueInteraction(question_generator=_generator("Ok ?"))

        text = await _collect(interaction, _context())

        assert "\n\n---\n\n" in text
        assert "---<br/>" not in text

    async def test_nothing_of_the_card_carries_html(self) -> None:
        interaction = DraftCritiqueInteraction(question_generator=_generator("Ok ?"))

        text = await _collect(interaction, _context())

        assert "<br/>" not in text


class TestWhenTheModelFails:
    async def test_the_card_still_shows_with_a_localized_question(self) -> None:
        interaction = DraftCritiqueInteraction(question_generator=_generator(fail=True))

        text = await _collect(interaction, _context())

        assert "paul@example.org" in text
        assert "confirmer, modifier ou annuler" in text
        assert text.count("---") == 1

    async def test_a_deletion_keeps_its_warning_and_its_own_question(self) -> None:
        interaction = DraftCritiqueInteraction(question_generator=_generator(fail=True))

        text = await _collect(
            interaction,
            _context(draft_type="email_delete", draft_content={"subject": "Newsletter"}),
        )

        assert "irréversible" in text
        assert "Confirmes-tu cette suppression ?" in text


class TestAnUnknownType:
    async def test_it_streams_the_question_with_no_card_and_no_rule(self) -> None:
        """Defense in depth: a type the renderer does not know is asked about
        by the model alone, rather than crashing before the question."""
        interaction = DraftCritiqueInteraction(question_generator=_generator("Tu confirmes ?"))

        text = await _collect(
            interaction, _context(draft_type="quantum_teleport", draft_content={"x": 1})
        )

        assert text == "Tu confirmes ?"


class TestTheOtherPathsAreUntouched:
    async def test_a_clarification_streams_verbatim_without_a_card(self) -> None:
        generator = AsyncMock()
        interaction = DraftCritiqueInteraction(question_generator=generator)

        text = await _collect(
            interaction, _context(clarification_question="Quelle partie veux-tu changer ?")
        )

        assert text.split() == "Quelle partie veux-tu changer ?".split()
        generator.assert_not_called()

    async def test_a_batch_lists_its_items_once(self) -> None:
        generator = AsyncMock()
        interaction = DraftCritiqueInteraction(question_generator=generator)
        drafts = [
            {"draft_id": "d-1", "draft_type": "email", "draft_content": {**EMAIL, "to": "a@x.org"}},
            {"draft_id": "d-2", "draft_type": "email", "draft_content": {**EMAIL, "to": "b@x.org"}},
        ]

        text = await _collect(interaction, _context(batch_total=2, batch_drafts=drafts))

        assert text.count("a@x.org") == 1
        assert text.count("b@x.org") == 1
        generator.assert_not_called()
