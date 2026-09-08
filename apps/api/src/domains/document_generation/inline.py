"""Inline emphasis a model writes and a renderer turns into runs (ADR-274).

The prompt allows ``**bold**`` and ``*italic*``; models also produce
``_italic_``, backticked code and ``[text](url)``. Every rich renderer (docx,
pptx, pdf) consumes the SAME span list, so an emphasis renders identically in
the three; md passes the markup through and txt strips it.

What is NOT emphasis stays literal: an unmatched marker, an intra-word
underscore (``snake_case``), a multiplication sign in a price list. A renderer
that ate those would deface data it was asked to reproduce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: ``[text](url)`` becomes ``text (url)``: a document is read on paper too.
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")

#: Emphasis tokens, longest first. Italic markers require a non-space, non-marker
#: boundary on both sides AND a word boundary outside, which is what keeps
#: ``2 * 3`` and ``snake_case`` literal.
_TOKEN = re.compile(
    r"(?P<bold_italic>\*\*\*(?=\S)(?:.+?)(?<=\S)\*\*\*)"
    r"|(?P<bold_italic_underscore>(?<!\w)___(?=\S)(?:.+?)(?<=\S)___(?!\w))"
    r"|(?P<bold>\*\*(?=\S)(?:.+?)(?<=\S)\*\*)"
    r"|(?P<bold_underscore>(?<!\w)__(?=\S)(?:.+?)(?<=\S)__(?!\w))"
    r"|(?P<italic>(?<![\w*])\*(?=[^\s*])(?:.+?)(?<=[^\s*])\*(?![\w*]))"
    r"|(?P<underscore>(?<!\w)_(?=\S)(?:.+?)(?<=\S)_(?!\w))"
    r"|(?P<code>`[^`\n]+`)"
)

#: Escaped markers are hidden from the tokenizer, then restored as plain text.
_ESCAPES: tuple[tuple[str, str], ...] = ((r"\*", "\x00"), (r"\_", "\x01"), (r"\`", "\x02"))


@dataclass(frozen=True, slots=True)
class Span:
    """A run of text with its emphasis."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


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
    text = _LINK.sub(lambda match: f"{match.group(1)} ({match.group(2)})", text)

    spans: list[Span] = []
    position = 0
    for match in _TOKEN.finditer(text):
        if match.start() > position:
            spans.append(Span(_restore(text[position : match.start()])))
        spans.append(_span_for(match.group(0), match.lastgroup or "code"))
        position = match.end()
    if position < len(text):
        spans.append(Span(_restore(text[position:])))
    return spans


def strip_inline(text: str) -> str:
    """The plain text of a line, emphasis markers removed."""
    return "".join(span.text for span in parse_inline(text))
