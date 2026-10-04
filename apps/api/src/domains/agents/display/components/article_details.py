"""Supplied Wikipedia metadata and section headings, with no remote reads."""

from collections.abc import Mapping

from src.core.i18n_cards import CardLabel, card_label
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    render_collapsible,
    render_kv_rows,
    render_section_header,
)
from src.domains.agents.display.components.research_content import render_research_list
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import list_values, nonnegative_integer, scalar_text


def article_metadata(data: Mapping[str, object], ctx: RenderContext) -> str:
    fields: list[tuple[CardLabel, str]] = [("article_language", scalar_text(data.get("language")))]
    keys: list[tuple[str, CardLabel]] = [
        ("page_id", "article_page"),
        ("content_length", "article_length"),
    ]
    for key, label in keys:
        if (value := nonnegative_integer(data.get(key))) is not None:
            fields.append((label, str(value)))
    pairs = [(card_label(label, ctx.language), value) for label, value in fields if value]
    return render_kv_rows(pairs) if pairs else ""


def article_sections(data: Mapping[str, object], ctx: RenderContext) -> str:
    sections = [
        f"<li>{escape_html(title)}</li>"
        for section in list_values(data.get("sections"))
        if isinstance(section, dict) and (title := scalar_text(section.get("title")))
    ]
    if not sections:
        return ""
    return render_section_header(
        card_label("article_sections", ctx.language), Icons.ARTICLE, "indigo"
    ) + render_research_list(sections, ctx)


def article_categories(value: object, ctx: RenderContext) -> str:
    categories = [escape_html(text) for item in list_values(value) if (text := scalar_text(item))]
    if not categories:
        return ""
    badges = "".join(
        f'<span class="lia-badge lia-badge--subtle">{text}</span>' for text in categories
    )
    return render_collapsible(
        trigger_text=f'{card_label("article_categories", ctx.language)} ({len(categories)})',
        content_html=f'<div class="lia-article__categories">{badges}</div>',
        with_separator=False,
    )
