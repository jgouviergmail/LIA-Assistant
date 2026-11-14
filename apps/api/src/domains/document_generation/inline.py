"""Inline emphasis a model writes and a renderer turns into runs (ADR-274).

The prompt allows ``**bold**`` and ``*italic*``; models also produce
``_italic_``, backticked code and ``[text](url)``. Every rich renderer (docx,
pptx, pdf) consumes the SAME span list, so an emphasis renders identically in
the three; md passes the markup through and txt strips it.

A link reads ``text (url)``: a document is read on paper too, so the address
stays printed. The address is its own span carrying ``url``, which a rich
renderer makes clickable; it is set aside while emphasis is tokenized, so an
underscore or an asterisk inside an address is never read as emphasis.

What is NOT emphasis stays literal: an unmatched marker, an intra-word
underscore (``snake_case``), a multiplication sign in a price list. A renderer
that ate those would deface data it was asked to reproduce.

A line is read in LINEAR time (ADR-326's rule, here for a document's text): an
opening marker is tried only when a closer of its kind exists further on its
line — none for one opener means none for the next — and a link is read from
its first closing bracket, so a line of unclosed markers costs one pass, not
one pass per marker. What is read is exactly what the former single pattern
read (``tests/unit/domains/document_generation/test_inline_linear.py``).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Final

#: Brackets the index of a link's address while emphasis is tokenized. A control
#: character, which ``normalize`` strips from every text the model wrote, so no
#: content can forge one.
_ADDRESS_MARK = "\x03"
_ADDRESS = re.compile(f"{_ADDRESS_MARK}(\\d+){_ADDRESS_MARK}")

#: A link from the bracket closing its text: ``](address)``.
_LINK_TAIL = re.compile(r"\]\((https?://[^\s)]+)\)")
#: Where a link's text ends: its closing bracket, or the line.
_TEXT_END = re.compile(r"[\]\n]")
#: Where an address ends: its closing parenthesis, or a blank.
_ADDRESS_END = re.compile(r"[\s)]")
#: « No such position further on »: asked again, the answer is the same.
_NONE: Final = -1


@dataclass(frozen=True, slots=True)
class _Rule:
    """One emphasis: the token it matches, and where a closer of its kind may start.

    Attributes:
        kind: What the token becomes (``_span_for``).
        mark: The character every token of the rule opens with.
        opener: Characters of the opening marker.
        token: The whole emphasis, tried where an opener may be.
        closer: Zero-width, every position where its closing marker may start.
    """

    kind: str
    mark: str
    opener: int
    token: re.Pattern[str]
    closer: re.Pattern[str]


def _rule(kind: str, mark: str, opener: int, token: str, closer: str) -> _Rule:
    return _Rule(kind, mark, opener, re.compile(token), re.compile(closer))


#: Emphasis rules, longest first. Italic markers require a non-space, non-marker
#: boundary on both sides AND a word boundary outside, which is what keeps
#: ``2 * 3`` and ``snake_case`` literal. Each closer is its token's own closing
#: half: a token matches from an opener exactly when a closer starts further on
#: its line, at least one character after the opener.
_RULES: Final = (
    _rule("bold_italic", "*", 3, r"\*\*\*(?=\S)(?:.+?)(?<=\S)\*\*\*", r"(?<=\S)(?=\*\*\*)"),
    _rule(
        "bold_italic_underscore",
        "_",
        3,
        r"(?<!\w)___(?=\S)(?:.+?)(?<=\S)___(?!\w)",
        r"(?<=\S)(?=___(?!\w))",
    ),
    _rule("bold", "*", 2, r"\*\*(?=\S)(?:.+?)(?<=\S)\*\*", r"(?<=\S)(?=\*\*)"),
    _rule(
        "bold_underscore",
        "_",
        2,
        r"(?<!\w)__(?=\S)(?:.+?)(?<=\S)__(?!\w)",
        r"(?<=\S)(?=__(?!\w))",
    ),
    _rule(
        "italic",
        "*",
        1,
        r"(?<![\w*])\*(?=[^\s*])(?:.+?)(?<=[^\s*])\*(?![\w*])",
        r"(?<=[^\s*])(?=\*(?![\w*]))",
    ),
    _rule("underscore", "_", 1, r"(?<!\w)_(?=\S)(?:.+?)(?<=\S)_(?!\w)", r"(?<=\S)(?=_(?!\w))"),
    _rule("code", "`", 1, r"`[^`\n]+`", r"(?=`)"),
)
#: The characters an emphasis may open with.
_MARK = re.compile(r"[*_`]")

#: Escaped markers are hidden from the tokenizer, then restored as plain text.
_ESCAPES: tuple[tuple[str, str], ...] = ((r"\*", "\x00"), (r"\_", "\x01"), (r"\`", "\x02"))


@dataclass(frozen=True, slots=True)
class Span:
    """A run of text with its emphasis, and the address it links to when it is one."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    url: str = ""


def _restore(text: str) -> str:
    """Put escaped markers back as the characters they stand for."""
    for marker, placeholder in _ESCAPES:
        text = text.replace(placeholder, marker[1])
    return text


