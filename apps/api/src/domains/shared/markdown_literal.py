"""Text another person wrote, rendered in a chat bubble as itself (ADR-316).

The chat renders Markdown with raw HTML allowed (sanitised) and images from any
``https:`` host. That is right for what LIA writes and wrong for what a third
party typed: a comment travelling with a shared image must not load a tracking
image, hide a link behind friendly words, or draw markup that reads like LIA's
own. So the characters that open a link, an image, an HTML tag, a code span, a
nested quote or a formula become numeric character references, and nothing
else does: Markdown decodes a reference into the plain character, never into
markup. An ``&`` is referenced only where it would open a reference of its own
(``&lt;``), so « Tom & Jerry » stays as typed. Emphasis stays — it can only
change how the person's own words look — and a bare URL still becomes a link
whose text is its address: the reader sees where it goes.

Not a backslash escape: measured in the browser (2026-09-24), the chat's math
step reads ``\\[x\\]`` as a LaTeX display block, so an escaped link rendered
as a formula. A ``$`` is referenced too: the chat's math step reads dollar
delimiters on DECODED text, so it is told to take a REFERENCED dollar as a
literal one (``protectReferencedDollars``, ``lib/markdown-dollars.ts``) —
measured: without it, ``rm -rf $BACKUP_DIR/$OLD`` drew a formula.

A DRAFT card's values are a stricter case (ADR-323, :func:`markdown_data_literal`):
a subject, a recipient, a tool call's argument are what will be sent or run,
so the emphasis marks are referenced as well — « 2*3*4 » drew its 3 in italics
— and so is what the chat's TOKENIZER needs to start a link on the raw source:
the ``:`` of ``http://``, the ``.`` of ``www.``, every ``@``. Referencing a
URL's own marks had cut its link or sent it elsewhere (measured, review 14:
``jean&#95;dupont@example.com`` linked to ``dupont@example.com``, and a
reference written right after a URL was swallowed into the link). With the
triggers referenced, the only links left are the ones GFM's autolink transform
draws on the DECODED text, and each reads as the whole address it goes to
(measured through the chat's pipeline: an address, a URL holding ``_``, a
``www.`` host). An
``_`` between two letters or digits stays as typed: it opens nothing
(CommonMark never opens ``_`` emphasis inside a word). A line's STRUCTURE is
not a character: a body whose lines open with « - » still reads as a list, as
it will in the mail it becomes.

A surface that renders no Markdown reads references as the chat does, through
ONE reader (:func:`read_as_markdown`): outside code every valid reference is
its character; inside a code span or block the text stays as typed; an ``&``
that opens no valid reference (« &copy=2 », which HTML5 would decode) is an
``&``; and a bare URL of LIA's own prose keeps its marks, as the chat's
autolink does. What the reader produces is kept out of the flattener's reach,
so nothing it spells is read as markup. Its code is Markdown's: inside raw
HTML the chat reads no code span, where the reader reads one wherever two
backticks pair — an HTML card references its backticks (``escape_html``), and
LIA's HTML documents are told to write code in ``<code>``, never between
backticks (``html_response_directive.txt``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html.entities import html5

from src.core.constants import MARKDOWN_CODE_SPAN_TICKS_MAX, MARKDOWN_SPAN_MAX_CHARS

__all__ = [
    "RESERVED_MARKERS",
    "literal_quote",
    "markdown_data_literal",
    "markdown_literal",
    "read_as_markdown",
]

#: What opens markup a third party must not draw: links and images (``[``,
#: ``]``), HTML and autolinks (``<``, ``>``), code (`` ` ``), an escape (``\``),
#: a formula (``$``), and an ``&`` that would start a character reference.
_ACTIVE = re.compile(r"[\\`\[\]<>$]|&(?=#?[A-Za-z0-9]+;)")

#: The same, plus strike-through, emphasis, an ``_`` that could delimit — every
#: ``_`` but one between two letters or digits — and what the chat's tokenizer
#: needs to start a link: the ``:`` of ``http://``, the ``.`` of ``www.``, every ``@``.
_ACTIVE_IN_DATA = re.compile(
    r"[\\`\[\]<>$*~@]"
    r"|&(?=#?[A-Za-z0-9]+;)"
    r"|(?<![^\W_])_|_(?![^\W_])"
    r"|(?i:(?<=http)|(?<=https)):(?=//)"
    r"|(?i:(?<=www))\."
)

#: A bare URL the chat autolinks (GFM, micromark), for the reader: a scheme or
#: ``www.`` where a link may start, a domain with no ``_`` that ends on a
#: separator (stricter than micromark, which refuses an ``_`` in its last two
#: segments only), then anything up to a space, a tag or a quote. Stricter is
#: the safe side: a URL read as prose has its marks read as marks, as the chat
#: reads them where it links nothing.
_URL = re.compile(
    r"(?<![^\s(*_~])(?:https?://|www\.)(?:[^\W_]|-)+(?:\.(?:[^\W_]|-)+)*(?![\w-])[^\s<>\"']*"
)


def _reference(match: re.Match[str]) -> str:
    return f"&#{ord(match.group(0))};"


def _bare_urls(text: str) -> list[tuple[int, int]]:
    """Where a bare URL the chat would autolink sits in ``text``: (start, end) spans.

    Args:
        text: The text to scan.

    Returns:
        The spans, in order.
    """
    return [match.span() for match in _URL.finditer(text)]


def markdown_literal(text: str) -> str:
    """Neutralise what would turn a person's text into markup.

    Args:
        text: Text somebody else wrote.

    Returns:
        The same text, rendering as itself.
    """
    return _ACTIVE.sub(_reference, text)


def markdown_data_literal(text: str) -> str:
    """Neutralise what would draw a value differently from how it is held.

    Args:
        text: A value a card shows — what will be sent, saved or run.

    Returns:
        The same text, every mark that could act drawn as its character; a
        link the chat still draws reads as the whole address it goes to.
    """
    return _ACTIVE_IN_DATA.sub(_reference, text)


# --- Reading references as the chat does ------------------------------------

#: A fenced block's opening line (group 1, its fence group 2 — the block runs
#: to a closing fence at least as long, or to the end) or a code span (its
#: backticks group 3, its content group 4; it never crosses a blank line).
#:
#: Linear by construction (ADR-326). The fence is taken whole and never handed
#: back (``(?=(…))\2``, the same atomic form the browser's twin can write, since
#: JavaScript has no possessive quantifier): a line of n backticks with no
#: newline used to try every shorter fence and rescan the line each time. A
#: code span opens with at most ``MARKDOWN_CODE_SPAN_TICKS_MAX`` backticks and
#: holds at most ``MARKDOWN_SPAN_MAX_CHARS``: a run of n backticks was compared
#: n times over as a closing run of every length (measured 3.6 s on 120 KB).
_CODE = re.compile(
    r"^([ \t]{0,3}(?=(`{3,}|~{3,}))\2[^\n]*\n)"
    rf"|(?<!`)(`{{1,{MARKDOWN_CODE_SPAN_TICKS_MAX}}})(?!`)"
    rf"((?:(?!\n[ \t]*\n)[\s\S]){{0,{MARKDOWN_SPAN_MAX_CHARS}}}?)(?<!`)\3(?!`)",
    re.MULTILINE,
)
#: A character reference as CommonMark reads it (the ``;`` is required).
_CHARACTER_REFERENCE = re.compile(
    r"&(?:#([0-9]{1,7})|#[xX]([0-9A-Fa-f]{1,6})|([A-Za-z][A-Za-z0-9]{0,31}));"
)
_REPLACEMENT_CHARACTER = "�"
#: The ASCII punctuation a flattener's rules could read.
_PUNCTUATION = re.compile(r"[!-/:-@\[-`{-~]")
#: The marks a bare URL owns and a flattener's emphasis rules would take.
_URL_MARKS = re.compile(r"[*_~]")

#: Where a character waits while a flattener runs: a private-use plane no rule
#: of Markdown or HTML reads, one shield per ASCII code.
_SHIELD_BASE = 0xF0000
_ESCAPE = chr(_SHIELD_BASE + 0x80)
#: The block this module owns — the shields, the escape, and markers a
#: flattener may use for its own placeholders. A raw character of the block in
#: the text travels as the escape plus its shifted twin, so the reading is
#: one-to-one whatever the text holds.
_BLOCK_END = _SHIELD_BASE + 0xFF
_SHIFT = 0x100
#: Characters of the block a flattener may use as placeholders: the reader
#: never writes one and never leaves a raw one in the text it hands over.
RESERVED_MARKERS = tuple(chr(code) for code in range(_SHIELD_BASE + 0x81, _BLOCK_END + 1))

_RAW_RESERVED = re.compile(f"[{chr(_SHIELD_BASE)}-{chr(_BLOCK_END)}]")
_SHIELDED = re.compile(
    f"{_ESCAPE}([{chr(_SHIELD_BASE + _SHIFT)}-{chr(_BLOCK_END + _SHIFT)}])"
    f"|[{chr(_SHIELD_BASE)}-{chr(_SHIELD_BASE + 0x7F)}]"
)


def _shielded(char: str) -> str:
    """One character, kept out of a flattener's reach where it could act."""
    code = ord(char)
    if code < 0x80:
        return chr(_SHIELD_BASE + code)
    if _SHIELD_BASE <= code <= _BLOCK_END:
        return _ESCAPE + chr(code + _SHIFT)
    return char


