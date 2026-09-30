"""The scripts a voice counts as one token per character are declared, disjoint,
and written as escapes (ADR-326).

The literal « 豈 » that opened the compatibility range was normalised (NFC) to
U+8C48 by a tool on the way to the repository, and the range silently became
U+8C48–U+FAFF: 28 000 characters wide, overlapping the ideographs and the
Hangul, and the browser's twin counted every emoji as a token where the server
counted a quarter. Escapes survive normalisation; this test holds the ranges
and the two twins to the same declaration.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

from src.domains.voice_sessions.projection import _CJK, CJK_RANGES, char_token_cost

pytestmark = pytest.mark.unit

TWIN = Path(__file__).parents[5] / "web" / "src" / "lib" / "live" / "delegation.ts"
_TWIN_PAIR = re.compile(r"\[\s*0x([0-9a-fA-F]+)\s*,\s*0x([0-9a-fA-F]+)\s*\]")


def test_the_ranges_are_ordered_and_disjoint() -> None:
    for low, high in CJK_RANGES:
        assert low < high
    for (a_low, a_high), (b_low, b_high) in itertools.combinations(CJK_RANGES, 2):
        assert (
            a_high < b_low or b_high < a_low
        ), f"{a_low:04X}-{a_high:04X} overlaps {b_low:04X}-{b_high:04X}"


def test_the_pattern_is_written_as_escapes() -> None:
    assert (
        _CJK.pattern.isascii()
    ), "a literal character is one normalisation away from a wrong range"


@pytest.mark.parametrize(
    ("char", "cost"),
    [
        ("中", 1.0),  # an ideograph
        ("豈", 1.0),  # what NFC made of U+F900 — inside 4E00-9FFF anyway
        ("豈", 1.0),  # the compatibility range's first character
        ("﫿", 1.0),  # its last
        ("あ", 1.0),  # Hiragana
        ("가", 1.0),  # Hangul
        ("ꀀ", 0.25),  # Yi: a token under the corrupted range
        ("", 0.25),  # private use: same
        ("ힰ", 0.25),  # Hangul Jamo extended-B: same
        ("\U0001f600", 0.25),  # an emoji: a token in the browser before, a quarter here
        ("A", 0.25),
    ],
)
def test_what_one_character_costs(char: str, cost: float) -> None:
    assert char_token_cost(char) == cost


def test_the_browser_twin_declares_the_same_ranges() -> None:
    """``delegation.ts`` declares ``CJK_RANGES`` as ``[0x…, 0x…]`` pairs; both
    sides read the SAME numbers, so a range edited on one side fails here."""
    source = TWIN.read_text(encoding="utf-8")
    start = source.index("const CJK_RANGES")
    end = source.index("];", start)
    twin = [(int(low, 16), int(high, 16)) for low, high in _TWIN_PAIR.findall(source[start:end])]
    assert twin == list(CJK_RANGES)
