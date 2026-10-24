"""Every text flattener reads a hostile text in linear time (ADR-326).

A flattener runs synchronously on the event loop over text a third party may
have written — an e-mail body reaches the card whole, a chat message reaches
the radio's excerpt — so a pattern that rescans the text for every opening
mark is a denial of service: measured before the rewrite, 51 characters of
empty table cells cost 4.5 s, a 32 KB body 3.3 s of frozen loop, 40 KB of
newlines 14 s in the voice projection.

The guard measures CPU GROWTH, never a wall-clock budget alone: each witness runs at
n and at 4n, and a flattener may not take more than eight times longer on four
times the text (linear grows ×4, quadratic ×16, the exponential one did not
finish), measured by ``tests.support.cpu_growth`` — the one measurement the
linearity guards share: the thread's CPU in batches, sizes interleaved, the median
pair deciding, floors under which a ratio is noise. A separate elapsed-time ceiling
still catches the absurdly slow.
The witnesses are the ones that were slow —
every one of them, so a rewrite that trades one for another is caught.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from src.domains.agents.display import plain_text
from src.domains.agents.display.components import base as display_base
from src.domains.agents.display.components.folded_synthesis import format_synthesis_html
from src.domains.agents.display.components.html_flatten import format_email_body, html_to_text
from src.domains.connectors.clients.normalizers.reply_trimming import clean_reply_body
from src.domains.shared.markdown_literal import read_as_markdown, untrusted_markdown
from src.domains.voice.expressive_cues import (
    FISH_S1_CUES,
    AuthoredCues,
    cue_dialect,
    neutralize_literal,
)
from src.domains.voice.sentence_streamer import is_speakable
from src.domains.voice_sessions.projection import flatten_for_voice
from tests.support.cpu_growth import CEILING_SECONDS, measure_growth

pytestmark = pytest.mark.unit

#: Characters at the small size; the large size is four times as many.
SMALL = 8_000
#: Calls averaged into each reading: a flattener's call is short.
CPU_BATCH_CALLS = 16

Flattener = Callable[[str], object]

FLATTENERS: dict[str, Flattener] = {
    "format_synthesis_html": format_synthesis_html,
    "html_to_text(links=False)": lambda s: html_to_text(s, preserve_links=False),
    "html_to_text(links=True)": lambda s: html_to_text(s, preserve_links=True),
    "format_email_body(links=True)": lambda s: format_email_body(
        s, max_length=500, preserve_links=True
    ),
    "markdown_links_to_html": display_base.markdown_links_to_html,
    "looks_like_html": plain_text.looks_like_html,
    "strip_html_if_markup": plain_text.strip_html_if_markup,
    "markdown_links_to_plain": plain_text.markdown_links_to_plain,
    "markdown_to_plain_text": plain_text.markdown_to_plain_text,
    "read_as_markdown": lambda s: read_as_markdown(s),
    "untrusted_markdown": untrusted_markdown,
    "flatten_for_voice": lambda s: flatten_for_voice(s, strip_html=plain_text.strip_html_if_markup),
    "clean_reply_body": lambda s: clean_reply_body(s, subject="x"),
    # A sentence bound for TTS, read before every synthesis (py/polynomial-redos
    # #956/#957: a tag or bracket pattern rescanning to the end per opening mark).
    "is_speakable": is_speakable,
    # The cues of a text written for speech, and the brackets of one that was not,
    # read before every synthesis that carries them (ADR-345).
    "AuthoredCues.render": lambda s: AuthoredCues(cue_dialect("fishaudio", "s2.1-pro"), 3).render(
        s
    ),
    "neutralize_literal(angles)": lambda s: neutralize_literal(
        s, cue_dialect("gemini", "gemini-3.8-flash-tts")
    ),
    "neutralize_literal(parentheses)": lambda s: neutralize_literal(s, FISH_S1_CUES),
    "AuthoredCues.render(parentheses)": lambda s: AuthoredCues(FISH_S1_CUES, 3).render(s),
}

#: Each witness names the shape that was slow somewhere; every flattener meets
#: every witness, because the rules overlap (a link label in a voice line, a
#: table row in a notification body).
WITNESSES: dict[str, Callable[[int], str]] = {
    "unclosed <a then blanks": lambda n: "<a" + " " * n,
    "unclosed <a then newlines": lambda n: "<a" + "\n" * n,
    "a run of blanks": lambda n: " " * n,
    "a run of tabs": lambda n: "\t" * n,
    "a run of newlines": lambda n: "\n" * n,
    "newline-blank pairs": lambda n: "\n " * (n // 2),
    "blanks then <br>": lambda n: " " * n + "<br>",
    "empty table cells": lambda n: "--" + "| " * (n // 2) + "x",
    "table cells with tabs": lambda n: "--" + "|\t" * (n // 2) + "x",
    "unmatched brackets": lambda n: "[" * n,
    "link openers": lambda n: "[a](" * (n // 4),
    "link openers with a scheme": lambda n: "[a](http://x" * (n // 12),
    "italic openers": lambda n: "*a " * (n // 3),
    "bold openers": lambda n: "**a " * (n // 4),
    "strike openers": lambda n: "~~a " * (n // 4),
    "code openers": lambda n: "`a " * (n // 3),
    "a run of backticks": lambda n: "`" * n,
    "a run of fences": lambda n: "```" * (n // 3),
    "fence lines": lambda n: "```\n" * (n // 4),
    "heading marks then newlines": lambda n: "#\n" * (n // 2),
    "the icon class repeated": lambda n: '<span class="material-symbols-outlined'
    + " material-symbols-outlined" * (n // 26),
    "unclosed spans": lambda n: "<span " * (n // 6),
    "unclosed headings": lambda n: "<h1>" * (n // 4),
    "unclosed scripts": lambda n: "<script>" * (n // 8),
    "ampersands": lambda n: "&#" * (n // 2),
    "quoted lines": lambda n: "> a\n" * (n // 4),
    # The two witnesses CodeQL named against the rewritten patterns (#927 on the
    # anchor, #928 on the table rule), measured linear: its analysis models
    # neither `\b` inside a lookahead nor a `(?=…)` guard.
    "a link opener then '<a >a' repeated": lambda n: "<a >" + "<a >a" * (n // 5),
    "tab-pipe pairs": lambda n: "\t|" * (n // 2),
    # A line opening a reference definition whose label never closes: the
    # untrusted-Markdown lookahead reads at most one label per line (ADR-327).
    "unclosed definition labels": lambda n: ("[" + "a" * 200 + "\n") * (n // 202),
    # Parentheses an engine reads as directions, and task boxes (ADR-345).
    "unmatched parentheses": lambda n: "(" * n,
    "control marker openers": lambda n: "<|" * (n // 2),
    "task boxes after list markers": lambda n: "- [x] " * (n // 6),
}


@pytest.mark.parametrize("witness", list(WITNESSES), ids=list(WITNESSES))
@pytest.mark.parametrize("name", list(FLATTENERS), ids=list(FLATTENERS))
def test_a_flattener_grows_linearly_on_a_hostile_text(name: str, witness: str) -> None:
    make = WITNESSES[witness]
    growth = measure_growth(FLATTENERS[name], make(SMALL), make(4 * SMALL), batch=CPU_BATCH_CALLS)

    assert (
        growth.elapsed < CEILING_SECONDS
    ), f"{name} on {witness!r}: {growth.elapsed:.2f} s at {4 * SMALL} chars"
    assert growth.linear, f"{name} on {witness!r}: {growth.describe()}: super-linear"


def test_the_witnesses_are_the_ones_that_were_slow() -> None:
    """The three CodeQL alerts and the measured slow shapes all have a witness."""
    assert "empty table cells" in WITNESSES  # py/redos #900, exponential
    assert "the icon class repeated" in WITNESSES  # py/polynomial-redos #901
    assert "unclosed <a then blanks" in WITNESSES  # py/polynomial-redos #916
    assert "a run of newlines" in WITNESSES  # the voice projection, unflagged
    assert len(WITNESSES) >= 20 and len(FLATTENERS) >= 10


def test_the_criterion_catches_the_former_link_pattern() -> None:
    """A guard that could not fail proves nothing: the criterion above, applied to
    the anchor pattern as it shipped (a blank run before ``[^<>]*``), must refuse
    it — measured, four times the blanks cost twenty times the seconds."""
    import re

    former = re.compile(r"<a\s+([^<>]*)>((?:(?!<a\b)[\s\S])*?)</a>", re.IGNORECASE)
    make = WITNESSES["unclosed <a then blanks"]
    growth = measure_growth(
        lambda s: former.sub("", s), make(2_000), make(8_000), batch=CPU_BATCH_CALLS
    )

    assert growth.judged, "the former pattern is too fast here to judge its growth"
    assert (
        not growth.linear
    ), f"the criterion would have let the former pattern pass ({growth.describe()})"
