"""Research answer and individual result cards share full, safe details."""

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    render_card_top,
    render_chip,
    wrap_with_response,
)
from src.domains.agents.display.components.card_content import (
    render_folded_text,
    render_linked_title,
)
from src.domains.agents.display.components.folded_synthesis import render_folded_synthesis
from src.domains.agents.display.components.research_content import (
    research_identity,
    research_questions,
    research_sources,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import first_present, list_values, scalar_text


class SearchResultCard(BaseComponent):
    def render(
        self,
        data: dict[str, object],
        ctx: RenderContext,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        if "answer" in data:
            title = first_present(data, "query", "search_term", "question")
            badge = render_chip(V3Messages.get_internet(ctx.language), "indigo", Icons.SEARCH)
            body = render_folded_synthesis(
                scalar_text(data.get("answer")), ctx, citations=list_values(data.get("citations"))
            )
            body += research_sources(data.get("citations"), ctx) + research_questions(
                data.get("related_questions"), ctx
            )
            variant = "lia-search--answer"
        else:
            title = data.get("title")
            badge = ""
            body = render_folded_text(
                first_present(data, "snippet", "description"), ctx, preview_chars=180
            )
            variant = ""
        top = render_card_top(
            "search", "blue", render_linked_title(title, data.get("url")), badges_html=badge
        )
        card = f'<div class="lia-card lia-search {variant} {self._nested_class(ctx)}">{top}{research_identity(data)}<div class="lia-search__answer">{body}</div></div>'
        return wrap_with_response(
            card_html=card,
            domain="search",
            with_top_separator=is_first_item,
            with_bottom_separator=is_last_item,
        )
