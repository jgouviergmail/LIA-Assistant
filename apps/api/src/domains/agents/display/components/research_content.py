"""Shared research sources, complete snippets and progressive lists."""

from collections.abc import Mapping
from contextlib import suppress
from urllib.parse import urlsplit

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    render_collapsible,
    render_section_header,
)
from src.domains.agents.display.components.card_content import (
    render_folded_text,
    render_linked_title,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.urls import safe_image_url
from src.domains.agents.display.values import first_present, list_values, scalar_text


def render_research_list(items: list[str], ctx: RenderContext, *, preview: int = 4) -> str:
    if not items:
        return ""
    lead = f'<ol class="lia-research-list">{"".join(items[:preview])}</ol>'
    if len(items) <= preview:
        return lead
    return lead + render_collapsible(
        trigger_text=f"{V3Messages.get_see_more(ctx.language)} (+{len(items) - preview})",
        content_html=f'<ol class="lia-research-list" start="{preview + 1}">{"".join(items[preview:])}</ol>',
        with_separator=False,
    )


def research_sources(value: object, ctx: RenderContext) -> str:
    items = []
    for index, source in enumerate(list_values(value), 1):
        url = scalar_text(source)
        if not (target := safe_image_url(url)):
            continue
        try:
            domain = urlsplit(url).hostname or url
        except ValueError:
            domain = url
        items.append(
            f'<li value="{index}"><a class="lia-research-source" href="{target}" target="_blank" rel="noopener noreferrer">{escape_html(domain)}<span class="lia-card__meta">{escape_html(url)}</span></a></li>'
        )
    return (
        render_section_header(V3Messages.get_sources(ctx.language), Icons.LINK, "indigo")
        + render_research_list(items, ctx)
        if items
        else ""
    )


def research_questions(value: object, ctx: RenderContext) -> str:
    items = [
        f"<li>{escape_html(text)}</li>"
        for question in list_values(value)
        if (text := scalar_text(question))
    ]
    return (
        render_section_header(
            V3Messages.get_related_questions(ctx.language), "help_outline", "indigo"
        )
        + render_research_list(items, ctx, preview=3)
        if items
        else ""
    )


def research_result(data: Mapping[str, object], ctx: RenderContext) -> str:
    title = render_linked_title(
        data.get("title"), data.get("url"), class_name="lia-web-search__result-title"
    )
    text = render_folded_text(first_present(data, "snippet", "description"), ctx, preview_chars=180)
    return f'<div class="lia-web-search__result">{title}{research_identity(data)}{text}</div>'


def research_identity(data: Mapping[str, object]) -> str:
    parts = []
    url = scalar_text(data.get("url"))
    if safe_image_url(url):
        with suppress(ValueError):
            if host := urlsplit(url).hostname:
                parts.append(host)
    brands = {"brave": "Brave", "perplexity": "Perplexity", "wikipedia": "Wikipedia"}
    source = scalar_text(data.get("source"))
    if source in brands:
        parts.append(brands[source])
    if age := scalar_text(data.get("age")):
        parts.append(age)
    return f'<p class="lia-card__meta">{escape_html(" · ".join(parts))}</p>' if parts else ""
