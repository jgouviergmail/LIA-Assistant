"""Unified research presentation, retaining every supplied result and source."""

from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import (
    WEB_SEARCH_SOURCE_BRAVE,
    WEB_SEARCH_SOURCE_PERPLEXITY,
    WEB_SEARCH_SOURCE_WIKIPEDIA,
)
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    render_card_top,
    render_chip,
    render_section_header,
    wrap_with_response,
)
from src.domains.agents.display.components.card_content import (
    render_folded_text,
    render_linked_title,
)
from src.domains.agents.display.components.folded_synthesis import render_folded_synthesis
from src.domains.agents.display.components.research_content import (
    render_research_list,
    research_questions,
    research_result,
    research_sources,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import list_values, scalar_text


class WebSearchCard(BaseComponent):
    def render(
        self,
        data: dict[str, object],
        ctx: RenderContext,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        brands = {
            WEB_SEARCH_SOURCE_PERPLEXITY: ("Perplexity", Icons.AI),
            WEB_SEARCH_SOURCE_BRAVE: ("Brave", Icons.WEB),
            WEB_SEARCH_SOURCE_WIKIPEDIA: ("Wikipedia", Icons.BOOK),
        }
        used = list_values(data.get("sources_used"))
        badges = "".join(
            render_chip(label, "indigo", symbol)
            for source, (label, symbol) in brands.items()
            if source in used
        )
        top = render_card_top(
            "travel_explore",
            "blue",
            render_linked_title(data.get("query"), None),
            badges_html=badges,
        )
        content = []
        if synthesis := scalar_text(data.get("synthesis")):
            content.append(
                render_section_header(
                    V3Messages.get_ai_synthesis(ctx.language), Icons.AI, "indigo", first=True
                )
                + render_folded_synthesis(
                    synthesis, ctx, citations=list_values(data.get("citations"))
                )
            )
        wiki = data.get("wikipedia")
        if isinstance(wiki, dict):
            content.append(
                render_section_header("Wikipedia", Icons.BOOK, "indigo")
                + render_linked_title(wiki.get("title"), wiki.get("url"))
                + render_folded_text(wiki.get("summary"), ctx, preview_chars=300)
            )
        content.extend(
            (
                research_sources(data.get("citations"), ctx),
                research_questions(data.get("related_questions"), ctx),
            )
        )
        results = [
            f"<li>{research_result(result, ctx)}</li>"
            for result in list_values(data.get("results"))
            if isinstance(result, dict)
        ]
        if results:
            content.append(
                render_section_header(V3Messages.get_web_results(ctx.language), Icons.WEB, "indigo")
                + render_research_list(results, ctx)
            )
        card = f'<div class="lia-card lia-web-search {self._nested_class(ctx)}">{top}{"".join(content)}</div>'
        return wrap_with_response(
            card_html=card,
            domain="web_search",
            with_top_separator=is_first_item,
            with_bottom_separator=is_last_item,
        )
