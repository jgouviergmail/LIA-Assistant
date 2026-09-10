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
