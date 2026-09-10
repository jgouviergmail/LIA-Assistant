"""What LIA writes on a ticket is stored as plain text (2026-09-09).

A model answering in HTML puts its tags in front of the person in four places
at once: the panel, the push excerpt, the heartbeat quote and the register's
readable export. Flattened ONCE, where the run writes its words — never at each
reader, which would be four implementations of one rule and three chances to
forget it.

Lot 13 widened the rule from HTML to MARKUP. A ticket comment is a paragraph of
escaped text honouring newlines, so ``**Titre**`` and ``<br/>`` were read out
exactly as typed — the model's own Markdown prose, and the confirmation preview
beside it, which the renderer now writes in Markdown by design. One door,
:func:`markdown_to_plain_text`, flattens both vocabularies; it only ever
shortens, so the cap the confirming comment was built against still holds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domains.agents.display.plain_text import markdown_to_plain_text

pytestmark = pytest.mark.unit


class TestWhatReachesTheTicket:
    def test_html_is_flattened(self) -> None:
        written = markdown_to_plain_text("<p>Salle B <b>réservée</b> pour mardi.</p>")

        assert "<p>" not in written
        assert "<b>" not in written
        assert "réservée" in written

    def test_a_line_break_survives_as_a_break(self) -> None:
        written = markdown_to_plain_text("<p>Deux créneaux.</p><p>Mardi ou jeudi ?</p>")

        assert "Deux créneaux." in written
        assert "Mardi ou jeudi ?" in written

    def test_markdown_marks_go_and_the_lines_stay(self) -> None:
        # Until lot 13 this came out with its asterisks, on a surface that
        # renders none: « - **mardi 10h** » is not a list, it is punctuation
        # the reader has to ignore.
        written = markdown_to_plain_text(
            "Deux options :\n\n- mardi 10h\n- jeudi 14h\n\n**À toi de voir.**"
        )

        assert written == "Deux options :\n\n• mardi 10h\n• jeudi 14h\n\nÀ toi de voir."

    def test_a_confirmation_preview_reads_as_fields(self) -> None:
        """The exact shape the renderer writes, and what the ticket shows."""
        written = markdown_to_plain_text("- **Titre** : Réserver la salle\n- **Étapes** : 2")

        assert written == "• Titre : Réserver la salle\n• Étapes : 2"

    def test_plain_prose_is_returned_untouched(self) -> None:
        # The common case by far: flattening must not be a rewrite.
        prose = "J'ai trouvé deux créneaux.\n\nMardi 10h ou jeudi 14h ?"

        assert markdown_to_plain_text(prose) == prose

    def test_a_comparison_is_not_markup(self) -> None:
        """« a < b and c > d » carries angle brackets and no element."""
        sentence = "Le budget est < 200 € et le délai > 3 jours."

        assert markdown_to_plain_text(sentence) == sentence

    def test_flattening_never_lengthens(self) -> None:
        """What the cap depends on: the comment is bounded BEFORE this runs."""
        for text in (
            "- **Titre** : Réserver la salle\n- **Étapes** : 2",
            "**Gras** et `code` et ~~barré~~",
            "<p>Une réponse en HTML</p>",
            "# Titre\n\n> une citation",
        ):
            assert len(markdown_to_plain_text(text)) <= len(text)


class TestTheRunnerUsesIt:
    def test_the_only_writer_of_LIAs_words_flattens_them(self) -> None:
        """Read from the source: the rule has one site, and a second one added
        later would be a second place to forget it."""
        source = Path("src/infrastructure/scheduler/workboard_runner.py").read_text(
            encoding="utf-8"
        )

        assert "markdown_to_plain_text(plan.comment)" in source

    def test_the_preview_is_not_flattened_twice(self) -> None:
        """It travels INSIDE the comment; the door above is the only one."""
        source = Path("src/infrastructure/scheduler/workboard_runner.py").read_text(
            encoding="utf-8"
        )

        assert source.count("markdown_to_plain_text(") == 1
