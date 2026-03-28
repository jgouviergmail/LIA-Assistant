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
    render_card_top,
    render_chip,
    render_section_header,
    render_src_link,
    truncate,
)
from src.domains.agents.display.icons import Icons


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
        """Render Perplexity-style answer with sources using v4 components."""
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        related_questions = data.get("related_questions", [])
        query = data.get("query", "") or data.get("search_term", "")

        nested_class = self._nested_class(ctx)

        # v4 card-top
        internet_label = V3Messages.get_internet(ctx.language)
        title_html = (
            f'<span class="lia-card-top__title">{escape_html(query)}</span>' if query else ""
        )
        internet_badge = render_chip(internet_label, "indigo", Icons.SEARCH)
        card_top_html = render_card_top("search", "blue", title_html, badges_html=internet_badge)

        # Sources using v4 src-link (same format as WebSearchCard)
        sources_html = ""
        if citations:
            sources_label = V3Messages.get_sources(ctx.language)
            links_html = "".join(render_src_link(url) for url in citations[:5])
            sources_html = render_section_header(sources_label, Icons.LINK, "indigo") + links_html

        # Related questions
        related_html = ""
        if related_questions:
            q_items = [
                f'<li style="font-size:var(--lia-text-sm);color:var(--lia-text-secondary)">{escape_html(q)}</li>'
                for q in related_questions[:3]
            ]
            related_questions_label = V3Messages.get_related_questions(ctx.language)
            related_html = (
                render_section_header(related_questions_label, "help_outline", "indigo")
                + '<ul style="margin:var(--lia-space-xs) 0 0 var(--lia-space-lg);line-height:1.8">'
                + "".join(q_items)
                + "</ul>"
            )

        # Format answer
        answer_html = self._format_answer(answer)

        return f"""<div class="lia-card lia-search lia-search--answer {nested_class}">
{card_top_html}
<div class="lia-search__answer">
{answer_html}
</div>
{sources_html}
{related_html}
</div>"""

    def _render_result(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render standard search result using v4 card-top."""
        title = data.get("title", "")
        url = data.get("url", "")
        snippet = data.get("snippet") or data.get("description", "")

        nested_class = self._nested_class(ctx)
        domain = self._extract_domain(url)

        title_html = (
            f'<a class="lia-card-top__title" href="{escape_html(url)}" target="_blank">'
            f"{escape_html(title)}</a>"
        )
        card_top_html = render_card_top("search", "blue", title_html)

        return f"""<div class="lia-card lia-search {nested_class}">
{card_top_html}
<span style="font-size:var(--lia-text-xs);color:var(--lia-text-muted)">{escape_html(domain)}</span>
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
