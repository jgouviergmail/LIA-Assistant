"""The ``lia-card`` form of a described draft card, and which surface gets it (ADR-289).

The chat draws data as ``lia-card`` HTML cards; a draft about to become one of
those data is drawn the same way, from the same description the Markdown form
is drawn from (:mod:`~src.domains.agents.drafts.card_spec`). The classes are
the ones the data cards already use — the stylesheet knows them and the
sanitiser lets them through — and every value is escaped: a subject is data,
never markup.

A surface that renders no markup keeps the Markdown form: a ticket comment
(escaped text flattened by
:func:`~src.domains.agents.display.plain_text.markdown_to_plain_text`), an
external channel (Telegram strips every card from the first ``<div``), a
person who chose the ``markdown`` rendering. The surface is decided by the
RUN, not by a caller's guess — see :func:`card_surface`.
"""

from __future__ import annotations

from enum import StrEnum

from src.core.constants import RESPONSE_DISPLAY_MODE_MARKDOWN
from src.domains.agents.api.run_origin import out_of_turn_origin_ctx, plain_surface_ctx
from src.domains.agents.context.runtime_context import runtime_display_mode
from src.domains.agents.display.components.base import (
    compact_html,
    escape_html,
    render_desc_block,
    render_section_header,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.drafts.card_spec import (
    Block,
    CardSpec,
    Note,
    ResultItem,
    ResultSpec,
    Row,
)
from src.domains.agents.drafts.markdown_grammar import readable

__all__ = ["CardSurface", "card_surface", "to_html_card", "to_html_result"]


class CardSurface(StrEnum):
    """Where a card is drawn, which decides its form."""

    CHAT = "chat"  # renders HTML: the lia-card form
    PLAIN = "plain"  # renders no markup: the lot-13 Markdown form


def card_surface() -> CardSurface:
    """The surface of the current run, decided by the run, never by a caller.

    Plain — the lot-13 Markdown — for a ticket run (its out-of-turn origin
    says it), for an external channel (its handler declares
    ``plain_surface_ctx`` around the stream), and for a person who chose the
    ``markdown`` rendering (they asked for text). The chat's ``lia-card``
    otherwise.

    Returns:
        The surface.
    """
    if out_of_turn_origin_ctx.get() is not None or plain_surface_ctx.get():
        return CardSurface.PLAIN
    if runtime_display_mode() == RESPONSE_DISPLAY_MODE_MARKDOWN:
        return CardSurface.PLAIN
    return CardSurface.CHAT


#: The icon a labelled row wears, by the field key the renderer named
#: (``DRAFT_PREVIEW_LABELS`` keys). A key with no entry draws no icon.
_ROW_ICONS: dict[str, str] = {
    "to": Icons.PERSON,
    "cc": Icons.GROUP,
    "bcc": Icons.GROUP,
    "recipient": Icons.PERSON,
    "from": Icons.PERSON,
    "callee": Icons.PHONE,
    "subject": Icons.TEXT,
    "date": Icons.CALENDAR,
    "attachments": Icons.ATTACHMENT,
    "event": Icons.EVENT,
    "start": Icons.SCHEDULE,
    "end": Icons.SCHEDULE,
    "location": Icons.LOCATION,
    "attendees": Icons.GROUP,
    "video_conference": Icons.VIDEO_CALL,
    "contact": Icons.PERSON,
    "email": Icons.EMAIL,
    "phone": Icons.PHONE,
    "organization": Icons.WORK,
    "task": Icons.TASK,
    "due": Icons.CALENDAR,
    "title": Icons.TASK,
    "file": Icons.FILE,
    "sheet": Icons.SPREADSHEET,
    "range": Icons.SPREADSHEET,
    "changes": Icons.EDIT,
    "type": Icons.INFO,
    "label": Icons.LABEL,
    "label_parent": Icons.LABEL,
    "sublabels_to_delete": Icons.LABEL,
    "sublabels_included": Icons.LABEL,
    "objective": Icons.INFO,
    "schedule": Icons.SCHEDULE,
    "instruction": Icons.TEXT,
    "server": Icons.SETTINGS,
    "tool": Icons.EXTENSION,
    "details": Icons.INFO,
    "context": Icons.INFO,
    "query": Icons.SEARCH,
    "filter_archive": Icons.ARCHIVE,
    "filter_mark_read": Icons.MARK_EMAIL_READ,
}


def _row_html(row: Row, separator: str) -> str:
    icon_name = _ROW_ICONS.get(row.key or "")
    icon = (
        f'<span class="material-symbols-outlined">{escape_html(icon_name)}</span>'
        if icon_name
        else ""
    )
    text = f"<strong>{escape_html(row.label)}</strong>{escape_html(separator)}{escape_html(readable(row.value))}"
    return f'<div class="lia-d-row">{icon}<span>{text}</span></div>'


def _note_html(note: Note) -> str:
    return f'<div class="lia-d-row"><span>{escape_html(note.text)}</span></div>'


def _block_html(block: Block) -> str:
    text = "<br>".join(escape_html(line) for line in block.text.split("\n"))
    return render_section_header(block.label, Icons.DESCRIPTION, "indigo") + render_desc_block(
        text, with_border=False
    )


#: The illustration colour of a result, by its outcome mark.
_MARK_COLORS: dict[str, str] = {"✅": "green", "⚠️": "amber", "🚫": "gray", "❌": "red"}


def _card_top(emoji: str, title: str, color: str) -> str:
    return (
        '<div class="lia-card-top">'
        f'<div class="lia-illus lia-illus--{color}"><span style="font-size:var(--lia-text-lg)">{escape_html(emoji)}</span></div>'
        '<div class="lia-card-top__info">'
        f'<div class="lia-card-top__title">{escape_html(title)}</div>'
        "</div></div>"
    )


def _lines_html(lines: tuple[Row | Note | Block, ...], separator: str) -> list[str]:
    parts: list[str] = []
    for line in lines:
        if isinstance(line, Row):
            parts.append(_row_html(line, separator))
        elif isinstance(line, Note):
            parts.append(_note_html(line))
        else:
            parts.append(_block_html(line))
    return parts


def _item_html(item: ResultItem, separator: str, first: bool) -> str:
    first_class = " lia-sec--first" if first else ""
    title = f"{item.mark} {item.label}".strip()
    if item.secondary:
        title += f" — {item.secondary}"
    parts = [
        f'<div class="lia-sec{first_class}"><span class="lia-sec__label">{escape_html(title)}</span></div>'
    ]
    parts.extend(_row_html(row, separator) for row in item.fields)
    if item.excerpt:
        parts.append(render_desc_block(escape_html(item.excerpt), with_border=False))
    return "".join(parts)


def to_html_result(spec: ResultSpec) -> str:
    """Draw a described execution result as the chat's ``lia-card``.

    Args:
        spec: The result's description.

    Returns:
        One line of HTML: the outcome on top, then the single result's rows
        and blocks, or one section per batch item with its key fields.
    """
    color = _MARK_COLORS.get(spec.mark, "indigo")
    # The illustration wears the family's emoji and the title its mark; with
    # no family (an unknown type), the mark moves to the illustration.
    title = f"{spec.mark} {spec.headline}".strip() if spec.emoji else spec.headline
    top = _card_top(spec.emoji or spec.mark, title, color)
    parts = _lines_html(spec.lines, spec.separator)
    parts.extend(
        _item_html(item, spec.separator, first=index == 0) for index, item in enumerate(spec.items)
    )
    return compact_html(f'<div class="lia-card lia-draft-result">{top}{"".join(parts)}</div>')


def to_html_card(spec: CardSpec) -> str:
    """Draw a described card as the chat's ``lia-card``.

    Args:
        spec: The card's description.

    Returns:
        One line of HTML: the emoji and the title on top, the rows and notes as
        detail rows, each block as a section over a description block.
    """
    top = _card_top(spec.emoji, spec.title, "indigo")
    parts = _lines_html(spec.lines, spec.separator)
    return compact_html(f'<div class="lia-card lia-draft">{top}{"".join(parts)}</div>')
