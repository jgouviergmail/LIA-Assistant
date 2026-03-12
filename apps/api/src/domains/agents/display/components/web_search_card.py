"""
WebSearchCard Component - Unified Triple Source Search Display.

Renders combined results from Perplexity AI, Brave Search, and Wikipedia.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import (
    WEB_SEARCH_ALL_SOURCES,
    WEB_SEARCH_SOURCE_BRAVE,
    WEB_SEARCH_SOURCE_PERPLEXITY,
    WEB_SEARCH_SOURCE_WIKIPEDIA,
)
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    truncate,
)
from src.domains.agents.display.icons import Icons, icon


class WebSearchCard(BaseComponent):
    """
    Unified web search card with triple source display.

    Section order:
    1. Header (query title + sources indicator)
    2. Synthesis (Perplexity AI answer)
    3. Wikipedia (encyclopedia snippet)
    4. Citations (source URLs)
    5. Related questions
    6. Web results (Brave Search URLs)
    """

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """Render unified web search as modern card."""
        query = data.get("query", "")
        synthesis = data.get("synthesis")
        results = data.get("results", [])
        wikipedia = data.get("wikipedia")
        sources_used = data.get("sources_used", [])
        citations = data.get("citations", [])
        related_questions = data.get("related_questions", [])

        nested_class = self._nested_class(ctx)

        # Build sections in order:
        # 1. Header (titre + sources indicator)
        # 2. Synthesis (Perplexity)
        # 3. Wikipedia
        # 4. Citations (sources)
        # 5. Related questions
        # 6. Web results (Brave)
        sections = []

        # 1. Header with query and sources indicator
        header_html = self._render_header(query, sources_used, ctx)
        sections.append(header_html)

        # 2. Synthesis section (Perplexity)
        if synthesis:
            synthesis_html = self._render_synthesis(synthesis, ctx)
            sections.append(synthesis_html)

        # 3. Wikipedia section
        if wikipedia:
            wiki_html = self._render_wikipedia(wikipedia, ctx)
            sections.append(wiki_html)

        # 4. Citations (sources from Perplexity)
        if citations:
            citations_html = self._render_citations(citations, ctx)
            sections.append(citations_html)

        # 5. Related questions
        if related_questions:
            related_html = self._render_related_questions(related_questions, ctx)
            sections.append(related_html)

        # 6. Web results section (Brave) - last for visual hierarchy
        if results:
            results_html = self._render_results(results, ctx)
            sections.append(results_html)

        content = "\n".join(sections)

        return f"""<div class="lia-card lia-web-search {nested_class}">
{content}
</div>"""

    def _render_header(
        self,
        query: str,
        sources_used: list[str],
        ctx: RenderContext,
    ) -> str:
        """Render header with query and sources indicator."""
        # Source badges
        source_badges = []
        source_icons = {
            WEB_SEARCH_SOURCE_PERPLEXITY: (Icons.AI, "Perplexity"),
            WEB_SEARCH_SOURCE_BRAVE: (Icons.WEB, "Brave"),
            WEB_SEARCH_SOURCE_WIKIPEDIA: (Icons.BOOK, "Wikipedia"),
        }

        for source in WEB_SEARCH_ALL_SOURCES:
            icon_type, label = source_icons[source]
            is_active = source in sources_used
            active_class = "lia-web-search__source--active" if is_active else ""
            source_badges.append(
                f'<span class="lia-web-search__source {active_class}">'
                f"{icon(icon_type)} {label}"
                f"</span>"
            )

        sources_html = " ".join(source_badges)

        # Title row
        title_html = ""
        if query:
            title_html = f'<div class="lia-title-row"><span class="lia-title-row__text">{escape_html(query)}</span></div>'

        search_label = V3Messages.get_internet(ctx.language)

        return f"""<div class="lia-web-search__header">
  <div class="lia-badge-row">
    <span class="lia-badge lia-badge--primary">{icon(Icons.SEARCH)} {search_label}</span>
    <div class="lia-web-search__sources">{sources_html}</div>
  </div>
  {title_html}
