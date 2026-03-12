"""
ArticleCard Component - Modern Wikipedia Article Display.

Renders Wikipedia articles with summary and metadata.
Shows full article content with truncation (like email body).
"""

from __future__ import annotations

from typing import Any

from src.core.config import settings
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
)
from src.domains.agents.display.icons import Icons, icon

# Max characters for Wikipedia summary display (centralized in settings)
WIKIPEDIA_SUMMARY_MAX_CHARS = settings.wikipedia_summary_max_chars


class ArticleCard(BaseComponent):
    """
    Modern Wikipedia article card.

    Design:
    - Title + Wikipedia badge at top-right (like Perplexity format)
    - Full summary text with configurable truncation
    - "...voir la suite sur Wikipedia" link when truncated
    - Image thumbnail (if available)
    """

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """Render article as modern card - CSS handles responsive adaptation."""
        # Handle registry item structure (payload nested) or direct data
        item_data = data.get("payload", data) if isinstance(data, dict) else data

        # Extract data - try multiple possible field names
        title = item_data.get("title", "") or item_data.get("name", "")
        url = item_data.get("url", "") or item_data.get("link", "") or item_data.get("fullurl", "")

        # Summary can be in various fields depending on the source
        summary = (
            item_data.get("summary")
            or item_data.get("extract")
            or item_data.get("content")
            or item_data.get("snippet")
            or item_data.get("description")
            or item_data.get("text")
            or ""
        )

        thumbnail = (
            item_data.get("thumbnail")
            or item_data.get("image", "")
            or item_data.get("photo_url", "")
        )
        categories = item_data.get("categories", [])

        # Unified render - CSS handles responsive adaptation
        return self._render_card(title, url, summary, thumbnail, categories, ctx)

    def _render_card(
        self,
        title: str,
        url: str,
        summary: str,
        thumbnail: str,
        categories: list,
        ctx: RenderContext,
    ) -> str:
        """Unified Wikipedia card - CSS handles responsive adaptation.

        Layout (user requirement):
        1. Badge Wikipedia (first line)
        2. Title (second line)
        3. Separator (CSS border)
        4. Content
        """
        nested_class = self._nested_class(ctx)
        max_chars = WIKIPEDIA_SUMMARY_MAX_CHARS
        is_truncated = len(summary) > max_chars
        summary_text = summary[:max_chars] if is_truncated else summary

        # Always show link to Wikipedia article
        read_more_label = V3Messages.get_read_more_on_wikipedia(ctx.language)
        link_prefix = "..." if is_truncated else ""
        read_more_html = (
            f'<a href="{escape_html(url)}" class="lia-article__read-more" target="_blank">{link_prefix}{read_more_label}</a>'
            if url
            else ""
        )

        # Thumbnail (CSS hides on mobile)
        thumb_html = ""
        if thumbnail:
            thumb_html = f"""<div class="lia-article__thumb">
  <img src="{escape_html(thumbnail)}" alt="" loading="lazy">
</div>"""

        # Categories (CSS hides on mobile)
        cats_html = ""
        if categories:
            cat_badges = [
                f'<span class="lia-badge lia-badge--subtle">{escape_html(c)}</span>'
                for c in categories[:3]
            ]
            cats_html = f'<div class="lia-article__categories">{" ".join(cat_badges)}</div>'

        return f"""<div class="lia-card lia-article {nested_class}">
  {thumb_html}
  <div class="lia-article__content">
    <div class="lia-badge-row">
      <span class="lia-badge lia-badge--accent">{icon(Icons.ARTICLE)} Wikipedia</span>
    </div>
    <div class="lia-title-row">
      <span class="lia-title-row__text">{escape_html(title)}</span>
    </div>
    <div class="lia-article__body">
      <p class="lia-article__summary">{escape_html(summary_text)}</p>
      {read_more_html}
    </div>
    {cats_html}
  </div>
</div>"""
