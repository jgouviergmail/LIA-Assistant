"""A draft asked as one of several says WHERE it stands (ADR-288).

The question of the second draft opens on its position — « Brouillon 2 sur
3 » — above the card, in the person's language; a lone draft says nothing of
the kind. The position is a server line (lot 14: one author for the form),
so no frontend has to learn it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.i18n_hitl import HitlMessages
from src.domains.agents.drafts.card_html import card_surface
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.preview_renderer import render_confirmation_card
from src.domains.agents.services.hitl.interactions.draft_critique import (
    CARD_SEPARATOR,
    DraftCritiqueInteraction,
)

pytestmark = pytest.mark.unit

EMAIL = {"to": "paul@example.org", "subject": "Réunion de lundi", "body": "On se voit lundi ?"}


def _generator(*tokens: str) -> Any:
    async def astream(_prompt: Any, config: Any = None) -> AsyncGenerator[Any]:
        for token in tokens:
            yield SimpleNamespace(content=token)

    llm = MagicMock()
    llm.astream = astream
    return SimpleNamespace(tool_question_llm=llm)


async def _collect(context: dict[str, Any], language: str = "fr") -> str:
    interaction = DraftCritiqueInteraction(question_generator=_generator("Envoyer ?"))
    return "".join(
        [
            token
            async for token in interaction.generate_question_stream(
                context, user_language=language, user_timezone="Europe/Paris"
            )
        ]
    )


def _context(**overrides: Any) -> dict[str, Any]:
    context: dict[str, Any] = {"draft_id": "d-2", "draft_type": "email", "draft_content": EMAIL}
    context.update(overrides)
    return context


class TestThePositionOpensTheQuestion:
    async def test_the_second_of_three_says_so_above_the_card(self) -> None:
        text = await _collect(_context(sequence_index=2, sequence_total=3))
        card = render_confirmation_card(
            Draft(type=DraftType.EMAIL, content=EMAIL), "fr", "Europe/Paris", surface=card_surface()
        )
        position = HitlMessages.get_draft_sequence_position(2, 3, "fr")
        assert text.startswith(position + "\n\n" + card + CARD_SEPARATOR)
        assert text.endswith("Envoyer ?")

    async def test_a_lone_draft_says_nothing_of_the_kind(self) -> None:
        text = await _collect(_context())
        card = render_confirmation_card(
            Draft(type=DraftType.EMAIL, content=EMAIL), "fr", "Europe/Paris", surface=card_surface()
        )
        assert text.startswith(card + CARD_SEPARATOR)

    async def test_a_pre_generated_summary_is_positioned_too(self) -> None:
        text = await _collect(
            _context(draft_summary="Un e-mail à Paul", sequence_index=1, sequence_total=2)
        )
        assert text.startswith(HitlMessages.get_draft_sequence_position(1, 2, "fr") + "\n\n")


class TestTheSummaryOpensTheFirstQuestion:
    """Before the first card, the person reads what the turn prepared — every
    draft of the sequence, each named by its own type (ADR-289, no extra
    interrupt: the confirmation stays one per draft)."""

    SECOND = {"summary": "Call Hua", "start_datetime": "2026-09-17T10:00:00+02:00"}

    def _drafts(self) -> list[dict[str, Any]]:
        return [
            {"draft_id": "d-1", "draft_type": "email", "draft_content": EMAIL},
            {"draft_id": "d-2", "draft_type": "event", "draft_content": self.SECOND},
        ]

    async def test_it_lists_every_draft_then_positions_the_first(self) -> None:
        text = await _collect(
            _context(
                draft_id="d-1",
                sequence_index=1,
                sequence_total=2,
                sequence_drafts=self._drafts(),
            )
        )
        title = HitlMessages.get_draft_sequence_summary(2, "fr")
        assert text.startswith(title + "\n")
        head, _, rest = text.partition("\n\n")
        assert "paul@example.org" in head and "Réunion de lundi" in head
        assert "Call Hua" in head
        assert rest.startswith(HitlMessages.get_draft_sequence_position(1, 2, "fr") + "\n\n")

    async def test_each_row_wears_its_own_type(self) -> None:
        text = await _collect(
            _context(sequence_index=1, sequence_total=2, sequence_drafts=self._drafts())
        )
        head = text.partition("\n\n")[0]
        rows = [line for line in head.splitlines() if line.startswith("- ")]
        assert len(rows) == 2
        assert rows[0].startswith("- 📧") and rows[1].startswith("- 📅")

    async def test_a_later_question_repeats_nothing(self) -> None:
        text = await _collect(_context(draft_id="d-2", sequence_index=2, sequence_total=2))
        assert text.startswith(HitlMessages.get_draft_sequence_position(2, 2, "fr") + "\n\n")

    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    def test_the_title_counts_in_every_language(self, language: str) -> None:
        assert "3" in HitlMessages.get_draft_sequence_summary(3, language)
        assert "2" in HitlMessages.get_draft_sequence_summary(2, language)


class TestThePositionIsTranslated:
    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    def test_every_language_names_both_numbers(self, language: str) -> None:
        line = HitlMessages.get_draft_sequence_position(2, 3, language)
        assert "2" in line and "3" in line
        assert line == line.strip()

    def test_the_six_lines_differ(self) -> None:
        lines = {
            HitlMessages.get_draft_sequence_position(2, 3, lang)
            for lang in ("fr", "en", "de", "es", "it", "zh-CN")
        }
        assert len(lines) == 6