def _shield_punctuation(text: str) -> str:
    return _PUNCTUATION.sub(lambda match: _shielded(match.group(0)), text)


def _decoded(match: re.Match[str]) -> str | None:
    """What a reference stands for, or None when it names no character."""
    decimal, hexadecimal, name = match.groups()
    if name is not None:
        return html5.get(f"{name};")
    code = int(decimal) if decimal is not None else int(hexadecimal, 16)
    if code == 0 or 0xD800 <= code <= 0xDFFF or code > 0x10FFFF:
        return _REPLACEMENT_CHARACTER
    return chr(code)


def _read_references(text: str) -> str:
    """Every valid reference decoded and shielded; every other ``&`` shielded."""
    out: list[str] = []
    position = 0
    while (ampersand := text.find("&", position)) != -1:
        out.append(text[position:ampersand])
        reference = _CHARACTER_REFERENCE.match(text, ampersand)
        decoded = _decoded(reference) if reference else None
        if reference is None or decoded is None:
            out.append(_shielded("&"))
            position = ampersand + 1
        else:
            out.append("".join(_shielded(char) for char in decoded))
            position = reference.end()
    out.append(text[position:])
    return "".join(out)


def _read_prose(text: str) -> str:
    """Prose: its references read, the marks of its bare URLs kept as typed."""
    out: list[str] = []
    position = 0
    for start, end in _bare_urls(text):
        out.append(_read_references(text[position:start]))
        url = _URL_MARKS.sub(lambda match: _shielded(match.group(0)), text[start:end])
        out.append(_read_references(url))
        position = end
    out.append(_read_references(text[position:]))
    return "".join(out)


