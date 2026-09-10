"""The one Markdown vocabulary every draft-facing surface speaks (ADR-276 lot 13).

A draft is shown twice: BEFORE, as the confirmation card a person approves, and
AFTER, as the result of what they approved. Lot 13 gave the first one a single
vocabulary — Markdown list items, a language-carried separator, no ``<br/>`` —
and left the second one in HTML, so the same email read as a clean list on the
card and as a stack of blank lines in the answer (measured on production,
2026-09-09: ``supprimé\\n<br/>🗂️ **Titre** : …``, one blank line per field, the
tag itself read out verbatim on the ticket comment that quotes it).

The grammar therefore lives here rather than inside either renderer, so the two
cannot drift again:

- :func:`readable` — a value spelled for a person, never for Python;
- :func:`labelled_row` — one field, as a list item;
- :func:`plain_row` — one line with no label;
- :func:`labelled_block` — a value that carries its own paragraphs.

Why a list rather than hard breaks: the chat renders Markdown with no
hard-break plugin, so a list is what keeps one field per line without markup of
its own, and a surface that renders NEITHER (a ticket comment is escaped text)
can flatten Markdown into something readable through
:func:`~src.domains.agents.display.plain_text.markdown_to_plain_text`, where a
``<br/>`` was read out as typed.

The separator between a label and its value is NOT a literal here: it travels
with the labels (``DRAFT_PREVIEW_LABELS[lang]["separator"]``), because a ``": "``
in the code published French punctuation in six languages — an unbreakable
space before a French colon, a full-width colon in Chinese.
"""

from __future__ import annotations

__all__ = ["labelled_block", "labelled_row", "plain_row", "readable"]


def readable(value: object) -> str:
    """One value, spelled for a person rather than for Python.

    A row's value comes from a draft's stored content, and nothing guarantees
    it is a string: a recipient list rendered ``['paul@example.org']`` — the
    brackets, the quotes and all — on a card asking someone to approve sending
    it. Same doctrine as the tool-argument renderer: what is shown is data,
    never a Python spelling.

    A mapping is deliberately NOT joined: iterating it yields its KEYS, so a
    join would state something the content never said.

    Args:
        value: Whatever the content held under that key.

    Returns:
        The value as text: a sequence joined, everything else stringified.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return ", ".join(readable(item) for item in value)
    return str(value)


def labelled_row(label: str, separator: str, value: object) -> str:
    """One field, as a Markdown list item.

    Args:
        label: The field's localized name.
        separator: The language's own label/value punctuation.
        value: What to show for it; passed through :func:`readable`.

    Returns:
        The row.
    """
    return f"- **{label}**{separator}{readable(value)}"


def plain_row(text: str) -> str:
    """A line with no label: a statement, or one line of data.

    Args:
        text: The line, already localized or already rendered.

    Returns:
        The row, in the same list as the labelled ones.
    """
    return f"- {text}"


def labelled_block(label: str, text: str) -> str:
    """A field whose value is a TEXT: its own paragraph under a bold lead.

    An email body is not a field value — it carries its own paragraphs, and
    folding it into a list item either loses them or breaks the list. It
    therefore leaves the list and stands on its own, which is also how a
    reader wants to read the words they are about to send.

    Args:
        label: The field's localized name.
        text: The value, newlines and all.

    Returns:
        The block, carrying the blank lines that separate it from its
        neighbours — so the join stays a plain newline for every row.
    """
    return f"\n**{label}**\n\n{text}\n"
