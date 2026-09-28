"""Display prose is cut on a word boundary, ellipsis included in the bound, and
drawn on one line with its typography kept.

Reported 2026-09-23: the « Actions effectuées » card under a generated image
ended on « … posture cr » — a cut in the middle of a word reads as a defect,
the same cut on a word reads as a shortened sentence. ``" ".join(x.split())``,
which ``one_line`` replaced, folded a French colon's no-break space into an
ordinary one (ADR-323): every line separator ``one_line`` folds, and every
typographic space it keeps, is derived below. ``clip_data`` draws a value a
program produced — every space folded, every run of what nobody sees one
marker, spaces between included — and cuts it inside a token.
``spell_unseen`` keeps a label as written and spells only what would mislead.
"""

from __future__ import annotations

import sys
import time
import unicodedata

import pytest

from src.core.text_clip import (
    ELLIPSIS,
    clip_data,
    clip_on_word,
    clip_spelled,
    one_line,
    spell_unseen,
)

pytestmark = [pytest.mark.unit]


def _drawn(text: str) -> str:
    """A program's value as ``clip_data`` draws it, uncut."""
    return clip_data(text, sys.maxsize)


_NBSP = chr(0xA0)

#: Every character ``str.splitlines`` breaks on, and every other ASCII
#: whitespace — derived, so a separator the pattern forgets fails here.
_FOLDED = sorted(
    {chr(c) for c in range(0x110000) if len(("a" + chr(c) + "b").splitlines()) > 1}
    | {chr(c) for c in range(0x80) if chr(c).isspace()}
)
#: The rest of the whitespace: the typography's spaces, which stay.
_KEPT = [chr(c) for c in range(0x110000) if chr(c).isspace() and chr(c) not in _FOLDED]

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


def test_a_preview_on_one_line_keeps_its_typography() -> None:
    """``" ".join(x.split())`` re-spaced a French colon inside item data."""
    ideographic = chr(0x3000)
    text = f"  Rappel{_NBSP}:\n\tMédecin  {ideographic}x "

    assert one_line(text) == f"Rappel{_NBSP}: Médecin {ideographic}x"


@pytest.mark.parametrize("separator", _FOLDED, ids=lambda c: f"U+{ord(c):04X}")
def test_a_preview_on_one_line_breaks_on_no_line_separator(separator: str) -> None:
    """A subject or a title may carry any separator ``str.splitlines`` breaks
    on — a lone carriage return is a line ending too: kept, the bullet it is
    drawn in would break across lines."""
    assert one_line(f"Title{separator}second") == "Title second"


@pytest.mark.parametrize("space", _KEPT, ids=lambda c: f"U+{ord(c):04X}")
def test_a_typographic_space_stays_between_words_and_leaves_the_ends(space: str) -> None:
    """Between two words it is typography; at an end it is nothing — and a
    label drawn in bold is not bold when a space touches its markers."""
    assert one_line(f"{space}Rappel{space}: Médecin{space} ") == f"Rappel{space}: Médecin"


#: Every whitespace character, and every invisible format character.
_WHITESPACE = [chr(c) for c in range(0x110000) if chr(c).isspace()]
_INVISIBLE = [chr(c) for c in range(0x110000) if unicodedata.category(chr(c)) == "Cf"]


@pytest.mark.parametrize("space", _WHITESPACE, ids=lambda c: f"U+{ord(c):04X}")
def test_a_program_s_value_folds_every_space(space: str) -> None:
    """A typographic space in a program's value carries no typography."""
    assert _drawn(f"{space}a{space}{space}b{space}") == "a b"


@pytest.mark.parametrize("char", _INVISIBLE, ids=lambda c: f"U+{ord(c):04X}")
def test_a_program_s_value_shows_every_invisible_character(char: str) -> None:
    """A zero-width space hides text, a bidirectional override reorders it."""
    assert _drawn(f"a{char}b") == f"a⟨U+{ord(char):04X}⟩b"


#: What draws nothing outside the format category: the combining grapheme
#: joiner, the Hangul fillers, a Khmer inherent vowel, a Mongolian and an
#: ordinary variation selector and one of its supplement, unassigned
#: default-ignorable code points (the tag block's unassigned edges among
#: them), the braille blank, and control characters.
_HIDDEN_ELSEWHERE = [
    chr(code)
    for code in (
        0x034F,
        0x115F,
        0x1160,
        0x17B4,
        0x17B5,
        0x180B,
        0x180C,
        0x180F,
        0xFE0F,
        0xE0100,
        0xE0000,
        0xE0080,
        0xE0FFF,
        0x2065,
        0x2800,
        0x3164,
        0xFFA0,
        0xFFF0,
        0xFFF8,
        0x00,
        0x08,
        0x1B,
        0x7F,
    )
]


