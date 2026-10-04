"""Wikipedia content: full received text, progressive details and truthful sources."""

from collections.abc import Mapping

from src.core.config import settings
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.article_details import (
    article_categories,
    article_metadata,
    article_sections,
)
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    render_card_top,
    render_chip,
    wrap_with_response,
)
from src.domains.agents.display.components.card_content import (
    render_details,
    render_folded_text,
    render_linked_title,
    render_text_content,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.urls import safe_image_url
from src.domains.agents.display.values import first_present, scalar_text

WIKIPEDIA_SUMMARY_MAX_CHARS = settings.wikipedia_summary_max_chars


class ArticleCard(BaseComponent):
    def render(
        self,
        data: dict[str, object],
        ctx: RenderContext,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        raw = data.get("payload", data)
        item: Mapping[str, object] = raw if isinstance(raw, dict) else {}
        title = first_present(item, "title", "name")
        url = first_present(item, "url", "link", "fullurl")
        text = first_present(
            item, "summary", "extract", "content", "snippet", "description", "text"
        )
        top = render_card_top(
            "menu_book",
            "purple",
            render_linked_title(title, url),
            badges_html=render_chip("Wikipedia", "indigo", Icons.ARTICLE),
        )
        body = render_folded_text(
            text,
            ctx,
            preview_chars=min(
                WIKIPEDIA_SUMMARY_MAX_CHARS, settings.web_search_synthesis_preview_chars
            ),
        )
        full_content = scalar_text(item.get("content"))
        if full_content and full_content != scalar_text(text):
            body += render_details(render_text_content(full_content), ctx)
        image = first_present(item, "thumbnail", "image", "photo_url")
        if isinstance(image, dict):
            image = image.get("source")
        target = safe_image_url(scalar_text(image))
        thumbnail = (
            f'<div class="lia-article__thumb"><img src="{target}" alt="" loading="lazy"></div>'
            if target
            else ""
        )
        read_more = (
            render_linked_title(
                V3Messages.get_read_more_on_wikipedia(ctx.language),
                url,
                class_name="lia-article__read-more",
            )
            if safe_image_url(scalar_text(url))
            else ""
        )
        card = f'<div class="lia-card lia-article {self._nested_class(ctx)}">{top}{thumbnail}<div class="lia-article__body">{body}{read_more}</div>{article_metadata(item, ctx)}{article_sections(item, ctx)}{article_categories(item.get("categories"), ctx)}</div>'
        return wrap_with_response(
            card_html=card,
            domain="wikipedia",
            with_top_separator=is_first_item,
            with_bottom_separator=is_last_item,
        )
