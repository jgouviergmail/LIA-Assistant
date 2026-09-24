"""Display prose is cut on a word boundary, ellipsis included in the bound.

Reported 2026-09-23: the « Actions effectuées » card under a generated image
ended on « … posture cr » — a cut in the middle of a word reads as a defect,
the same cut on a word reads as a shortened sentence.
"""

from __future__ import annotations

import pytest

from src.core.text_clip import ELLIPSIS, clip_on_word

pytestmark = [pytest.mark.unit]

_REPORTED = (
    "Image photoréaliste d’un chat domestique jouant de la trompette, trompette dorée "
    "tenue avec ses pattes avant, posture crâneuse, lumière de studio douce"
)


class TestClipOnWord:
    def test_a_text_that_fits_is_unchanged(self) -> None:
        assert clip_on_word("un chat", 7) == "un chat"

    def test_the_reported_card_ends_on_a_whole_word(self) -> None:
        clipped = clip_on_word(_REPORTED, 120)

        assert clipped == (
            "Image photoréaliste d’un chat domestique jouant de la trompette, trompette "
            "dorée tenue avec ses pattes avant, posture…"
        )

    @pytest.mark.parametrize("limit", [5, 12, 40, 119, 120])
    def test_the_ellipsis_counts_inside_the_bound(self, limit: int) -> None:
        """A contract one character looser than the published one is how they drift."""
        clipped = clip_on_word(_REPORTED, limit)

        assert len(clipped) <= limit
        assert clipped.endswith(ELLIPSIS)

    def test_a_cut_that_falls_between_two_words_keeps_the_complete_one(self) -> None:
        """« abc def » + « ghi »: the space after « def » proves it is whole."""
        assert clip_on_word("abc def ghi", 8) == "abc def…"

    def test_no_separator_is_left_dangling(self) -> None:
        assert clip_on_word("des pattes avant, posture", 19) == "des pattes avant…"

    def test_a_no_break_space_is_a_word_boundary(self) -> None:
        """French prose keeps its no-break spaces (the debrief strips nothing)."""
        text = "la relation : bonne, suivie de près"

        assert clip_on_word(text, 17) == "la relation…"

    def test_a_single_long_token_is_cut_inside_it(self) -> None:
        """No space before the bound: that cut is the only one there is."""
        assert clip_on_word("https://example.org/a/very/long/path", 12) == "https://exa…"
