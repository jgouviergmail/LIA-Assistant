"""What a draft card SAYS, described once and drawn per surface (ADR-289).

A confirmation card was Markdown by construction: the per-type renderers
produced Markdown lines, so Markdown was the only form the card could take,
on every surface. The chat, however, draws data as ``lia-card`` HTML cards —
and a draft about to become one of those data deserves the same care.

So the renderers now DESCRIBE the card and a serializer draws it:

- :class:`Row` — one labelled field (« Destinataire : paul@… »);
- :class:`Note` — one line with no label (a spreadsheet row, a remainder);
- :class:`Block` — a labelled TEXT carrying its own paragraphs (a body);
- :class:`CardSpec` — the emoji, the title and the lines, plus the language's
  own label/value separator.

:func:`to_markdown_lines` is the lot-13 grammar, byte for byte: the golden
characterization net (``test_detailed_preview_characterization.py``) is the
oracle that the description changed nothing of the Markdown form. The HTML
form lives in :mod:`~src.domains.agents.drafts.card_html`.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domains.agents.drafts.markdown_grammar import (
    labelled_block,
    labelled_row,
    plain_row,
)

__all__ = [
    "Block",
    "CardSpec",
    "Note",
    "PreviewLine",
    "ResultItem",
    "ResultSpec",
    "Row",
    "first_block_index",
    "to_markdown_lines",
]


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
    """One line with no label: a statement, or one line of data."""

    text: str


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


def to_markdown_lines(
    lines: tuple[PreviewLine, ...] | list[PreviewLine], separator: str
) -> list[str]:
    """The lot-13 Markdown form of the described lines, one string per line.

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
            rendered.append(labelled_row(label, separator, line.value))
        elif isinstance(line, Note):
            rendered.append(plain_row(line.text))
        else:
            rendered.append(labelled_block(line.label, line.text))
    return rendered
