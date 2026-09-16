"""A draft card is described ONCE and drawn per surface (ADR-289).

The per-type renderers used to produce Markdown lines directly, which made
Markdown the only form a card could take. They now describe the card — a
title under an emoji, rows, notes, blocks — and a serializer draws it: as the
lot-13 Markdown for a surface that renders no markup (a ticket comment), as a
``lia-card`` for the chat. The Markdown form is byte for byte what it was:
``test_detailed_preview_characterization.py`` is the oracle, untouched.
"""

from __future__ import annotations

import pytest

from src.domains.agents.drafts.card_spec import (
    Block,
    CardSpec,
    Note,
    Row,
    to_markdown_lines,
)
from src.domains.agents.drafts.markdown_grammar import (
    labelled_block,
    labelled_row,
    plain_row,
)
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.preview_renderer import (
    build_card_spec,
    render_confirmation_card,
    render_detailed_preview,
)

pytestmark = pytest.mark.unit

EMAIL = {
    "to": "paul@example.org",
    "cc": "anne@example.org",
    "subject": "Réunion de lundi",
    "body": "Bonjour Paul,\n\nOn se voit lundi ?\n\nÀ bientôt",
}


class TestTheDescription:
    def test_an_email_is_described_as_rows_and_a_block(self) -> None:
        spec = build_card_spec(Draft(type=DraftType.EMAIL, content=EMAIL), "fr", "Europe/Paris")
        assert isinstance(spec, CardSpec)
        assert spec.emoji == "📧"
        assert spec.title == "Réunion de lundi"
        kinds = [type(line).__name__ for line in spec.lines]
        assert kinds == ["Row", "Row", "Row", "Block"]
        assert spec.lines[0] == Row(label="Destinataire", value="paul@example.org", key="to")
        assert spec.lines[-1] == Block(label="Message", text=EMAIL["body"])

    def test_a_spreadsheet_write_carries_notes(self) -> None:
        content = {
            "spreadsheet_title": "Budget",
            "sheet_name": "2026",
            "values": [["a", "b"], ["c", "d"]],
        }
        spec = build_card_spec(
            Draft(type=DraftType.SPREADSHEET_WRITE, content=content), "fr", "Europe/Paris"
        )
        assert Note(text="a | b") in spec.lines
        assert Note(text="c | d") in spec.lines

    @pytest.mark.parametrize("draft_type", list(DraftType))
    def test_every_type_describes_itself(self, draft_type: DraftType) -> None:
        spec = build_card_spec(Draft(type=draft_type, content={}), "fr", "Europe/Paris")
        assert spec.title
        assert spec.emoji


class TestTheMarkdownFormIsTheLot13One:
    def test_each_line_kind_maps_to_its_grammar(self) -> None:
        lines = (Row("À", "x"), Note("n"), Block("Message", "a\n\nb"))
        assert to_markdown_lines(lines, " : ") == [
            labelled_row("À", " : ", "x"),
            plain_row("n"),
            labelled_block("Message", "a\n\nb"),
        ]

    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    def test_the_preview_is_the_serialized_description(self, language: str) -> None:
        draft = Draft(type=DraftType.EMAIL, content=EMAIL)
        spec = build_card_spec(draft, language, "Europe/Paris")
        assert "\n".join(
            to_markdown_lines(spec.lines, spec.separator)
        ).strip() == render_detailed_preview(draft, language, "Europe/Paris")

    def test_the_markdown_card_is_unchanged(self) -> None:
        draft = Draft(type=DraftType.EMAIL, content=EMAIL)
        card = render_confirmation_card(draft, "fr", "Europe/Paris")
        assert card.startswith("📧 **Réunion de lundi**\n\n- **Destinataire**")
        assert "<" not in card
