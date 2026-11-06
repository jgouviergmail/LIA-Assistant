"""The words a confirmation card is written in (ADR-289): rows, notes, blocks.

Every per-type renderer of ``preview_renderer`` describes its card with these:
a field under its localized label, a line with no label, a text keeping its
paragraphs, and the update pattern — the new value marked ✏️, else the value
kept. The form (a Markdown item, a ``lia-card`` row) is drawn later by the
surface's serializer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.domains.agents.drafts.card_spec import Block, Note, Row

#: Formats an ISO date or datetime for display, or "" for a falsy input — bound
#: to the person's language and timezone by ``render_detailed_preview``.
FormatDt = Callable[[str | None], str]


def row(lbl: dict[str, str], key: str, value: object) -> Row:
    """One field of a card, described under its localized label.

    The form — a Markdown list item, a ``lia-card`` key/value row — is drawn
    later by the surface's serializer (ADR-289); the grammar every surface
    shares lives in :mod:`~src.domains.agents.drafts.markdown_grammar`.

    Args:
        lbl: The localized labels.
        key: Which field this row is.
        value: What to show for it.

    Returns:
        The described row.
    """
    return Row(lbl[key], value, key=key)


def note(text: str) -> Note:
    """A line with no label: a statement, or one line of data.

    Args:
        text: The line, already localized or already rendered.

    Returns:
        The described note.
    """
    return Note(text)


def block(lbl: dict[str, str], key: str, text: str) -> Block:
    """A field whose value is a TEXT carrying its own paragraphs.

    Args:
        lbl: The localized labels.
        key: Which field this block is.
        text: The value, newlines and all.

    Returns:
        The described block.
    """
    return Block(lbl[key], text)


def format_day(raw: str, format_dt: FormatDt) -> str:
    """A day as the card shows it, in the reader's language.

    Args:
        raw: An ISO day, or ``--MM-DD`` when the contact holds no year.
        format_dt: The card's formatter, which keeps a date a date.

    Returns:
        The day; a day with no year as it was written.
    """
    return raw.removeprefix("--") if raw.startswith("--") else format_dt(raw)


def updated_row(
    lbl: dict[str, str], key: str, new_value: str | None, current_value: str
) -> Row | None:
    """Render an update-preview row showing the new value or the current one.

    Args:
        lbl: The localized labels.
        key: Which field this row is.
        new_value: Value from the draft content (``None``/empty = unchanged).
        current_value: Value read from the current resource snapshot.

    Returns:
        The formatted row (suffixed with `` ✏️`` when the field is modified),
        or ``None`` when both values are empty and the row must be omitted.
    """
    value = new_value or current_value
    if not value:
        return None
    mark = " ✏️" if new_value else ""
    return row(lbl, key, f"{value}{mark}")


def updated_datetime_row(
    lbl: dict[str, str],
    key: str,
    new_raw: str | None,
    current_raw: str,
    format_dt: FormatDt,
) -> Row | None:
    """Render an update-preview datetime row (new value marked, else current).

    Args:
        lbl: The localized labels.
        key: Which field this row is.
        new_raw: Raw ISO datetime from the draft content, if modified.
        current_raw: Raw ISO datetime from the current resource snapshot.
        format_dt: Localized datetime formatter.

    Returns:
        The formatted row, or ``None`` when neither value is set.
    """
    value = format_dt(new_raw) if new_raw else format_dt(current_raw) if current_raw else ""
    if not value:
        return None
    mark = " ✏️" if new_raw else ""
    return row(lbl, key, f"{value}{mark}")


def first_item_value(items: list[dict[str, Any]], key: str, default: str = "") -> str:
    """Return ``items[0][key]`` with a default for empty lists or missing keys.

    Mirrors the Google People API shape (``names``, ``emailAddresses``, ...)
    where the first entry is the primary value.
    """
    return items[0].get(key, default) if items else default


__all__ = [
    "FormatDt",
    "block",
    "first_item_value",
    "note",
    "row",
    "updated_datetime_row",
    "updated_row",
]
