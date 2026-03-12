"""
LangChain v1 tools for Wikipedia operations.

LOT 10: Wikipedia API integration for knowledge retrieval.

Note: Wikipedia API requires no authentication.
This is a standalone tool without connector-based dependency injection.

Data Registry Integration:
    Wikipedia results are registered in ContextTypeRegistry to enable:
    - Contextual references ("the 2nd article", "that Wikipedia page")
    - Data persistence for response_node
    - Cross-domain queries with LocalQueryEngine
"""

from typing import Annotated

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel

from src.core.config import settings
from src.core.i18n import _
from src.domains.agents.constants import (
    AGENT_QUERY,
    AGENT_WIKIPEDIA,
    CONTEXT_DOMAIN_WIKIPEDIA,
)
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.wikipedia_client import WikipediaClient
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA REGISTRY INTEGRATION
# ============================================================================


class WikipediaArticleItem(BaseModel):
    """Schema for Wikipedia article data in context registry."""

    title: str  # Article title
    page_id: int | None = None  # Wikipedia page ID
    summary: str = ""  # Article summary/snippet
    url: str = ""  # Wikipedia URL
    language: str = "fr"  # Language code


# Register Wikipedia context type for Data Registry support
# This enables contextual references like "the 2nd article", "that Wikipedia page"
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_WIKIPEDIA,
        agent_name=AGENT_WIKIPEDIA,
        item_schema=WikipediaArticleItem,
        primary_id_field="page_id",
        display_name_field="title",
        reference_fields=["title", "summary"],
        icon="📚",
    )
)


# Client instances per language (cached)
_wikipedia_clients: dict[str, WikipediaClient] = {}


def _get_wikipedia_client(language: str = "fr") -> WikipediaClient:
    """Get or create Wikipedia client for a language."""
    global _wikipedia_clients
    if language not in _wikipedia_clients:
        _wikipedia_clients[language] = WikipediaClient(language=language)
    return _wikipedia_clients[language]


