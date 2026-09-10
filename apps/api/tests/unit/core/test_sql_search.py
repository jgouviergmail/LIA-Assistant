"""A search term is a NEEDLE, never a pattern (ADR-276 cold review).

``LIKE``'s two wildcards are ordinary characters to whoever types them: ``_``
is what a person writes in a snake_case title, ``%`` what they write in a rate.
Measured on a real PostgreSQL server, unescaped: ``_`` matched EVERY title on
the board, and ``100%`` matched « Budget 1000 euros ». The conversation search
has escaped them since it was written (``message_reads.matching_content``); the
board did not, and both now go through this one helper.
"""

from __future__ import annotations

import pytest

from src.core.sql_search import LIKE_ESCAPE, escape_like

pytestmark = pytest.mark.unit


class TestEscapeLike:
    def test_a_wildcard_becomes_the_character_it_looks_like(self) -> None:
        assert escape_like("100%") == "100" + LIKE_ESCAPE + "%"
        assert escape_like("run_id") == "run" + LIKE_ESCAPE + "_id"

    def test_the_escape_character_escapes_itself_first(self) -> None:
        """Otherwise a backslash the person typed would escape the character
        after it, and the wildcard would come back."""
        typed = "a" + LIKE_ESCAPE + "%b"
        assert escape_like(typed) == "a" + LIKE_ESCAPE * 2 + LIKE_ESCAPE + "%b"

    def test_ordinary_text_is_untouched(self) -> None:
        assert escape_like("Réserver la salle") == "Réserver la salle"
        assert escape_like("") == ""

    def test_the_escape_character_is_the_one_sql_is_told_about(self) -> None:
        """A term escaped with one character and matched with another means
        nothing at all: the caller passes this very value as ``escape=``."""
        assert LIKE_ESCAPE == "\\"
