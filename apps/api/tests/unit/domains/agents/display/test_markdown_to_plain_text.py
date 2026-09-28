"""A surface that renders no markup gets none (ADR-276, lot 13).

A ticket comment is a paragraph of escaped text honouring newlines, and both
vocabularies reach it: LIA writes Markdown, the HITL renderer writes Markdown
around values that may be HTML written by somebody else's mail client. The
measured shape before this door existed, read on a real ticket:

    <br/>**Titre**: Réserver la salle<br/><br/>**Étapes**: 2

The assertions below are about what a reader SEES, so they pin whole strings —
and the ones that pin what must NOT change are the point of the module: the
stripper is a family of regular expressions, and every one of them can eat
prose that merely resembles a mark.
"""

from __future__ import annotations

import pytest

from src.domains.agents.display.plain_text import markdown_to_plain_text

pytestmark = pytest.mark.unit


class TestNumericReferences:
    def test_a_reference_is_its_character_again(self) -> None:
        """How a third party's character reaches Markdown as itself."""
        assert (
            markdown_to_plain_text("Réunion &#60;lundi&#62; &#91;1&#93; &#95;x&#126;")
            == "Réunion <lundi> [1] _x~"
        )

    def test_it_is_decoded_after_the_marks(self) -> None:
        """Decoded first, the asterisks it spells would be read as emphasis."""
        assert markdown_to_plain_text("&#42;&#42;x&#42;&#42;") == "**x**"

    def test_every_reference_is_read_as_the_chat_reads_it(self) -> None:
        """The chat shows « &#233; » as « é »: kept as typed, the ticket
        disagreed with the chat about the same words (review 14)."""
        assert markdown_to_plain_text("tape &#233; puis &#x26; ou &#0;") == (
            "tape é puis & ou " + chr(0xFFFD)
        )

    def test_a_reference_in_code_stays_as_typed(self) -> None:
        """The chat shows a code span as typed, its references included."""
        assert markdown_to_plain_text("tape `&#91;` puis &#91;") == "tape &#91; puis ["

    def test_a_bare_ampersand_is_an_ampersand(self) -> None:
        """HTML5 reads « &copy=2 » as « ©=2 »; the chat reads Markdown, which does not."""
        assert markdown_to_plain_text("<p>Panier</p> ?id=7&copy=2").split() == [
            "Panier",
            "?id=7&copy=2",
        ]

    def test_a_reference_survives_html_elsewhere_in_the_text(self) -> None:
        """The HTML stripper decodes every reference before it strips its tags:
        « Réunion &#60;lundi&#62; » became the tag « <lundi> » and went."""
        text = "<p>Brouillon</p>\n- **Objet** : Réunion &#60;lundi&#62; [1]"

        assert "Objet : Réunion <lundi> [1]" in markdown_to_plain_text(text)

    def test_a_reference_is_decoded_once(self) -> None:
        """A value typed as « &#60;b&#62; » is drawn « &#38;#60;b&#38;#62; »:
        decoded twice beside HTML, it read « <b> »."""
        text = "<p>Brouillon</p>\n- Code &#38;#60;b&#38;#62; and"

        assert "Code &#60;b&#62; and" in markdown_to_plain_text(text)


