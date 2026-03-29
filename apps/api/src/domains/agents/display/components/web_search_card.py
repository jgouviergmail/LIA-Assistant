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
    render_desc_block,
    render_section_header,
    render_src_link,
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

        # v4: card-top with sources ABOVE title
        source_chips = self._render_source_indicators(sources_used)
        title_html = (
            f'<span class="lia-card-top__title">{escape_html(query)}</span>' if query else ""
        )
        # Custom card-top: sources above title
        card_top_html = (
            f'<div class="lia-card-top">'
            f'<div class="lia-illus lia-illus--blue">'
            f'<span class="material-symbols-outlined" style="font-size:22px;'
            f"font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 24\">"
            f"travel_explore</span></div>"
            f'<div class="lia-card-top__info">'
            f'<div class="lia-card-top__badges" style="margin-bottom:var(--lia-space-2xs)">'
            f"{source_chips}</div>"
            f"{title_html}"
            f"</div></div>"
        )

        return f"""<div class="lia-card lia-web-search {nested_class}">
{card_top_html}
{content}
</div>"""

    def _render_source_indicators(self, sources_used: list[str]) -> str:
        """Render source indicator chips (active/inactive)."""
        source_icons = {
            WEB_SEARCH_SOURCE_PERPLEXITY: (Icons.AI, "Perplexity"),
            WEB_SEARCH_SOURCE_BRAVE: (Icons.WEB, "Brave"),
            WEB_SEARCH_SOURCE_WIKIPEDIA: (Icons.BOOK, "Wikipedia"),
        }
        parts = []
        for source in WEB_SEARCH_ALL_SOURCES:
            icon_type, label = source_icons[source]
            is_active = source in sources_used
            active_class = "lia-web-search__source--active" if is_active else ""
            parts.append(
                f'<span class="lia-web-search__source {active_class}">'
                f"{icon(icon_type)} {label}</span>"
            )
        return " ".join(parts)

    def _render_header(
        self,
        query: str,
        sources_used: list[str],
        ctx: RenderContext,
    ) -> str:
        """Header is now handled by card-top in render(). Return empty."""
        return ""

    def _render_synthesis(self, synthesis: str, ctx: RenderContext) -> str:
        """Render Perplexity AI synthesis section using v4 components."""
        formatted = self._format_text(synthesis)
        synthesis_label = V3Messages.get_ai_synthesis(ctx.language)
        return render_section_header(
            synthesis_label, Icons.AI, "indigo", first=True
        ) + render_desc_block(formatted, with_border=False)

    def _render_results(self, results: list[dict[str, Any]], ctx: RenderContext) -> str:
        """Render Brave Search web results using v4 section header."""
        if not results:
            return ""

        results_label = V3Messages.get_web_results(ctx.language)
        header = render_section_header(results_label, Icons.WEB, "indigo")

        result_items = []
        for result in results[:5]:
            title = result.get("title", "")
            url = result.get("url", "")
            snippet = result.get("snippet", "")
            domain = self._extract_domain(url)

            result_items.append(
                f'<div class="lia-web-search__result">'
                f'<a href="{escape_html(url)}" class="lia-web-search__result-title" '
                f'target="_blank" rel="noopener">{escape_html(title)}</a>'
                f'<span class="lia-web-search__result-domain">{escape_html(domain)}</span>'
                f'<p class="lia-web-search__result-snippet">{escape_html(truncate(snippet, 120))}</p>'
                f"</div>"
            )

        return header + "".join(result_items)

    def _render_wikipedia(self, wikipedia: dict[str, Any], ctx: RenderContext) -> str:
        """Render Wikipedia section using v4 components."""
        title = wikipedia.get("title", "")
        summary = wikipedia.get("summary", "")
        url = wikipedia.get("url", "")
        display_summary = truncate(summary, 300)

        header = render_section_header("Wikipedia", Icons.BOOK, "indigo")
        content = (
            f'<div style="font-size:var(--lia-text-sm);color:var(--lia-text-secondary);line-height:var(--lia-leading-normal)">'
            f'<a href="{escape_html(url)}" target="_blank" rel="noopener" '
            f'style="color:var(--lia-primary);text-decoration:none;font-weight:600">'
            f"{escape_html(title)}</a>"
            f" — {escape_html(display_summary)}"
            f"</div>"
        )
        return header + content

    def _render_citations(self, citations: list[str], ctx: RenderContext) -> str:
        """Render source citations using v4 src-link component."""
        sources_label = V3Messages.get_sources(ctx.language)
        links_html = "".join(render_src_link(url) for url in citations[:5])
        return render_section_header(sources_label, Icons.LINK, "indigo") + links_html

    def _render_related_questions(
        self,
        questions: list[str],
        ctx: RenderContext,
    ) -> str:
        """Render related questions using v4 section header."""
        related_label = V3Messages.get_related_questions(ctx.language)
        q_items = [
            f'<li style="font-size:var(--lia-text-sm);color:var(--lia-text-secondary)">{escape_html(q)}</li>'
            for q in questions[:3]
        ]
        return (
            render_section_header(related_label, "help_outline", "indigo")
            + '<ul style="margin:var(--lia-space-xs) 0 0 var(--lia-space-lg);line-height:1.8">'
            + "".join(q_items)
            + "</ul>"
        )

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
