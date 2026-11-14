"""The inline parser reads a hostile line in linear time, and exactly what it read before.

A document's text is the model's, and a model relays what it was given: a line of
``**a **a **a …`` or of ``[a [a [a …`` made every opening marker scan the rest of the
line for a closer that was not there — 32 000 characters cost seconds of a regex
search that holds the interpreter lock, in a worker serving other people's turns.

The rewrite decides, once per line, whether a closer of each kind exists further on
— no closer for one opener means none for the next — and reads a link from its first
closing bracket. It must accept EXACTLY the language of the patterns it replaces,
frozen below as they shipped and compared over every short string of the marks they
read (the method of ADR-326), and it must grow as the text does (``cpu_growth``).
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Iterable

import pytest

from src.domains.document_generation.inline import Span, parse_inline
from tests.support.cpu_growth import CEILING_SECONDS, measure_growth

pytestmark = pytest.mark.unit

# --- the former parser, byte for byte as it shipped ---------------------------

_FORMER_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_FORMER_TOKEN = re.compile(
    r"(?P<bold_italic>\*\*\*(?=\S)(?:.+?)(?<=\S)\*\*\*)"
    r"|(?P<bold_italic_underscore>(?<!\w)___(?=\S)(?:.+?)(?<=\S)___(?!\w))"
    r"|(?P<bold>\*\*(?=\S)(?:.+?)(?<=\S)\*\*)"
    r"|(?P<bold_underscore>(?<!\w)__(?=\S)(?:.+?)(?<=\S)__(?!\w))"
    r"|(?P<italic>(?<![\w*])\*(?=[^\s*])(?:.+?)(?<=[^\s*])\*(?![\w*]))"
    r"|(?P<underscore>(?<!\w)_(?=\S)(?:.+?)(?<=\S)_(?!\w))"
    r"|(?P<code>`[^`\n]+`)"
)
_ESCAPES: tuple[tuple[str, str], ...] = ((r"\*", "\x00"), (r"\_", "\x01"), (r"\`", "\x02"))
_ADDRESS = re.compile("\x03(\\d+)\x03")


def _restore(text: str) -> str:
    for marker, placeholder in _ESCAPES:
        text = text.replace(placeholder, marker[1])
    return text


def _former_span(token: str, kind: str) -> Span:
    if kind in ("bold_italic", "bold_italic_underscore"):
        return Span(_restore(token[3:-3]), bold=True, italic=True)
    if kind in ("bold", "bold_underscore"):
        return Span(_restore(token[2:-2]), bold=True)
    if kind in ("italic", "underscore"):
        return Span(_restore(token[1:-1]), italic=True)
    return Span(_restore(token[1:-1]), code=True)


def former_parse_inline(text: str) -> list[Span]:
    """``parse_inline`` as it shipped before the linear rewrite."""
    if not text:
        return []
    for marker, placeholder in _ESCAPES:
        text = text.replace(marker, placeholder)
    addresses: list[str] = []

    def set_aside(match: re.Match[str]) -> str:
        addresses.append(_restore(match.group(2)))
        return f"{match.group(1)} (\x03{len(addresses) - 1}\x03)"

    text = _FORMER_LINK.sub(set_aside, text)
    spans: list[Span] = []
    position = 0
    for match in _FORMER_TOKEN.finditer(text):
        if match.start() > position:
            spans.append(Span(_restore(text[position : match.start()])))
        spans.append(_former_span(match.group(0), match.lastgroup or "code"))
        position = match.end()
    if position < len(text):
        spans.append(Span(_restore(text[position:])))
    if not addresses:
        return spans
    linked: list[Span] = []
    for span in spans:
        for index, part in enumerate(_ADDRESS.split(span.text)):
            if index % 2:
                address = addresses[int(part)]
                linked.append(Span(address, span.bold, span.italic, span.code, address))
            elif part:
                linked.append(Span(part, span.bold, span.italic, span.code, span.url))
    return linked


# --- the same language ---------------------------------------------------------


def _strings(alphabet: Iterable[str], up_to: int) -> Iterable[str]:
    symbols = list(alphabet)
    for length in range(up_to + 1):
        for parts in itertools.product(symbols, repeat=length):
            yield "".join(parts)


#: The marks each rule reads, as symbols, and how many of them a compared string holds
#: at most. A symbol may be several characters — a whole marker, the middle of a link
#: — so that five of them already nest emphasis and frame a link by its neighbours:
#: the suite runs under coverage, where a deeper sweep costs minutes (the rewrite was
#: compared once over 22 million strings, up to ten symbols, before it was kept).
ALPHABETS: dict[str, tuple[tuple[str, ...], int]] = {
    "emphasis": (("*", "**", "_", "__", "`", "a", " "), 5),
    "emphasis over lines": (("*", "_", "`", "a", " ", "\n"), 5),
    "escapes and word edges": (("\\*", "\\_", "*", "_", "a", "é", " "), 5),
    "links": (("[", "](http://x", ")", "]", "(", "a", " ", "\n"), 5),
    "links and emphasis": (("[a](http://x_y)", "[", "]", "*", "_", "a", " "), 5),
}


@pytest.mark.parametrize("name", list(ALPHABETS))
def test_the_linear_parser_reads_exactly_what_the_former_one_read(name: str) -> None:
    alphabet, up_to = ALPHABETS[name]
    checked = 0
    for text in _strings(alphabet, up_to):
        checked += 1
        assert parse_inline(text) == former_parse_inline(text), f"differs on {text!r}"
    assert checked > 9_000


# --- linear growth -------------------------------------------------------------

#: Characters at the small size; the large size is four times as many.
SMALL = 8_000
#: Each witness is ONE line: an opener that finds no closer, again and again.
WITNESSES: dict[str, Callable[[int], str]] = {
    "unclosed bold": lambda n: "**a " * (n // 4),
    "unclosed bold italic": lambda n: "***a " * (n // 5),
    "unclosed italic": lambda n: "*a " * (n // 3),
    "unclosed underscore": lambda n: "_a " * (n // 3),
    "unclosed double underscore": lambda n: "__a " * (n // 4),
    "a run of asterisks": lambda n: "*" * n,
    "a run of underscores": lambda n: "_" * n,
    "a run of backticks": lambda n: "`" * n,
    "unclosed brackets": lambda n: "[a " * (n // 3),
    "brackets before one closer": lambda n: "[" * n + "]",
    "links with no closing parenthesis": lambda n: "[a](http://x" * (n // 12),
    "links whose address ends at a far blank": lambda n: "[a](http://x" * (n // 12) + " ",
    "a closer on the next line only": lambda n: "**a " * (n // 4) + "\nb**",
    "one unclosed marker a line": lambda n: "**a\n" * (n // 4),
    "a run of line breaks": lambda n: "\n" * n,
    "empty links": lambda n: "[](http://x) " * (n // 13),
    "every mark, none closed": lambda n: "**a *b _c __d `e [f " * (n // 20),
}


@pytest.mark.parametrize("witness", list(WITNESSES))
def test_the_parser_grows_linearly_on_a_hostile_line(witness: str) -> None:
    make = WITNESSES[witness]
    growth = measure_growth(parse_inline, make(SMALL), make(4 * SMALL))

    assert growth.elapsed < CEILING_SECONDS, f"{witness!r}: {growth.elapsed:.2f} s"
    assert growth.linear, f"{witness!r}: {growth.describe()}: super-linear"


@pytest.mark.parametrize("witness", ["unclosed bold", "unclosed brackets"])
def test_the_criterion_catches_the_former_parser(witness: str) -> None:
    """A guard that could not fail proves nothing: the former parser must be refused."""
    make = WITNESSES[witness]
    growth = measure_growth(former_parse_inline, make(4_000), make(16_000))

    assert growth.judged, "the former parser is too fast here to judge its growth"
    assert not growth.linear, f"the criterion let the former parser pass ({growth.describe()})"
