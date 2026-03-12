"""
SearchResultCard Component - Modern Search Result Display.

Renders Perplexity/web search results with sources.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    truncate,
)
from src.domains.agents.display.icons import Icons, icon


class SearchResultCard(BaseComponent):
    """
    Modern search result card.

    Design:
    - Answer text (main content)
    - Sources as compact links
    - Related questions (expandable)
    - Perplexity branding
    """

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """Render search result as modern card."""
        # Check if it's an answer result or standard result
        if "answer" in data:
            return self._render_answer(data, ctx)
        else:
            return self._render_result(data, ctx)

    def _render_answer(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render Perplexity-style answer with sources (Wikipedia format)."""
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        related_questions = data.get("related_questions", [])
        query = data.get("query", "") or data.get("search_term", "")

        nested_class = self._nested_class(ctx)

        # Sources with spacing below label
        sources_html = ""
        if citations:
            source_items = []
            for url in citations[:5]:
                domain = self._extract_domain(url)
                source_items.append(
                    f'<a href="{escape_html(url)}" class="lia-source" target="_blank">'
                    f'<span class="lia-source__icon">{icon(Icons.LINK)}</span>'
                    f'<span class="lia-source__domain">{escape_html(domain)}</span>'
                    f"</a>"
                )
            sources_label = V3Messages.get_sources(ctx.language)
            sources_html = f"""<div class="lia-search__sources">
  <span class="lia-search__sources-label">{sources_label} :</span>
  <div class="lia-search__sources-list">
    {chr(10).join(source_items)}
  </div>
</div>"""

        # Related questions - CSS handles visibility on mobile
        related_html = ""
        if related_questions:
            q_items = [
                f'<li class="lia-search__related-item">{escape_html(q)}</li>'
                for q in related_questions[:3]
            ]
            related_questions_label = V3Messages.get_related_questions(ctx.language)
            related_html = f"""<div class="lia-search__related">
  <span class="lia-search__related-label">{related_questions_label} :</span>
  <ul class="lia-search__related-list">
    {chr(10).join(q_items)}
  </ul>
</div>"""

        # Format answer (strip [x] references and format markdown)
        answer_html = self._format_answer(answer)

        # New layout: Badge first line, title second line (using shared utility classes)
        internet_label = V3Messages.get_internet(ctx.language)
        title_html = (
            f'<div class="lia-title-row"><span class="lia-title-row__text">{escape_html(query)}</span></div>'
            if query
            else ""
        )

        return f"""<div class="lia-card lia-search lia-search--answer {nested_class}">
  <div class="lia-badge-row">
    <span class="lia-badge lia-badge--primary">{icon(Icons.WEB)} {internet_label}</span>
  </div>
  {title_html}
  <div class="lia-search__answer">
    {answer_html}
  </div>
  {sources_html}
  {related_html}
</div>"""

    def _render_result(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render standard search result - CSS handles responsive adaptation."""
        title = data.get("title", "")
        url = data.get("url", "")
        snippet = data.get("snippet") or data.get("description", "")

        nested_class = self._nested_class(ctx)
        domain = self._extract_domain(url)

        # Unified template - CSS handles truncation on mobile
        return f"""<div class="lia-card lia-search {nested_class}">
  <div class="lia-search__header">
    <a href="{escape_html(url)}" class="lia-search__title" target="_blank">{escape_html(title)}</a>
    <span class="lia-search__domain">{escape_html(domain)}</span>
  </div>
  <p class="lia-search__snippet">{escape_html(truncate(snippet, 150))}</p>
</div>"""

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www.
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return url[:30] if url else ""

    def _format_answer(self, answer: str) -> str:
        """Format answer text, converting basic markdown and stripping reference markers."""
        if not answer:
            return ""

        import re

        # Strip reference markers [x] or [1] etc. before HTML escaping
        text = re.sub(r"\s*\[\d+\]", "", answer)

        # Escape HTML
        text = escape_html(text)

        # Convert **bold**
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

        # Convert *italic*
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

        # Convert newlines to paragraphs
        paragraphs = text.split("\n\n")
        if len(paragraphs) > 1:
            text = "".join(f"<p>{p}</p>" for p in paragraphs if p.strip())
        else:
            text = text.replace("\n", "<br>")

        return text
