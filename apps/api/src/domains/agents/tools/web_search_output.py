"""What a unified web search returns, and the text the model reads of it.

The output of :mod:`src.domains.agents.tools.web_search_tools`: Perplexity's
synthesis, the page links (the person's Brave, else the instance's SearXNG) and
the Wikipedia article. Every provider's words reach the model wrapped as
external content; a source that was asked and failed is SAID, by its name, never
shown as « no synthesis », « no links » or « no article » (ADR-382, ADR-303).
"""

from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel

from src.core.config import settings
from src.domains.agents.constants import (
    WEB_SEARCH_SOURCE_BRAVE,
    WEB_SEARCH_SOURCE_PERPLEXITY,
    WEB_SEARCH_SOURCE_WIKIPEDIA,
)
from src.domains.agents.utils.content_wrapper import wrap_external_content

#: How much of each part the model is handed: the rest stays in the registry item.
_CITATIONS_SHOWN: Final = 3
_LINKS_SHOWN: Final = 5
_EXCERPT_MAX_CHARS: Final = 100
_ARTICLE_MAX_CHARS: Final = 500
_QUESTIONS_SHOWN: Final = 3


class WebSearchResult(BaseModel):
    """One page link, from Brave or from the instance's SearXNG (``source``)."""

    title: str
    url: str
    snippet: str
    source: str = WEB_SEARCH_SOURCE_BRAVE


class WikipediaResult(BaseModel):
    """Wikipedia article summary."""

    title: str
    summary: str
    url: str


class UnifiedWebSearchOutput(BaseModel):
    """Output schema for unified web search."""

    query: str
    synthesis: str | None = None  # From Perplexity
    results: list[WebSearchResult] = []  # The page links (Brave or SearXNG)
    wikipedia: WikipediaResult | None = None
    sources: list[str] = []  # All configured sources
    sources_used: list[str] = []  # Sources that returned results
    related_questions: list[str] = []  # From Perplexity
    citations: list[str] = []  # From Perplexity


#: What is missing, which search it came from, and what its absence does NOT say,
#: when a source other than the page-link service failed. A link service (Brave,
#: SearXNG) reads the default.
_MISSING_PARTS: Final[dict[str, tuple[str, str, str]]] = {
    WEB_SEARCH_SOURCE_PERPLEXITY: ("AI synthesis", "synthesis search", "what the web holds"),
    WEB_SEARCH_SOURCE_WIKIPEDIA: (
        "Wikipedia article",
        "encyclopedia search",
        "whether an article exists",
    ),
}
_MISSING_LINKS: Final = ("Web links", "link search", "what the web holds")


def failure_line(source: str) -> str:
    """What the model reads when a source that was asked failed: a failure, not an absence.

    Args:
        source: The source that did not answer (``perplexity``, ``brave``,
            ``searxng``, ``wikipedia``).

    Returns:
        One sentence, in the technical English the model reads.
    """
    part, search, unknown = _MISSING_PARTS.get(source, _MISSING_LINKS)
    return (
        f"{part} unavailable: the {search} ({source}) did not answer this time; "
        f"this says nothing about {unknown}."
    )


def _cut(text: str, limit: int) -> str:
    """A text within ``limit`` characters, its cut marked."""
    return text[:limit] + "..." if len(text) > limit else text


def _external(content: str, source_url: str, source_type: str) -> str:
    """A provider's words as external content, unless the operator switched the wrapping off."""
    if not settings.external_content_wrapping_enabled:
        return content
    return wrap_external_content(content=content, source_url=source_url, source_type=source_type)


def _synthesis_lines(output: UnifiedWebSearchOutput) -> list[str]:
    """Perplexity's answer and the first addresses it cites."""
    if not output.synthesis:
        return []
    lines = [
        "### Synthesis (Perplexity AI)",
        _external(output.synthesis, "perplexity.ai", "search_synthesis"),
    ]
    if output.citations:
        lines.append(f"\nSources: {', '.join(output.citations[:_CITATIONS_SHOWN])}")
    return [*lines, ""]


def _link_lines(output: UnifiedWebSearchOutput) -> list[str]:
    """The page links: a numbered title, its address, then its excerpt."""
    if not output.results:
        return []
    lines = [f"### Web Results ({len(output.results)} links)"]
    for index, result in enumerate(output.results[:_LINKS_SHOWN], 1):
        lines.extend([f"  [{index}] {result.title}", f"      {result.url}"])
        if result.snippet:
            excerpt = _external(
                _cut(result.snippet, _EXCERPT_MAX_CHARS), result.url, "search_snippet"
            )
            lines.append(f"      {excerpt}")
    return [*lines, ""]


def _article_lines(output: UnifiedWebSearchOutput) -> list[str]:
    """The Wikipedia article: its title, the head of its summary, its address."""
    article = output.wikipedia
    if article is None:
        return []
    return [
        f"### Wikipedia: {article.title}",
        _external(_cut(article.summary, _ARTICLE_MAX_CHARS), article.url, "search_snippet"),
        f"\n🔗 {article.url}",
        "",
    ]


def _question_lines(output: UnifiedWebSearchOutput) -> list[str]:
    """The first questions Perplexity relates to this one."""
    if not output.related_questions:
        return []
    return [
        "### Related questions",
        *(f"  - {question}" for question in output.related_questions[:_QUESTIONS_SHOWN]),
    ]


def render_summary(output: UnifiedWebSearchOutput, *, failed_sources: Sequence[str]) -> str:
    """The text the model reads for one search.

    Args:
        output: What the three searches brought back.
        failed_sources: The sources that were asked and did not answer, in the
            order they were asked.

    Returns:
        A header, one line per source that failed, then each source's part.
    """
    header = (
        f"Web search results for '{output.query}' "
        f"({len(output.sources_used)}/{len(output.sources)} sources):\n"
    )
    failures = [*(failure_line(source) for source in failed_sources), ""] if failed_sources else []
    return "\n".join(
        [
            header,
            *failures,
            *_synthesis_lines(output),
            *_link_lines(output),
            *_article_lines(output),
            *_question_lines(output),
        ]
    )


__all__ = [
    "UnifiedWebSearchOutput",
    "WebSearchResult",
    "WikipediaResult",
    "failure_line",
    "render_summary",
]
