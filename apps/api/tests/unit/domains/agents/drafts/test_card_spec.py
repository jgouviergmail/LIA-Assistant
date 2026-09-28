"""A draft card is described ONCE and drawn per surface (ADR-289).

The per-type renderers used to produce Markdown lines directly, which made
Markdown the only form a card could take. They now describe the card — a
title under an emoji, rows, notes, blocks — and a serializer draws it: as the
lot-13 Markdown for a surface that renders no markup (a ticket comment), as a
``lia-card`` for the chat. The Markdown form is pinned byte for byte by
``test_detailed_preview_characterization.py``; every value is drawn as the
characters it holds, and nothing a card shows may load, hide, or link
elsewhere than it reads before the person has approved it.
"""

from __future__ import annotations

import pytest

from src.domains.agents.drafts.card_spec import (
    Block,
    CardSpec,
    Note,
    Row,
    linkable,
    shown_value,
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

    def test_a_row_value_is_drawn_as_itself(self) -> None:
        """Data, never markup: the chat's sanitiser dropped « <lundi> »."""
        assert to_markdown_lines((Row("Objet", "Réunion <lundi> [1] *a*"),), " : ") == [
            "- **Objet** : Réunion &#60;lundi&#62; &#91;1&#93; &#42;a&#42;"
        ]

    def test_a_list_value_is_joined_then_drawn(self) -> None:
        """Spelled for a person first (``readable``), then drawn as itself."""
        assert to_markdown_lines((Row("À", ["<a>", "b"]),), ": ") == ["- **À**: &#60;a&#62;, b"]

    def test_a_line_break_in_a_row_writes_no_row_of_its_own(self) -> None:
        """A routine's instruction drew a « Planification » it never had."""
        rendered = to_markdown_lines(
            (Row("Instruction", "Envoie le rapport\n- **Planification** : jamais"),), " : "
        )

        assert rendered == [
            "- **Instruction** : Envoie le rapport - &#42;&#42;Planification&#42;&#42; : jamais"
        ]

    def test_a_block_is_drawn_as_itself_with_its_paragraphs(self) -> None:
        """An image in a body was fetched the moment the card was drawn."""
        body = "Bonjour,\n\n![x](https://t.example/p.png) <img src=https://t.example/q.png>"

        (block,) = to_markdown_lines((Block("Message", body),), " : ")

        assert block == labelled_block(
            "Message",
            "Bonjour,\n\n!&#91;x&#93;(https&#58;//t.example/p.png) &#60;img src=https&#58;//t.example/q.png&#62;",
        )

    def test_a_note_is_data(self) -> None:
        """A spreadsheet cell spelled as a link read as one."""
        assert to_markdown_lines((Note("[x](https://e.example) | *y*\nz"),), " : ") == [
            "- &#91;x&#93;(https&#58;//e.example) | &#42;y&#42; z"
        ]

    def test_a_link_is_described_as_one(self) -> None:
        note = Note("Lien", href="https://meet.example/abc", emoji="📹")

        assert to_markdown_lines((note,), " : ") == ["- 📹 [Lien](https://meet.example/abc)"]


class TestWhatACardShows:
    def test_a_url_ending_on_a_backslash_is_no_link(self) -> None:
        """``[Lien](https://e.example/a\\)`` never closes: the backslash
        escapes the parenthesis that would end it (review 14)."""
        assert not linkable("https://e.example/a" + chr(92))

    @pytest.mark.parametrize(
        "url",
        ["https://meet.example/abc?x=1&y=2", "http://e.example/a#b"],
    )
    def test_a_clean_url_is_linkable(self, url: str) -> None:
        assert linkable(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://e.example/x) ![p](https://t.example/p.png",
            "https://e.example/a b",
            'https://e.example/"x',
            "javascript:alert(1)",
            "ftp://e.example/f",
            "https://e.example/<b>",
        ],
    )
    def test_a_url_that_could_end_its_link_is_not(self, url: str) -> None:
        """« …/x) ![](…) » would have drawn an image after the link."""
        assert not linkable(url)

    def test_a_value_is_spelled_and_on_one_line_in_a_row(self) -> None:
        assert shown_value(["a\nb", chr(0x200B) * 2]) == "a b, " + chr(0x200B) * 2
        assert shown_value(chr(0x200B) * 2) == "⟨U+200B×2⟩"

    def test_a_block_keeps_its_paragraphs(self) -> None:
        assert shown_value("a\n\nb", one_row=False) == "a\n\nb"

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
