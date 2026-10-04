"""Shared parent and child ticket summary presentation."""

from typing import Any

from src.core.i18n_cards import CardLabel, card_label
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_date,
    render_chip,
    render_chip_row,
    render_d_item,
)
from src.domains.agents.display.ticket_labels import ticket_status_label
from src.domains.agents.display.values import scalar_text
from src.domains.workboard.constants import AssigneeKind, TicketPriority, TicketStatus


def ticket_core_fields(data: dict[str, Any], ctx: RenderContext) -> str:
    chips: list[str] = []
    status = scalar_text(data.get("status"))
    if status in TicketStatus:
        chips.append(
            render_chip(
                ticket_status_label(TicketStatus(status), ctx.language),
                "green" if status == TicketStatus.DONE else "indigo",
            )
        )
    priority = scalar_text(data.get("priority"))
    if priority in TicketPriority:
        label = (
            card_label("urgent", ctx.language)
            if priority == TicketPriority.URGENT
            else V3Messages.get_priority(ctx.language, priority)
        )
        chips.append(
            render_chip(
                label,
                (
                    "red"
                    if priority in ("high", "urgent")
                    else "amber" if priority == "medium" else "indigo"
                ),
                "flag",
            )
        )
    assignee = scalar_text(data.get("assignee_kind"))
    if assignee in AssigneeKind:
        chips.append(
            render_chip(
                "LIA" if assignee == AssigneeKind.LIA else card_label("person", ctx.language),
                "indigo",
                "person",
            )
        )
    dates = ""
    date_fields: tuple[tuple[str, CardLabel], ...] = (("start_at", "start"), ("due_at", "due"))
    for key, label_key in date_fields:
        value = scalar_text(data.get(key))
        if value:
            label = card_label(label_key, ctx.language)
            date = format_date(
                value, ctx.language, ctx.timezone, format_type="short", include_time=True
            )
            dates += render_d_item(
                "schedule",
                f"{escape_html(label)}{label_separator(ctx.language)}{escape_html(date)}",
            )
    return render_chip_row(" ".join(chips)) + dates
