"""The title a discussion takes from its first message (ADR-378 amendment 2026-11-12).

A discussion created without a title waits for the person's first message and
takes its title from it: the first line that says something, on one line, cut
on a word when it is long. No model is called — the title is the person's own
words, so they recognise the discussion in the list — and what comes out is a
title the catalogue's own grammar accepts.
"""

from __future__ import annotations

import pytest

from src.core.constants import CONVERSATION_AUTO_TITLE_MAX_LENGTH
from src.core.text_clip import ELLIPSIS
from src.domains.conversations.catalogue_schemas import ConversationTitleInput
from src.domains.conversations.titles import derive_title

pytestmark = pytest.mark.unit


class TestATitleFromTheFirstMessage:
    def test_a_short_message_is_its_own_title(self) -> None:
        assert derive_title("  Plan my trip to Lisbon  ") == "Plan my trip to Lisbon"

    def test_only_the_first_line_that_says_something_is_read(self) -> None:
        message = "\n\n  \nCompare these two offers\n- the first costs 40 €\n- the second 55 €"

        assert derive_title(message) == "Compare these two offers"

    def test_ordinary_whitespace_is_folded_and_typography_kept(self) -> None:
        # The no-break space a French colon takes is typography, and stays.
        assert derive_title("Résume\tce   document : il est long") == (
            "Résume ce document : il est long"
        )

    def test_a_long_message_is_cut_on_a_word_and_says_so(self) -> None:
        message = "Can you look at my calendar for next week and tell me which meetings overlap"

        title = derive_title(message)

        assert title is not None
        assert len(title) <= CONVERSATION_AUTO_TITLE_MAX_LENGTH
        assert title.endswith(ELLIPSIS)
        # Every word kept is a whole word of the message.
        assert message.startswith(title[: -len(ELLIPSIS)])
        assert message[len(title) - len(ELLIPSIS)] == " "

    def test_writing_without_spaces_is_cut_at_the_bound(self) -> None:
        title = derive_title("界" * (CONVERSATION_AUTO_TITLE_MAX_LENGTH * 2))

        assert title == "界" * (CONVERSATION_AUTO_TITLE_MAX_LENGTH - 1) + ELLIPSIS

    @pytest.mark.parametrize("message", ["", "  \n\t ", "​", "﻿ ‍", "\x00"])
    def test_nothing_readable_gives_no_title(self, message: str) -> None:
        assert derive_title(message) is None

    def test_a_nul_never_reaches_the_column(self) -> None:
        # PostgreSQL text cannot store it, and the catalogue's grammar refuses it.
        assert derive_title("Budget\x00 2027") == "Budget 2027"

    @pytest.mark.parametrize(
        "message",
        [
            "Plan my trip to Lisbon",
            "👩🏽‍💻 pair on the parser",
            "工程设计的下一步是什么？",
            "‏مشروع جديد للعام القادم",
            "x" * 5000,
            "Line one\n" + "y" * 900,
        ],
        ids=["latin", "emoji", "cjk", "rtl", "one long word", "long second line"],
    )
    def test_what_comes_out_is_a_title_the_catalogue_accepts(self, message: str) -> None:
        title = derive_title(message)

        assert title is not None
        assert ConversationTitleInput(title=title).title == title
