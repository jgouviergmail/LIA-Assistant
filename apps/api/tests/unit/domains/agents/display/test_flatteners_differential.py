"""The linear rewrites accept exactly what the former patterns accepted (ADR-326).

Each pattern the linearity guard forced to change is compared here with its
FORMER form, frozen as it shipped, over every short string of the alphabet
the pattern reads. A rewrite that narrowed or widened the language fails on
the first differing string, named. The bound the spans now carry
(``MARKDOWN_SPAN_MAX_CHARS``) is never reached by a short string, so the
comparison is exact where it runs; what a span longer than the bound does is
stated by its own test below, not left to be discovered.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Iterable

import pytest

from src.core.constants import MARKDOWN_CODE_SPAN_TICKS_MAX, MARKDOWN_SPAN_MAX_CHARS
from src.domains.agents.display import plain_text
from src.domains.agents.display.components.html_flatten import _LINK_RE
from src.domains.shared import markdown_literal
from src.domains.voice_sessions import projection

pytestmark = pytest.mark.unit

# --- the former patterns, byte for byte as they shipped ----------------------

FORMER_TABLE_RULE = re.compile(
    r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-*:?[ \t]*)*\|?[ \t]*$\n?", re.MULTILINE
)
FORMER_HTML_LINK = re.compile(r"<a\s+([^<>]*)>((?:(?!<a\b)[\s\S])*?)</a>", re.IGNORECASE)
FORMER_EMPHASIS = re.compile(r"(\*\*|\*|~~|`)(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
FORMER_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
FORMER_HTML_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
FORMER_CODE = re.compile(
    r"^([ \t]{0,3}(`{3,}|~{3,})[^\n]*\n)"
    r"|(?<!`)(`+)(?!`)((?:(?!\n[ \t]*\n)[\s\S])*?)(?<!`)\3(?!`)",
    re.MULTILINE,
)
FORMER_ICON_SPAN = re.compile(
    r"""<span[^<>]*class=["'][^"']*material-symbols-outlined[^"']*["'][^<>]*>[^<]*</span\s*>""",
    re.IGNORECASE,
)


def _strings(alphabet: Iterable[str], up_to: int) -> Iterable[str]:
    """Every string of at most ``up_to`` symbols of ``alphabet`` (symbols may be tokens)."""
    symbols = list(alphabet)
    for length in range(up_to + 1):
        for parts in itertools.product(symbols, repeat=length):
            yield "".join(parts)


def _first_difference(
    former: Callable[[str], object], current: Callable[[str], object], strings: Iterable[str]
) -> tuple[int, str | None]:
    checked = 0
    for text in strings:
        checked += 1
        if former(text) != current(text):
            return checked, text
    return checked, None


def _same(
    former: re.Pattern[str],
    current: re.Pattern[str],
    alphabet: Iterable[str],
    up_to: int,
    *,
    groups: bool = True,
) -> None:
    """Same matches on every short string — spans, and the groups when a caller reads them."""

    def spans(pattern: re.Pattern[str]) -> Callable[[str], object]:
        if groups:
            return lambda text: [(m.span(), m.groups()) for m in pattern.finditer(text)]
        return lambda text: [m.span() for m in pattern.finditer(text)]

    checked, differing = _first_difference(spans(former), spans(current), _strings(alphabet, up_to))
    assert differing is None, f"differs on {differing!r} after {checked} strings"
    assert checked > 1_000


def test_table_rule_reads_the_same_rows() -> None:
    """The row is dropped whole (``.sub("")``): its one former group was never read."""
    _same(FORMER_TABLE_RULE, plain_text._MD_TABLE_RULE_RE, " \t|:-x\n", 6, groups=False)


def test_html_link_reads_the_same_anchors() -> None:
    """Group 1 keeps its leading blank now; the MATCH is the same, and ``href=``
    is searched through the attributes either way."""

    def matches(pattern: re.Pattern[str]) -> Callable[[str], object]:
        return lambda text: [
            (m.span(), m.group(1).strip(), m.group(2)) for m in pattern.finditer(text)
        ]

    checked, differing = _first_difference(
        matches(FORMER_HTML_LINK), matches(_LINK_RE), _strings("<a/> x\n", 6)
    )
    assert differing is None, f"differs on {differing!r} after {checked} strings"