</div>"""

    def _render_synthesis(self, synthesis: str, ctx: RenderContext) -> str:
        """Render Perplexity AI synthesis section."""
        # Format synthesis text
        formatted = self._format_text(synthesis)

        synthesis_label = V3Messages.get_ai_synthesis(ctx.language)

        return f"""<div class="lia-web-search__synthesis">
  <div class="lia-web-search__section-label">
    {icon(Icons.AI)} {synthesis_label}
  </div>
  <div class="lia-web-search__synthesis-content">
    {formatted}
  </div>
</div>"""

    def _render_results(self, results: list[dict[str, Any]], ctx: RenderContext) -> str:
        """Render Brave Search web results."""
        if not results:
            return ""

        result_items = []
        for result in results[:5]:
            title = result.get("title", "")
            url = result.get("url", "")
            snippet = result.get("snippet", "")
            domain = self._extract_domain(url)

            result_items.append(
                f"""<div class="lia-web-search__result">
  <a href="{escape_html(url)}" class="lia-web-search__result-title" target="_blank" rel="noopener">
    {escape_html(title)}
  </a>
  <span class="lia-web-search__result-domain">{escape_html(domain)}</span>
  <p class="lia-web-search__result-snippet">{escape_html(truncate(snippet, 120))}</p>
</div>"""
            )

        results_label = V3Messages.get_web_results(ctx.language)

        return f"""<div class="lia-web-search__results">
  <div class="lia-web-search__section-label">
    {icon(Icons.WEB)} {results_label}
  </div>
  <div class="lia-web-search__results-list">
    {chr(10).join(result_items)}
  </div>
</div>"""

    def _render_wikipedia(self, wikipedia: dict[str, Any], ctx: RenderContext) -> str:
        """Render Wikipedia section."""
        title = wikipedia.get("title", "")
        summary = wikipedia.get("summary", "")
        url = wikipedia.get("url", "")

        # Truncate summary for display
        display_summary = truncate(summary, 300)

        return f"""<div class="lia-web-search__wikipedia">
  <div class="lia-web-search__section-label">
    {icon(Icons.BOOK)} Wikipedia
  </div>
  <div class="lia-web-search__wikipedia-content">
    <a href="{escape_html(url)}" class="lia-web-search__wikipedia-title" target="_blank" rel="noopener">
      {escape_html(title)}
    </a>
    <p class="lia-web-search__wikipedia-summary">{escape_html(display_summary)}</p>
  </div>
</div>"""

    def _render_citations(self, citations: list[str], ctx: RenderContext) -> str:
        """Render source citations."""
        source_items = []
        for url in citations[:5]:
            domain = self._extract_domain(url)
            source_items.append(
                f'<a href="{escape_html(url)}" class="lia-source" target="_blank" rel="noopener">'
                f'<span class="lia-source__icon">{icon(Icons.LINK)}</span>'
                f'<span class="lia-source__domain">{escape_html(domain)}</span>'
                f"</a>"
            )

        sources_label = V3Messages.get_sources(ctx.language)

        return f"""<div class="lia-web-search__citations">
  <span class="lia-web-search__section-label">{sources_label} :</span>
  <div class="lia-web-search__citations-list">
    {chr(10).join(source_items)}
  </div>
</div>"""

    def _render_related_questions(
        self,
        questions: list[str],
        ctx: RenderContext,
    ) -> str:
        """Render related questions."""
        q_items = [
            f'<li class="lia-web-search__related-item">{escape_html(q)}</li>' for q in questions[:3]
        ]

        related_label = V3Messages.get_related_questions(ctx.language)

        return f"""<div class="lia-web-search__related">
  <span class="lia-web-search__section-label">{related_label} :</span>
  <ul class="lia-web-search__related-list">
    {chr(10).join(q_items)}
  </ul>
</div>"""

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return url[:30] if url else ""

    def _format_text(self, text: str) -> str:
        """Format text, converting basic markdown and escaping HTML."""
        if not text:
            return ""

        # Strip reference markers [x] before HTML escaping
        text = re.sub(r"\s*\[\d+\]", "", text)

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