# ============================================================================
# TOOL 1: SEARCH WIKIPEDIA
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="search_wikipedia",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def search_wikipedia_tool(
    query: Annotated[str, "Search query for Wikipedia articles"],
    language: Annotated[str, "Wikipedia language code (e.g., 'fr', 'en', 'es', 'de')"] = "fr",
    max_results: Annotated[int, "Maximum number of results (default 5)"] = 5,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Search for Wikipedia articles matching a query.

    Returns article titles and snippets matching the search query.
    Use get_wikipedia_article to retrieve full content.

    Args:
        query: Search query (e.g., 'Albert Einstein', 'Tour Eiffel')
        language: Wikipedia language code (default: 'fr' for French)
        max_results: Maximum results to return (default 5, max 20)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with matching articles in registry

    Examples:
        - search_wikipedia("intelligence artificielle")
        - search_wikipedia("machine learning", language="en")
    """
    try:
        client = _get_wikipedia_client(language)

        # client.search() returns a list of dicts directly
        search_results = await client.search(
            query=query,
            limit=min(max_results, 20),
        )

        if not search_results:
            return UnifiedToolOutput.failure(
                message=_("No article found for '{query}' on Wikipedia ({language})").format(
                    query=query, language=language
                ),
                error_code="no_results",
                metadata={"query": query, "language": language, "total": 0},
            )

        # Create registry items for each article
        registry_updates: dict[str, RegistryItem] = {}
        article_summaries = []

        for idx, article in enumerate(search_results, 1):
            # Clean HTML tags from snippets
            snippet = article.get("snippet", "")
            snippet = snippet.replace('<span class="searchmatch">', "").replace("</span>", "")

            title = article.get("title", "")
            page_id = article.get("pageid")

            item_id = generate_registry_id(
                RegistryItemType.WIKIPEDIA_ARTICLE,
                f"wikipedia_search_{page_id or title}",
            )

            registry_item = RegistryItem(
                id=item_id,
                type=RegistryItemType.WIKIPEDIA_ARTICLE,
                payload={
                    "title": title,
                    "page_id": page_id,
                    "snippet": snippet,
                    "language": language,
                    "url": f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}",
                },
                meta=RegistryItemMeta(
                    source="wikipedia",
                    domain=CONTEXT_DOMAIN_WIKIPEDIA,
                    tool_name="search_wikipedia",
                ),
            )
            registry_updates[item_id] = registry_item

            # Build summary line
            snippet_preview = snippet[:100] + "..." if len(snippet) > 100 else snippet
            article_summaries.append(f"#{idx} [{item_id}] {title}\n   {snippet_preview}")

        logger.info(
            "search_wikipedia_success",
            query=query,
            language=language,
            results_count=len(search_results),
        )

        # Build summary for LLM
        summary = (
            _("Wikipedia search for '{query}' ({language}): {count} results").format(
                query=query, language=language, count=len(search_results)
            )
            + "\n\n"
        )
        summary += "\n\n".join(article_summaries)

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata={
                "query": query,
                "language": language,
                "total": len(search_results),
            },
        )

    except Exception as e:
        logger.error(
            "search_wikipedia_error",
            query=query,
            language=language,
            error=str(e),
        )
        return UnifiedToolOutput.failure(
            message=_("Error during Wikipedia search: {error}").format(error=str(e)),
            error_code="search_error",
            metadata={"error": str(e)},
        )


# ============================================================================
# TOOL 2: GET ARTICLE SUMMARY
# ============================================================================


WIKIPEDIA_SUMMARY_MAX_CHARS = settings.wikipedia_summary_max_chars


@tool
@track_tool_metrics(
    tool_name="get_wikipedia_summary",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_wikipedia_summary_tool(
    title: Annotated[str, "Wikipedia article title"],
    language: Annotated[str, "Wikipedia language code (e.g., 'fr', 'en', 'es', 'de')"] = "fr",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get a summary of a Wikipedia article.

    Returns the article's introduction/summary (up to WIKIPEDIA_SUMMARY_MAX_CHARS).
    For full article content, use get_wikipedia_article.

    Args:
        title: Article title (e.g., 'Albert Einstein', 'Tour Eiffel')
        language: Wikipedia language code (default: 'fr' for French)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with article summary in registry

    Examples:
        - get_wikipedia_summary("Paris")
        - get_wikipedia_summary("Quantum mechanics", language="en")
    """
    try:
        client = _get_wikipedia_client(language)

        # Use get_article with extract_chars for configurable length (not get_article_summary which returns short fixed text)
        result = await client.get_article(title=title, extract_chars=WIKIPEDIA_SUMMARY_MAX_CHARS)

        if not result or "error" in result or "extract" not in result:
            return UnifiedToolOutput.failure(
                message=_("Article '{title}' not found on Wikipedia ({language})").format(
                    title=title, language=language
                ),
                error_code="article_not_found",
                metadata={"title": title, "language": language},
            )

        article_title = result.get("title", title)
        page_id = result.get("pageid")
        extract = result.get("extract", "")
        url = (
            result.get("fullurl")
            or f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}"
        )

        item_id = generate_registry_id(
            RegistryItemType.WIKIPEDIA_ARTICLE,
            f"wikipedia_summary_{page_id or title}",
        )

        registry_item = RegistryItem(
            id=item_id,
            type=RegistryItemType.WIKIPEDIA_ARTICLE,
            payload={
                "title": article_title,
                "page_id": page_id,
                "summary": extract,
                "url": url,
                "language": language,
                "type": "summary",
            },
            meta=RegistryItemMeta(
                source="wikipedia",
                domain=CONTEXT_DOMAIN_WIKIPEDIA,
                tool_name="get_wikipedia_summary",
            ),
        )

        logger.info(
            "get_wikipedia_summary_success",
            title=title,
            language=language,
            summary_length=len(extract),
        )

        # Build summary for LLM
        summary = _("Wikipedia summary: {title}").format(title=article_title) + f" [{item_id}]\n\n"
        summary += extract
        summary += f"\n\n🔗 URL: {url}"

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates={item_id: registry_item},
            metadata={
                "title": article_title,
                "page_id": page_id,
                "language": language,
                "summary_length": len(extract),
                "url": url,
            },
        )

    except Exception as e:
        logger.error(
            "get_wikipedia_summary_error",
            title=title,
            language=language,
            error=str(e),
        )
        return UnifiedToolOutput.failure(
            message=_("Error retrieving summary: {error}").format(error=str(e)),
            error_code="summary_error",
            metadata={"error": str(e)},
        )