def test_emphasis_reads_the_same_pairs() -> None:
    _same(FORMER_EMPHASIS, plain_text._MD_EMPHASIS_RE, "*~` a\n", 6)


def test_markdown_link_reads_the_same_links() -> None:
    _same(FORMER_MD_LINK, plain_text._MD_LINK_RE, ["[", "]", "(", ")", "a", " ", "http://x"], 5)


def test_voice_link_reads_the_same_links() -> None:
    former = re.compile(r"\[([^\]]+)\]\([^)]*\)")
    _same(former, projection._LINK, ["[", "]", "(", ")", "a", " "], 6)


def test_html_markdown_link_reads_the_same_links() -> None:
    current = re.compile(
        rf"\[([^\]]{{0,{MARKDOWN_SPAN_MAX_CHARS}}})\]\(([^)]{{1,{MARKDOWN_SPAN_MAX_CHARS}}})\)"
    )
    _same(FORMER_HTML_MD_LINK, current, ["[", "]", "(", ")", "a", " "], 6)


def test_code_spans_read_the_same_spans() -> None:
    _same(FORMER_CODE, markdown_literal._CODE, "`~ a\n", 7)


def test_code_fences_of_any_length_read_the_same() -> None:
    """Fences of three or more marks read the same; a code SPAN opened by a run
    longer than ``MARKDOWN_CODE_SPAN_TICKS_MAX`` is the one stated divergence,
    so runs of four backticks are kept out of this equivalence."""
    long_run = re.compile("`" * (MARKDOWN_CODE_SPAN_TICKS_MAX + 1))
    strings = (
        text
        for text in _strings(["`", "``", "```", "~~~", "a", " ", "\n"], 5)
        if not long_run.search(text)
    )

    def spans(pattern: re.Pattern[str]) -> Callable[[str], object]:
        return lambda text: [(m.span(), m.groups()) for m in pattern.finditer(text)]

    checked, differing = _first_difference(
        spans(FORMER_CODE), spans(markdown_literal._CODE), strings
    )
    assert differing is None, f"differs on {differing!r} after {checked} strings"
    assert checked > 1_000


def test_a_code_span_opens_with_at_most_three_backticks() -> None:
    """Four backticks open a span for CommonMark and did for the former pattern;
    they read as prose now — the price of never comparing a run of n backticks
    n times over, stated here."""
    assert FORMER_CODE.search("````a````") is not None
    assert markdown_literal._CODE.search("````a````") is None
    assert markdown_literal._CODE.search("```a```") is not None
    assert markdown_literal._CODE.search("```\ncode\n```\n").group(2) == "```"


def test_icon_span_reads_the_same_spans() -> None:
    tokens = ["<span ", 'class="', "material-symbols-outlined", " ", '"', ">", "</span>", "x", "<"]
    _same(FORMER_ICON_SPAN, plain_text._ICON_SPAN_RE, tokens, 5)


# --- what the bound changes, stated ------------------------------------------


def test_a_span_past_the_bound_keeps_its_marks() -> None:
    """An emphasis or a link label longer than the bound is prose with marks in
    it, never a pair to strip — the price of a linear read, stated here."""
    short = "*" + "a" * MARKDOWN_SPAN_MAX_CHARS + "*"
    long = "*" + "a" * (MARKDOWN_SPAN_MAX_CHARS + 1) + "*"
    assert plain_text._MD_EMPHASIS_RE.sub(r"\2", short) == "a" * MARKDOWN_SPAN_MAX_CHARS
    assert plain_text._MD_EMPHASIS_RE.sub(r"\2", long) == long

    label = "x" * (MARKDOWN_SPAN_MAX_CHARS + 1)
    assert plain_text.markdown_links_to_plain(f"[{label}](https://example.com)") == (
        f"[{label}](https://example.com)"
    )


def test_a_voice_list_marker_needs_its_text_on_the_same_line() -> None:
    """« - » alone on a line, text on the next, is not a list item any more: the
    marker's blanks stop at the line's end (the twin's corpus pins it)."""
    flat = projection.flatten_for_voice("-\nfoo", strip_html=plain_text.strip_html_if_markup)
    assert flat == "- foo"
    assert (
        projection.flatten_for_voice("- foo", strip_html=plain_text.strip_html_if_markup) == "foo."
    )
