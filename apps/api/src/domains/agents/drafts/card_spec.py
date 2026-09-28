"""What a draft card SAYS, described once and drawn per surface (ADR-289).

A confirmation card was Markdown by construction: the per-type renderers
produced Markdown lines, so Markdown was the only form the card could take,
on every surface. The chat, however, draws data as ``lia-card`` HTML cards —
and a draft about to become one of those data deserves the same care.

So the renderers now DESCRIBE the card and a serializer draws it:

- :class:`Row` — one labelled field (« Destinataire : paul@… »);
- :class:`Note` — one line with no label (a spreadsheet row, a remainder), or
  a link;
- :class:`Block` — a labelled TEXT carrying its own paragraphs (a body);
- :class:`CardSpec` — the emoji, the title and the lines, plus the language's
  own label/value separator.

Everything a card shows of a draft is DATA — what will be sent, saved or run —
and is drawn as the characters it holds (:func:`shown_value`): on one line
where a row stands, what would mislead spelled out, and on the Markdown form
every mark that could act referenced. Nothing in a card may load or hide
before the person has approved it — an image in a body would be fetched the
moment the card is drawn — and nothing may link elsewhere than it reads: on
the Markdown form the chat still links a bare address or URL a value holds,
to itself, its text the whole address (``markdown_data_literal``). The one
link that reads otherwise is a link LIA builds itself, and it is described
as one (:class:`Note` with ``href``), never smuggled in as text.

:func:`to_markdown_lines` is the lot-13 grammar, pinned byte for byte by the
golden characterization net (``test_detailed_preview_characterization.py``),
whose docstring lists every regeneration and why. The HTML form lives in
:mod:`~src.domains.agents.drafts.card_html`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.text_clip import one_line, spell_unseen
from src.domains.agents.drafts.markdown_grammar import (
    labelled_block,
    labelled_row,
    plain_row,
    readable,
)
from src.domains.shared.markdown_literal import markdown_data_literal

__all__ = [
    "Block",
    "CardSpec",
    "Note",
    "PreviewLine",
    "ResultItem",
    "ResultSpec",
    "Row",
    "first_block_index",
    "linkable",
    "shown_value",
    "to_markdown_lines",
]

#: A URL a card may draw as a link: http(s), and nothing that could close the
#: link's Markdown or open another (a space, a bracket, a parenthesis, a quote,
#: a backslash — ``…/a\)`` escaped the parenthesis that closes it).
_LINKABLE = re.compile(r"https?://[^\s()<>\[\]\"'`\\]+")


@dataclass(frozen=True)
class Row:
    """One labelled field of a card.

    ``key`` names the field the way the renderer did (a ``DRAFT_PREVIEW_LABELS``
    key), so a surface that draws icons can pick one; the Markdown form never
    reads it.
    """

    label: str
    value: object
    key: str | None = None
    #: An emoji the Markdown form puts before the label (the result rows do);
    #: the HTML form draws an icon from ``key`` instead.
    emoji: str | None = None


@dataclass(frozen=True)
class Note:
    """One line with no label: a statement, one line of data, or a link.

    A note is data unless ``href`` makes it a link — built by LIA from a URL
    :func:`linkable` accepted — whose words ``text`` is.
    """

    text: str
    href: str | None = None
    #: An emoji put before the line (a link's kind).
    emoji: str | None = None


@dataclass(frozen=True)
class Block:
    """A labelled TEXT that carries its own paragraphs."""

    label: str
    text: str


PreviewLine = Row | Note | Block


@dataclass(frozen=True)
class CardSpec:
    """A draft card, described: what it is headed with and what it lists."""

    emoji: str
    title: str
    separator: str
    lines: tuple[PreviewLine, ...]


@dataclass(frozen=True)
class ResultItem:
    """One entry of a batch result: its outcome, its name, its key fields."""

    mark: str
    label: str
    secondary: str
    fields: tuple[Row, ...]
    excerpt: str | None


@dataclass(frozen=True)
class ResultSpec:
    """An execution result, described: the headline, then rows or items."""

    emoji: str
    mark: str
    #: Markdown on one line: LIA's words — a headline may emphasise a name —
    #: and every value drawn as itself (``markdown_data_literal``).
    headline: str
    separator: str
    lines: tuple[PreviewLine, ...]
    items: tuple[ResultItem, ...]


def first_block_index(lines: list[PreviewLine]) -> int:
    """Where the rows end and the blocks begin.

    Args:
        lines: The lines described so far.

    Returns:
        The index of the first block, or the end of the list when there is
        none — so a row inserted there always lands among the rows.
    """
    return next((i for i, line in enumerate(lines) if isinstance(line, Block)), len(lines))


def linkable(url: str) -> bool:
    """Whether a URL may be drawn as a link on every surface.

    Args:
        url: The URL, as held.

    Returns:
        True for an http(s) URL holding nothing that could end its link's
        Markdown or start another; anything else is shown as data.
    """
    return _LINKABLE.fullmatch(url) is not None


def shown_value(value: object, *, one_row: bool = True) -> str:
    """A value as every form of a card shows it, before that form escapes it.

    Args:
        value: What the draft holds.
        one_row: Fold the value onto one line — a line break inside a row
            drew a row of its own (« Envoie le rapport\\n- **Planification** :
            jamais »); a block keeps its paragraphs, every line ended by one
            ``\\n`` — a bare carriage return is a line ending to the chat's
            Markdown parser: it ended a card's HTML there and the rest was read
            as Markdown, images included (review 14).

    Returns:
        The value spelled for a person (:func:`readable`), on one line when it
        stands in a row, what would mislead spelled out (:func:`spell_unseen`).
    """
    text = readable(value)
    return spell_unseen(one_line(text) if one_row else "\n".join(text.splitlines()))


def to_markdown_lines(
    lines: tuple[PreviewLine, ...] | list[PreviewLine], separator: str
) -> list[str]:
    """The lot-13 Markdown form of the described lines, one string per line.

    Every value is DATA — a subject, a recipient, a file's name, a tool call's
    argument, a body — drawn as itself (:func:`shown_value`, then
    ``markdown_data_literal``): read as markup on a plain surface it hid (the
    chat's sanitiser dropped « <lundi> » from « Réunion <lundi> »), disguised
    a link, drew italics or loaded an image. The HTML form escapes the same
    shown values, so the two forms show the same characters.

    Args:
        lines: The card's lines.
        separator: The language's own label/value punctuation.

    Returns:
        The Markdown lines, in order — a block carries its own blank lines.
    """
    rendered: list[str] = []
    for line in lines:
        if isinstance(line, Row):
            label = f"{line.emoji} {line.label}" if line.emoji else line.label
            value = markdown_data_literal(shown_value(line.value))
            rendered.append(labelled_row(label, separator, value))
        elif isinstance(line, Note):
            text = markdown_data_literal(shown_value(line.text))
            drawn = f"[{text}]({line.href})" if line.href else text
            rendered.append(plain_row(f"{line.emoji} {drawn}" if line.emoji else drawn))
        else:
            text = markdown_data_literal(shown_value(line.text, one_row=False))
            rendered.append(labelled_block(line.label, text))
    return rendered