# ============================================================================
# TOOL 3: GET FULL ARTICLE
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_wikipedia_article",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_wikipedia_article_tool(
    title: Annotated[str, "Wikipedia article title"],
    language: Annotated[str, "Wikipedia language code (e.g., 'fr', 'en', 'es', 'de')"] = "fr",
    sections: Annotated[bool, "Include section breakdown (default True)"] = True,
    max_length: Annotated[int, "Maximum content length in characters (default 10000)"] = 10000,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get full content of a Wikipedia article.

    Returns the complete article text with optional section breakdown.
    For quick overviews, use get_wikipedia_summary instead.

    Args:
        title: Article title (e.g., 'Albert Einstein', 'Tour Eiffel')
        language: Wikipedia language code (default: 'fr' for French)
        sections: Include section breakdown (default True)
        max_length: Maximum content length (default 10000 chars)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with full article content in registry

    Examples:
        - get_wikipedia_article("Révolution française")
        - get_wikipedia_article("World War II", language="en", sections=True)
    """
    try:
        client = _get_wikipedia_client(language)

        # client.get_article() returns a dict with "extract" key for content
        result = await client.get_article(title=title)

        # Check for error or missing page
        if not result or "error" in result or "extract" not in result:
            return UnifiedToolOutput.failure(
                message=_("Article '{title}' not found on Wikipedia ({language})").format(
                    title=title, language=language
                ),
                error_code="article_not_found",
                metadata={"title": title, "language": language},
            )

        # Get content from "extract" key
        content = result.get("extract", "")

        # Truncate if too long
        original_length = len(content)
        truncated = original_length > max_length
        if truncated:
            content = content[:max_length] + "\n\n[... " + _("content truncated") + " ...]"

        article_title = result.get("title", title)
        page_id = result.get("pageid")
        url = result.get(
            "fullurl", f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}"
        )

        # Build payload
        payload = {
            "title": article_title,
            "page_id": page_id,
            "content": content,
            "content_length": original_length,
            "url": url,
            "language": language,
            "type": "full_article",
        }

        # Add sections if requested
        section_data = []
        if sections:
            section_list = await client.get_article_sections(title)
            if section_list:
                section_data = [
                    {
                        "title": s.get("line", ""),
                        "level": int(s.get("level", 1)),
                        "index": s.get("index"),
                    }
                    for s in section_list[:20]  # Limit sections
                ]
                payload["sections"] = section_data

        item_id = generate_registry_id(
            RegistryItemType.WIKIPEDIA_ARTICLE,
            f"wikipedia_article_{page_id or title}",
        )

        registry_item = RegistryItem(
            id=item_id,
            type=RegistryItemType.WIKIPEDIA_ARTICLE,
            payload=payload,
            meta=RegistryItemMeta(
                source="wikipedia",
                domain=CONTEXT_DOMAIN_WIKIPEDIA,
                tool_name="get_wikipedia_article",
            ),
        )

        logger.info(
            "get_wikipedia_article_success",
            title=title,
            language=language,
            content_length=len(content),
        )

        # Build summary for LLM
        summary_parts = [
            _("Wikipedia article: {title}").format(title=article_title) + f" [{item_id}]\n"
        ]

        if section_data:
            summary_parts.append("📑 " + _("Sections") + ":")
            for s in section_data[:5]:
                indent = "  " * (s["level"] - 1)
                summary_parts.append(f"  {indent}- {s['title']}")
            if len(section_data) > 5:
                summary_parts.append(
                    "  ... " + _("and {count} more sections").format(count=len(section_data) - 5)
                )
            summary_parts.append("")

        summary_parts.append("📖 " + _("Content") + ":")
        # Show first part of content
        content_preview = content[:2000] if len(content) > 2000 else content
        summary_parts.append(content_preview)
        if len(content) > 2000:
            summary_parts.append(
                "\n... ["
                + _("{count} additional characters in registry").format(
                    count=original_length - 2000
                )
                + "]"
            )

        summary_parts.append(f"\n🔗 URL: {url}")

        summary = "\n".join(summary_parts)

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates={item_id: registry_item},
            metadata={
                "title": article_title,
                "page_id": page_id,
                "language": language,
                "content_length": original_length,
                "truncated": truncated,
                "sections_count": len(section_data),
            },
        )

    except Exception as e:
        logger.error(
            "get_wikipedia_article_error",
            title=title,
            language=language,
            error=str(e),
        )
        return UnifiedToolOutput.failure(
            message=_("Error retrieving article: {error}").format(error=str(e)),
            error_code="article_error",
            metadata={"error": str(e)},
        )


# ============================================================================
# TOOL 4: GET RELATED ARTICLES
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_wikipedia_related",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_wikipedia_related_tool(
    title: Annotated[str, "Wikipedia article title"],
    language: Annotated[str, "Wikipedia language code (e.g., 'fr', 'en', 'es', 'de')"] = "fr",
    max_results: Annotated[int, "Maximum number of related articles (default 10)"] = 10,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get articles related to a Wikipedia article.

    Returns links to other Wikipedia articles referenced in the given article.
    Useful for exploring related topics.

    Args:
        title: Article title (e.g., 'Albert Einstein')
        language: Wikipedia language code (default: 'fr')
        max_results: Maximum related articles to return (default 10)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with related articles in registry

    Examples:
        - get_wikipedia_related("Python (langage)")
        - get_wikipedia_related("Machine learning", language="en")
    """
    try:
        client = _get_wikipedia_client(language)

        # client.get_related_articles() returns a list directly
        related_articles = await client.get_related_articles(title, limit=max_results)

        if not related_articles:
            return UnifiedToolOutput.failure(
                message=_("No related article found for '{title}'").format(title=title),
                error_code="no_results",
                metadata={"source_article": title, "total": 0},
            )

        # Create registry items for each related article
        registry_updates: dict[str, RegistryItem] = {}
        article_summaries = []

        for idx, article in enumerate(related_articles, 1):
            related_title = article.get("title", "")
            if not related_title:
                continue

            item_id = generate_registry_id(
                RegistryItemType.WIKIPEDIA_ARTICLE,
                f"wikipedia_related_{title}_{related_title}",
            )

            registry_item = RegistryItem(
                id=item_id,
                type=RegistryItemType.WIKIPEDIA_ARTICLE,
                payload={
                    "title": related_title,
                    "source_article": title,
                    "language": language,
                    "url": f"https://{language}.wikipedia.org/wiki/{related_title.replace(' ', '_')}",
                    "type": "related",
                },
                meta=RegistryItemMeta(
                    source="wikipedia",
                    domain=CONTEXT_DOMAIN_WIKIPEDIA,
                    tool_name="get_wikipedia_related",
                ),
            )
            registry_updates[item_id] = registry_item
            article_summaries.append(f"#{idx} [{item_id}] {related_title}")

        logger.info(
            "get_wikipedia_related_success",
            title=title,
            language=language,
            related_count=len(registry_updates),
        )

        # Build summary for LLM
        summary = (
            _("Articles related to '{title}' ({language}): {count} results").format(
                title=title, language=language, count=len(registry_updates)
            )
            + "\n\n"
        )
        summary += "\n".join(article_summaries)

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata={
                "source_article": title,
                "language": language,
                "total": len(registry_updates),
            },
        )

    except Exception as e:
        logger.error(
            "get_wikipedia_related_error",
            title=title,
            language=language,
            error=str(e),
        )
        return UnifiedToolOutput.failure(
            message=_("Error retrieving related articles: {error}").format(error=str(e)),
            error_code="related_error",
            metadata={"error": str(e)},
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "search_wikipedia_tool",
    "get_wikipedia_summary_tool",
    "get_wikipedia_article_tool",
    "get_wikipedia_related_tool",
]