def _read_code(match: re.Match[str], text: str) -> tuple[str, int]:
    """A code block or span: its delimiters as typed, its content shielded whole.

    Args:
        match: A match of :data:`_CODE` — a fence's opening line, or a span.
        text: The text the match was found in.

    Returns:
        The shielded code, and where the text resumes after it.
    """
    if match.group(1) is not None:
        opening, fence = match.group(1), match.group(2)
        closing = re.compile(
            rf"^[ \t]{{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", re.MULTILINE
        ).search(text, match.end())
        body_end = closing.start() if closing else len(text)
        resume = closing.end() if closing else len(text)
        closing_line = closing.group(0) if closing else ""
        return opening + _shield_punctuation(text[match.end() : body_end]) + closing_line, resume
    ticks = match.group(3)
    return ticks + _shield_punctuation(match.group(4)) + ticks, match.end()


def _shield(text: str) -> str:
    """The text as a flattener may read it: nothing it holds can act there."""
    text = _RAW_RESERVED.sub(lambda match: _shielded(match.group(0)), text)
    out: list[str] = []
    position = 0
    while (code := _CODE.search(text, position)) is not None:
        out.append(_read_prose(text[position : code.start()]))
        shielded, position = _read_code(code, text)
        out.append(shielded)
    out.append(_read_prose(text[position:]))
    return "".join(out)


def read_as_markdown(
    text: str,
    flatten: Callable[[str], str] | None = None,
    *,
    restore: Callable[[str], str] | None = None,
) -> str:
    """Flatten text the way the chat reads its character references.

    Outside code, every valid reference (numeric, or a named HTML5 entity with
    its ``;``) becomes its character; inside a code span or block the content
    stays as typed; an ``&`` that opens no valid reference stays an ``&``; a
    bare URL keeps its ``*``, ``_`` and ``~``. All of it is kept out of
    ``flatten``'s reach and written back after it, so « Réunion &#60;lundi&#62; »
    is never a tag to strip, « &#42;&#42;x » never an emphasis to drop, and an
    HTML flattener never decodes a reference twice or reads « &copy=2 » as
    « ©=2 ».

    Args:
        text: Text holding character references (LIA's words, a card's values).
        flatten: The flattener (Markdown or HTML to what a surface renders), or
            None to read the references alone. It may use
            :data:`RESERVED_MARKERS` for placeholders of its own and must leave
            none in what it returns.
        restore: How a kept character is written back — the character itself
            when None; an HTML surface passes its escaping.

    Returns:
        What ``flatten`` makes of the text, each kept character written back.
    """

    def _back(match: re.Match[str]) -> str:
        if match.group(1) is not None:
            return chr(ord(match.group(1)) - _SHIFT)
        char = chr(ord(match.group(0)) - _SHIELD_BASE)
        return restore(char) if restore is not None else char

    shielded = _shield(text)
    return _SHIELDED.sub(_back, flatten(shielded) if flatten is not None else shielded)


def literal_quote(text: str) -> str:
    """A Markdown block quote of a person's text, rendering as itself.

    Args:
        text: Text somebody else wrote; surrounding blank lines are dropped.

    Returns:
        One ``> `` line per line of text; a blank line keeps the quote open.
    """
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(f"> {markdown_literal(line)}" if line else ">" for line in lines)