@pytest.mark.parametrize("char", _HIDDEN_ELSEWHERE, ids=lambda c: f"U+{ord(c):04X}")
def test_what_draws_nothing_is_shown_whatever_its_category(char: str) -> None:
    """Seventy Hangul fillers or braille blanks hid a value as well as seventy
    zero-width spaces: none of them is a format character."""
    assert _drawn(f"a{char}b") == f"a⟨U+{ord(char):04X}⟩b"


def test_a_run_is_one_marker_with_its_length() -> None:
    """Seventy zero-width spaces cost the bound eleven characters, not seventy."""
    marker = "⟨U+200B×70⟩"

    assert _drawn("a" + chr(0x200B) * 70 + "b") == f"a{marker}b"
    assert len(marker) == 11


def test_a_mixed_run_names_three_code_points_in_order_then_counts() -> None:
    """In the order they appear, never sorted: the first is where the run starts."""
    run = "".join(chr(code) for code in (0x200C, 0x200B, 0x2060, 0x2061, 0x2062))

    assert _drawn(f"a{run}b") == "a⟨U+200C,U+200B,U+2060,…×5⟩b"


def test_a_marker_holds_no_whitespace() -> None:
    """A space inside the marker was a word boundary: a cut on a word dropped it."""
    marker = _drawn(chr(0x200B) + chr(0x200C) * 3)

    assert marker == "⟨U+200B,U+200C×4⟩"
    assert not any(char.isspace() for char in marker)


def test_a_script_s_marks_stay_and_a_smear_is_spelled() -> None:
    """Four marks on a letter are the most a script writes; five are a smear."""
    four = "a" + chr(0x0323) + chr(0x0302) + chr(0x0301) + chr(0x0300)

    assert _drawn(four) == four
    assert _drawn("a" + chr(0x0336) * 5) == "a⟨U+0336×5⟩"


def test_enclosing_marks_stack_like_the_others() -> None:
    assert _drawn("a" + chr(0x20DD) * 5) == "a⟨U+20DD×5⟩"


def test_spaces_between_what_nobody_sees_join_its_marker() -> None:
    """One marker each filled a card's bound; the run is one marker."""
    padded = (" " + chr(0x200B)) * 35 + "attacker@evil.example"

    assert _drawn(padded) == "⟨U+200B,U+0020×69⟩attacker@evil.example"


def test_the_spaces_at_a_run_s_edges_stay_spaces() -> None:
    """A space before or after what nobody sees still separates two words."""
    assert _drawn("a " + chr(0x200B) + "b") == "a ⟨U+200B⟩b"
    assert _drawn("❤" + chr(0xFE0F) + " text") == "❤⟨U+FE0F⟩ text"
    assert _drawn(" " + chr(0x200B) + " a ") == "⟨U+200B⟩ a"


def test_marks_on_no_letter_join_the_blank_run() -> None:
    """Marks stacked on spaces drew a smear in a card's bound."""
    smear = (" " + chr(0x0336) * 4) * 14 + "attacker@evil.example"

    assert _drawn(smear) == "⟨U+0336,U+0020×69⟩attacker@evil.example"
    assert _drawn(chr(0x0301) + "a") == "⟨U+0301⟩a"


class TestClipData:
    _URL = "https://evil.example/" + "a" * 100

    def test_a_value_that_fits_is_whole(self) -> None:
        assert clip_data("to: paul@example.org", 80) == "to: paul@example.org"

    def test_the_host_survives_a_word_before_it(self) -> None:
        """Cut on a word, « GET https://… » kept « GET » and dropped the host."""
        clipped = clip_data("GET " + self._URL, 80)

        assert clipped.startswith("GET https://evil.example/")
        assert clipped.endswith(ELLIPSIS) and len(clipped) == 80

    def test_the_host_survives_a_marker_before_it(self) -> None:
        """Cut on a word, two zero-width spaces showed their marker and nothing else."""
        clipped = clip_data(chr(0x200B) * 2 + self._URL, 80)

        assert clipped.startswith("⟨U+200B×2⟩https://evil.example/")
        assert len(clipped) == 80

    def test_a_marker_is_never_cut(self) -> None:
        """Kept whole, or left out with what follows it."""
        clipped = clip_data("x" * 75 + chr(0x200B) * 70 + "tail", 80)

        assert clipped == "x" * 75 + ELLIPSIS

    def test_no_space_is_left_before_the_ellipsis(self) -> None:
        assert clip_data("ab " + chr(0x200B) * 70 + " cd", 10) == "ab…"

    def test_what_a_person_can_see_may_still_fill_the_bound(self) -> None:
        """Visible padding is data: the cut is stated, the padding shown."""
        clipped = clip_data((chr(0x200B) * 2 + ".") * 23 + "attacker@evil.example", 80)

        assert clipped.endswith(ELLIPSIS)
        assert "attacker" not in clipped

    def test_the_value_is_read_only_as_far_as_the_bound(self) -> None:
        """A megabyte argument was drawn whole before the cut (190 ms on the loop)."""
        value = "a" * 20_000_000

        started = time.perf_counter()
        clipped = clip_data(value, 80)
        elapsed = time.perf_counter() - started

        assert clipped == "a" * 79 + ELLIPSIS
        assert elapsed < 0.5


