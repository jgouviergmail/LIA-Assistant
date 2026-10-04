"""Full received ticket details, kept outside the recurring model summary."""

from collections.abc import Mapping

from src.core.i18n_cards import card_label
from src.core.i18n_drafts import label_separator
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_date,
    render_d_item,
    render_section_header,
)
from src.domains.agents.display.components.card_content import render_details, render_text_content
from src.domains.agents.display.components.folded_synthesis import split_lead
from src.domains.agents.display.components.ticket_fields import ticket_core_fields
from src.domains.agents.display.ticket_run_labels import (
    ticket_author_label,
    ticket_outcome_label,
    ticket_run_error_label,
)
from src.domains.agents.display.values import (
    list_values,
    nonnegative_integer,
    nonnegative_number,
    scalar_text,
)


def _ticket_children(values: object, ctx: RenderContext) -> str:
    children = [child for child in list_values(values) if isinstance(child, dict)]
    if not children:
        return ""
    rows = [
        f'<li><strong>{escape_html(scalar_text(child.get("title")))}</strong>{ticket_core_fields(child, ctx)}</li>'
        for child in children
    ]
    return (
        render_section_header(card_label("steps", ctx.language), "checklist", "indigo")
        + '<ol class="lia-ticket-items">'
        + "".join(rows)
        + "</ol>"
    )


def _ticket_comments(values: object, ctx: RenderContext) -> str:
    rows: list[str] = []
    for comment in list_values(values):
        if not isinstance(comment, dict) or not scalar_text(comment.get("body")):
            continue
        kind = scalar_text(comment.get("author"))
        author = (
            card_label("person", ctx.language)
            if kind == "user"
            else ticket_author_label(kind, ctx.language)
        )
        rows.append(
            f'<li><strong>{escape_html(author)}</strong>{render_text_content(comment["body"])}</li>'
        )
    if not rows:
        return ""
    return (
        render_section_header(card_label("comments", ctx.language), "forum", "indigo")
        + '<ul class="lia-ticket-items">'
        + "".join(rows)
        + "</ul>"
    )


def _run_counts(value: dict[str, object], ctx: RenderContext) -> str:
    rows: list[str] = []
    if (cost := nonnegative_number(value.get("cost_eur"))) is not None:
        rows.append(
            render_d_item(
                "payments",
                escape_html(
                    f'{card_label("cost", ctx.language)}{label_separator(ctx.language)}{cost:.6g} €'
                ),
            )
        )
    for key in ("tokens_in", "tokens_out"):
        count = nonnegative_integer(value.get(key))
        if count is not None and (text := scalar_text(count)):
            rows.append(
                render_d_item(
                    "data_usage",
                    escape_html(
                        f"{card_label(key, ctx.language)}{label_separator(ctx.language)}{text}"
                    ),
                )
            )
    return "".join(rows)


def _ticket_last_run(value: object, ctx: RenderContext) -> str:
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    outcome = ticket_outcome_label(scalar_text(value.get("outcome")), ctx.language)
    if outcome:
        parts.append(render_d_item("history", escape_html(outcome)))
    if date := scalar_text(value.get("at")):
        parts.append(
            render_d_item(
                "schedule",
                escape_html(
                    format_date(
                        date, ctx.language, ctx.timezone, format_type="short", include_time=True
                    )
                ),
            )
        )
    if error := ticket_run_error_label(scalar_text(value.get("error")), ctx.language):
        parts.append(render_d_item("error", escape_html(error)))
    parts.append(_run_counts(value, ctx))
    content = "".join(parts)
    return (
        render_section_header(card_label("last_run", ctx.language), "history", "indigo") + content
        if content
        else ""
    )


def render_ticket_details(data: Mapping[str, object], ctx: RenderContext) -> str:
    lead, rest = split_lead(scalar_text(data.get("description")), preview_chars=240)
    content = (
        render_text_content(rest)
        + _ticket_children(data.get("children"), ctx)
        + _ticket_comments(data.get("comments"), ctx)
        + _ticket_last_run(data.get("last_run"), ctx)
    )
    return render_text_content(lead) + render_details(content, ctx)