class TestMarksGo:
    def test_bold_leaves_only_its_words(self) -> None:
        assert markdown_to_plain_text("**Titre**: Réserver la salle") == "Titre: Réserver la salle"

    def test_a_list_keeps_its_lines_and_gains_a_bullet(self) -> None:
        # The list is the preview's own shape: one field per line. Dropping the
        # marker entirely would read as prose that lost its punctuation.
        assert (
            markdown_to_plain_text("- **Titre**: Réserver la salle\n- **Étapes**: 2")
            == "• Titre: Réserver la salle\n• Étapes: 2"
        )

    def test_a_nested_pair_needs_both_passes(self) -> None:
        assert markdown_to_plain_text("**Sortie `run.sh`**") == "Sortie run.sh"

    def test_a_heading_keeps_its_words(self) -> None:
        assert markdown_to_plain_text("## Résumé\nDeux lignes") == "Résumé\nDeux lignes"

    def test_a_quote_loses_its_mark(self) -> None:
        assert markdown_to_plain_text("> Merci pour tout") == "Merci pour tout"

    def test_a_fence_keeps_what_it_wrapped(self) -> None:
        assert markdown_to_plain_text("```text\nLoyer | 1200\n```") == "Loyer | 1200"

    def test_strike_through_and_italic(self) -> None:
        assert markdown_to_plain_text("~~annulé~~ puis *repris*") == "annulé puis repris"

    def test_a_table_keeps_its_data_and_loses_its_rule(self) -> None:
        # LIA answers with tables, and a ticket comment shows every character:
        # the header and the rows are what a reader wants, « |---|---| » only
        # tells a renderer where the head stops.
        written = markdown_to_plain_text("| Jour | Heure |\n|---|:--:|\n| lundi | 10h |")

        assert written == "| Jour | Heure |\n| lundi | 10h |"

    def test_a_horizontal_rule_of_dashes_is_not_a_bullet(self) -> None:
        assert markdown_to_plain_text("Avant\n\n---\n\nAprès") == "Avant\n\nAprès"


class TestBothVocabularies:
    def test_a_break_written_as_markup_becomes_a_real_break(self) -> None:
        assert markdown_to_plain_text("Bonjour<br/>Paul") == "Bonjour\nPaul"

    def test_a_break_in_any_spelling(self) -> None:
        assert markdown_to_plain_text("a<br>b<BR />c") == "a\nb\nc"

    def test_html_from_a_mail_client_is_flattened_too(self) -> None:
        out = markdown_to_plain_text('**Message**:\n<div class="lia-response"><p>Bonjour</p></div>')
        assert "<" not in out
        assert "Message" in out and "Bonjour" in out

    def test_a_link_keeps_its_address_because_the_reader_cannot_click(self) -> None:
        assert (
            markdown_to_plain_text("[le devis](https://x.example/d.pdf)")
            == "le devis (https://x.example/d.pdf)"
        )


class TestProseIsNotAMark:
    """Every pattern here once had a candidate that ate ordinary text."""

    def test_an_identifier_keeps_its_underscores(self) -> None:
        # ``_`` is not handled at all, and this is why: it lives inside
        # identifiers far more often than around emphasis.
        assert markdown_to_plain_text("run_id: in_progress") == "run_id: in_progress"

    def test_a_comparison_is_not_html(self) -> None:
        assert markdown_to_plain_text("x < 5 and y > 3") == "x < 5 and y > 3"

    def test_a_multiplication_is_not_emphasis(self) -> None:
        assert markdown_to_plain_text("3 * 4 = 12") == "3 * 4 = 12"

    def test_a_parenthetical_that_is_not_a_url_stays_written(self) -> None:
        assert markdown_to_plain_text("[le devis](voir plus bas)") == "[le devis](voir plus bas)"

    def test_a_dash_inside_a_sentence_is_not_a_bullet(self) -> None:
        assert markdown_to_plain_text("Paris - Lyon en 2 h") == "Paris - Lyon en 2 h"


class TestShape:
    def test_a_gap_nobody_asked_for_is_closed(self) -> None:
        assert markdown_to_plain_text("a\n\n\n\n\nb") == "a\n\nb"

    def test_a_paragraph_break_survives(self) -> None:
        assert markdown_to_plain_text("a\n\nb") == "a\n\nb"

    def test_the_edges_are_trimmed(self) -> None:
        # The leading break was HALF the defect: every preview started with one.
        assert markdown_to_plain_text("\n\n**Titre**: X\n\n") == "Titre: X"

    def test_empty_is_a_no_op(self) -> None:
        assert markdown_to_plain_text("") == ""

    def test_plain_prose_passes_through_untouched(self) -> None:
        text = "J'ai réservé la salle pour lundi 14 h, et prévenu Marie."
        assert markdown_to_plain_text(text) == text
