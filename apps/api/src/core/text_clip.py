"""Cutting display prose to a bound without cutting a word.

One implementation for every surface that shortens a sentence a person reads:
an effect label under a chat bubble (ADR-263) and the prose fields of a
relationship debrief (ADR-269). A cut in the middle of a word reads as a
defect — « posture cr » under a generated image (2026-09-23) — while the same
cut on a word boundary, ellipsis included, reads as intentional.

Display text only: a value another program parses (an id, a URL, JSON) is
never shortened here.
"""

from __future__ import annotations

import re

#: The mark a shortened text ends with — one character, counted in the bound.
ELLIPSIS = "…"

#: The word the bound falls inside, with the whitespace before it — any Unicode
#: whitespace, since French prose carries no-break spaces (« posture : »).
_PARTIAL_WORD = re.compile(r"\s+\S*$")

#: Separators a cut must not leave dangling before the ellipsis: « avant,… »
#: reads as a typo, « avant… » as a cut.
_DANGLING_SEPARATORS = re.compile(r"[\s,;:—–-]+$")


def clip_on_word(text: str, limit: int) -> str:
    """Cut prose to ``limit`` characters, ellipsis included, on a word boundary.

    The ellipsis is counted IN the bound: a clip that returned ``limit + 1``
    characters would need the stored contract to be one character looser than
    the published one, and two nearly-equal numbers is how they drift. A text
    whose kept part is a single token (a long URL, an unbroken name) is cut
    inside it, since that is the only cut there is.

    Args:
        text: The prose, already stripped by the caller when that matters.
        limit: Longest the result may be, ellipsis included; at least 1.

    Returns:
        ``text`` unchanged when it fits, else its head and an ellipsis.
    """
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    # The cut falls inside a word unless the first dropped character is
    # whitespace: drop the partial word, keep a complete one.
    on_word = head if text[limit - 1].isspace() else (_PARTIAL_WORD.sub("", head) or head)
    kept = _DANGLING_SEPARATORS.sub("", on_word)
    return f"{kept or head}{ELLIPSIS}"