class TestSpellUnseen:
    def test_a_label_keeps_its_typography_and_its_emoji(self) -> None:
        """A joiner inside an emoji and a variation selector draw what they should."""
        label = f"Anniversaire{_NBSP}: 👨" + chr(0x200D) + "👩 ❤" + chr(0xFE0F)

        assert spell_unseen(label) == label

    def test_a_reordering_control_is_spelled(self) -> None:
        """A name ending in an override is read backwards."""
        assert spell_unseen("tool" + chr(0x202E) + "exe.lmth") == "tool⟨U+202E⟩exe.lmth"
        assert spell_unseen("a" + chr(0x2066) + chr(0x2069) + "b") == "a⟨U+2066,U+2069×2⟩b"

    def test_a_label_with_nothing_visible_is_spelled_whole(self) -> None:
        """A title of zero-width spaces headed a card with nothing."""
        assert spell_unseen(chr(0x200B) * 3) == "⟨U+200B×3⟩"
        assert spell_unseen(chr(0x3164) + " " + chr(0x2800)) == "⟨U+3164⟩ ⟨U+2800⟩"

    def test_a_smear_is_spelled(self) -> None:
        assert spell_unseen("a" + chr(0x0336) * 5 + "b") == "a⟨U+0336×5⟩b"

    @pytest.mark.parametrize(
        "joiner", [0x200D, 0x200C, 0xFE0F, 0x034F], ids=["ZWJ", "ZWNJ", "VS16", "CGJ"]
    )
    def test_a_smear_is_spelled_whatever_joins_it(self, joiner: int) -> None:
        """Four marks then a joiner, ten times: one cluster holding forty marks,
        which no stack of four ever reached (review 14)."""
        smear = (chr(0x0336) * 4 + chr(joiner)) * 10

        assert spell_unseen("a" + smear + "b") == f"a⟨U+0336,U+{joiner:04X}×50⟩b"

    def test_a_script_s_marks_beside_a_joiner_stay(self) -> None:
        text = "a" + chr(0x0301) * 3 + chr(0x200D) + "b"

        assert spell_unseen(text) == text

    def test_it_is_idempotent(self) -> None:
        spelled = spell_unseen(chr(0x200B) * 3)

        assert spell_unseen(spelled) == spelled


@pytest.mark.parametrize(
    "padding",
    [
        chr(0x3000) * 70,
        chr(0x200B) * 70,
        chr(0x3164) * 70,
        chr(0x2800) * 79,
        " " + chr(0x0336) * 70,
        chr(0xFE0F) * 70,
    ],
    ids=[
        "ideographic_space",
        "zero_width_space",
        "hangul_filler",
        "braille_blank",
        "stacked_marks",
        "variation_selector",
    ],
)
def test_padding_never_pushes_a_value_past_the_bound(padding: str) -> None:
    """Seventy ideographic spaces before an address hid it behind the cut, and
    once the spaces were folded seventy zero-width spaces, Hangul fillers or
    stacked marks did the same."""
    shown = clip_data(padding + "attacker@evil.example", 80)

    assert shown.endswith("attacker@evil.example")


class TestClipSpelled:
    """Spelled after the cut, a value passed its bound; cut after the spelling
    on a plain word boundary, a marker could be cut (review 14)."""

    def test_what_is_spelled_never_passes_the_bound(self) -> None:
        label = ("a" + chr(0x202E)) * 60

        clipped = clip_spelled(label, 60)

        assert len(clipped) <= 60 and clipped.endswith(ELLIPSIS)
        assert chr(0x202E) not in clipped

    def test_a_marker_is_never_cut(self) -> None:
        label = "y" * 50 + chr(0x202E) + "z"

        assert clip_spelled(label, 55) == "y" * 50 + ELLIPSIS

    def test_a_marker_the_bound_cannot_hold_is_the_only_cut_there_is(self) -> None:
        assert clip_spelled(chr(0x200B) * 3, 5) == "⟨U+2" + ELLIPSIS

    def test_a_label_that_fits_is_only_spelled(self) -> None:
        assert clip_spelled("a" + chr(0x202E) + "b", 60) == "a⟨U+202E⟩b"


def test_what_nobody_sees_at_a_value_s_end_leaves_no_space_after_its_marker() -> None:
    assert _drawn("a" + chr(0x200B) + " ") == "a⟨U+200B⟩"


def test_a_value_exactly_at_its_bound_is_whole() -> None:
    assert clip_data("a" * 80, 80) == "a" * 80
