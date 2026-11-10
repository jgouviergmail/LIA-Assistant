"""Research answer and individual result cards share full, safe details."""

from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    render_card_top,
    render_chip,
    render_collapsible,
    wrap_with_response,
)
from src.domains.agents.display.components.card_content import (
    render_folded_text,
    render_linked_title,
    render_text_content,
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
            context = scalar_text(data.get("context"))
            if context:
                body += render_collapsible(
                    trigger_text=card_label("research_context", ctx.language),
                    content_html=render_text_content(context),
                    with_separator=False,
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
        identity = research_identity(data)
        provenance = f'<div class="lia-search__provenance">{identity}</div>' if identity else ""
        card = (
            f'<div class="lia-card lia-search {variant} {self._nested_class(ctx)}">'
            f'{provenance}<div class="lia-search__clipping">{top}'
            f'<div class="lia-search__answer">{body}</div></div></div>'
        )
        return wrap_with_response(
            card_html=card,
            domain="search",
            with_top_separator=is_first_item,
            with_bottom_separator=is_last_item,
        )