def _span_for(token: str, kind: str) -> Span:
    """One matched token as its span."""
    if kind in ("bold_italic", "bold_italic_underscore"):
        return Span(_restore(token[3:-3]), bold=True, italic=True)
    if kind in ("bold", "bold_underscore"):
        return Span(_restore(token[2:-2]), bold=True)
    if kind in ("italic", "underscore"):
        return Span(_restore(token[1:-1]), italic=True)
    return Span(_restore(token[1:-1]), code=True)


def _addresses_aside(text: str) -> tuple[str, list[str]]:
    """Every ``[text](address)`` rewritten ``text (n)``, its address set aside.

    A link's text ends at the FIRST closing bracket after its opening one, so every
    opening bracket before that closing one shares its fate: when what follows it is
    no address, none of them opens a link, and the reading resumes after it.

    Args:
        text: A line, its escaped markers already hidden.

    Returns:
        The text with each address replaced by its bracketed index, and the addresses.
    """
    addresses: list[str] = []
    pieces: list[str] = []
    copied = position = 0
    address_end = 0  # the first blank or closing parenthesis at or after the last asked
    while (opening := text.find("[", position)) != _NONE:
        closing = _TEXT_END.search(text, opening + 1)
        if closing is None:
            break  # neither a closing bracket nor a line end further on: no link closes
        end = position = closing.start()
        position += 1
        if text[end] != "]" or end == opening + 1 or not text.startswith("(", end + 1):
            continue
        if address_end < end + 2:
            found = _ADDRESS_END.search(text, end + 2)
            if found is None:
                break  # no closing parenthesis further on: no address closes
            address_end = found.start()
        tail = _LINK_TAIL.match(text, end) if text[address_end] == ")" else None
        if tail is None:
            continue
        # An escaped marker inside an address (``a\_b``) is the character itself.
        addresses.append(_restore(tail.group(1)))
        index = f"{_ADDRESS_MARK}{len(addresses) - 1}{_ADDRESS_MARK}"
        pieces.extend((text[copied:opening], f"{text[opening + 1 : end]} ({index})"))
        copied = position = tail.end()
    if not addresses:
        return text, addresses
    pieces.append(text[copied:])
    return "".join(pieces), addresses


class _Closers:
    """Whether a closer of a rule starts further on a line, asked at rising positions."""

    __slots__ = ("_end", "_next", "_text")

    def __init__(self, text: str, end: int) -> None:
        self._text, self._end = text, end
        #: Per rule, a closer at or after the last position asked; ``_NONE``: no more.
        self._next: dict[str, int] = {}

    def from_position(self, rule: _Rule, position: int) -> bool:
        """Whether a closer of ``rule`` starts at ``position`` or later on the line."""
        known = self._next.get(rule.kind)
        if known == _NONE:
            return False
        if known is None or known < position:
            found = rule.closer.search(self._text, position, self._end)
            known = self._next[rule.kind] = found.start() if found else _NONE
        return known != _NONE


def _lines(text: str) -> Iterator[tuple[int, int]]:
    """Each line of ``text``, as the positions of its first character and of its end."""
    start = 0
    while (end := text.find("\n", start)) != _NONE:
        yield start, end
        start = end + 1
    yield start, len(text)


def _tokens(text: str) -> Iterator[tuple[str, re.Match[str]]]:
    """Every emphasis of ``text`` in order, each rule tried where it may match.

    The leftmost opener wins, then the first rule that matches there, as one pattern
    of alternatives read them; an opener with no closer further on its line is not
    tried at all, which is what keeps a line of unclosed markers linear.
    """
    for start, end in _lines(text):
        closers = _Closers(text, end)
        position = start
        while (mark := _MARK.search(text, position, end)) is not None:
            position = mark.start()
            character = mark.group()
            token = next(
                (
                    (rule.kind, found)
                    for rule in _RULES
                    if rule.mark == character
                    and closers.from_position(rule, position + rule.opener + 1)
                    and (found := rule.token.match(text, position)) is not None
                ),
                None,
            )
            if token is None:
                position += 1
                continue
            yield token
            position = token[1].end()


def parse_inline(text: str) -> list[Span]:
    """Split a line into emphasis spans.

    Args:
        text: Model text, possibly carrying ``**``, ``*``, ``_``, backticks and
            markdown links.

    Returns:
        Spans in order; an empty text yields no span.
    """
    if not text:
        return []
    for marker, placeholder in _ESCAPES:
        text = text.replace(marker, placeholder)
    text, addresses = _addresses_aside(text)

    spans: list[Span] = []
    position = 0
    for kind, match in _tokens(text):
        if match.start() > position:
            spans.append(Span(_restore(text[position : match.start()])))
        spans.append(_span_for(match.group(0), kind))
        position = match.end()
    if position < len(text):
        spans.append(Span(_restore(text[position:])))
    if not addresses:
        return spans
    return [piece for span in spans for piece in _linked(span, addresses)]


def _linked(span: Span, addresses: list[str]) -> list[Span]:
    """A span with its set-aside addresses put back, each its own linked span."""
    pieces: list[Span] = []
    for index, part in enumerate(_ADDRESS.split(span.text)):
        if index % 2:
            address = addresses[int(part)]
            pieces.append(replace(span, text=address, url=address))
        elif part:
            pieces.append(replace(span, text=part))
    return pieces


def strip_inline(text: str) -> str:
    """The plain text of a line, emphasis markers removed."""
    return "".join(span.text for span in parse_inline(text))
