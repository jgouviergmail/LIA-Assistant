"""
LangChain v1 tools for Unified Web Search operations.

Unified Triple Source Search: Perplexity AI + Brave Search + Wikipedia.

Architecture:
    - Parallel execution via asyncio.gather() with return_exceptions=True
    - Fallback chain: continues if one source fails
    - Wikipedia always available (no auth required)
    - Consolidation and deduplication of results

Data Registry Integration:
    Results are registered in ContextTypeRegistry to enable:
    - Contextual references ("the search results", "those articles")
    - Data persistence for response_node
    - Cross-domain queries with LocalQueryEngine

Fallback Matrix:
    | P | B | W | Result                     |
    |---|---|---|----------------------------|
    | Y | Y | Y | Triple source consolidated |
    | Y | Y | N | Perplexity + Brave         |
    | Y | N | Y | Perplexity + Wikipedia     |
    | N | Y | Y | Brave + Wikipedia          |
    | Y | N | N | Perplexity only            |
    | N | Y | N | Brave only                 |
    | N | N | Y | Wikipedia only             |
"""

import asyncio
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel

from src.core.config import settings
from src.core.constants import DEFAULT_LANGUAGE
from src.core.i18n import _
from src.core.time_utils import get_current_datetime_context
from src.domains.agents.constants import (
    AGENT_WEB_SEARCH,
    CONTEXT_DOMAIN_WEB_SEARCH,
    WEB_SEARCH_ALL_SOURCES,
    WEB_SEARCH_SOURCE_BRAVE,
    WEB_SEARCH_SOURCE_PERPLEXITY,
    WEB_SEARCH_SOURCE_WIKIPEDIA,
)
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences, parse_user_id
from src.domains.connectors.clients.brave_search_client import BraveSearchClient
from src.domains.connectors.clients.perplexity_client import PerplexityClient
from src.domains.connectors.clients.wikipedia_client import WikipediaClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.cache.web_search_cache import WebSearchCache
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)

# Brave API freshness format mapping (tool "day"/"week"/"month" → Brave "pd"/"pw"/"pm")
_BRAVE_FRESHNESS_MAP: dict[str, str] = {"day": "pd", "week": "pw", "month": "pm"}

# Valid recency values accepted by the tool
_VALID_RECENCY = {"day", "week", "month", "year"}

# Normalization map for non-standard recency values the planner may generate
_RECENCY_NORMALIZE_MAP: dict[str, str] = {
    "1d": "day",
    "24h": "day",
    "7d": "week",
    "1w": "week",
    "30d": "month",
    "1m": "month",
    "1y": "year",
    "365d": "year",
    "pd": "day",
    "pw": "week",
    "pm": "month",
    "py": "year",
}


def _normalize_recency(recency: str | None) -> str | None:
    """Normalize recency parameter to valid values.

    The planner (LLM) may generate non-standard values like "7d", "1w", "pd", etc.
    This function normalizes them to the canonical values: "day", "week", "month", "year".
    Invalid values are treated as None (no recency filter).

    Args:
        recency: Raw recency value from planner.

    Returns:
        Normalized recency or None if invalid/not provided.
    """
    if recency is None:
        return None
    recency = recency.strip().lower()
    if recency in _VALID_RECENCY:
        return recency
    normalized = _RECENCY_NORMALIZE_MAP.get(recency)
    if normalized:
        logger.info(
            "recency_normalized",
            raw=recency,
            normalized=normalized,
        )
        return normalized
    logger.warning("recency_invalid_ignored", raw=recency, valid=list(_VALID_RECENCY))
    return None


# ============================================================================
# DATA MODELS
# ============================================================================


class WebSearchResult(BaseModel):
    """Individual web search result from Brave."""

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
    results: list[WebSearchResult] = []  # From Brave
    wikipedia: WikipediaResult | None = None
    sources: list[str] = []  # All configured sources
    sources_used: list[str] = []  # Sources that returned results
    related_questions: list[str] = []  # From Perplexity
    citations: list[str] = []  # From Perplexity


class WebSearchItem(BaseModel):
    """Schema for web search data in context registry."""

    query: str
    synthesis: str | None = None
    results_count: int = 0
    wikipedia_title: str | None = None
    sources_used: list[str] = []


# Register Web Search context type for Data Registry support
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_WEB_SEARCH,
        agent_name=AGENT_WEB_SEARCH,
        item_schema=WebSearchItem,
        primary_id_field="query",
        display_name_field="query",
        reference_fields=["query", "synthesis"],
        icon="🔍",
    )
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def _search_perplexity(
    query: str,
    user_uuid: UUID,
    user_timezone: str,
    user_language: str,
    recency: str | None,
) -> dict[str, Any] | None:
    """
    Execute Perplexity search if API key is configured.

    Returns dict with answer, citations, related_questions or None if not available.
    """
    try:
        async with get_db_context() as db:
            connector_service = ConnectorService(db)
            # Use get_api_key_credentials for API key connectors (not OAuth)
            credentials = await connector_service.get_api_key_credentials(
                user_id=user_uuid,
                connector_type=ConnectorType.PERPLEXITY,
            )

            if not credentials:
                logger.debug("perplexity_not_configured", user_id=str(user_uuid))
                return None

            client = PerplexityClient(
                api_key=credentials.api_key,
                user_id=user_uuid,
                model=settings.perplexity_search_model,
                user_timezone=user_timezone,
                user_language=user_language,
            )

            # Build system prompt with datetime context
            current_datetime = get_current_datetime_context(
                timezone_str=user_timezone,
                language=user_language,
            )
            system_prompt = f"Current date and time: {current_datetime}"

            # Convert recency filter
            recency_filter = None
            if recency in {"day", "week", "month", "year"}:
                recency_filter = recency

            result = await client.search(
                query=query,
                search_recency_filter=recency_filter,
                return_citations=True,
                return_related_questions=True,
                system_prompt=system_prompt,
            )

            logger.info(
                "perplexity_search_success",
                user_id=str(user_uuid),
                query=query[:50],
                citations_count=len(result.get("citations", [])),
            )

            return {
                "answer": result.get("answer", ""),
                "citations": result.get("citations", []),
                "related_questions": result.get("related_questions", []),
            }

    except Exception as e:
        logger.warning(
            "perplexity_search_failed",
            user_id=str(user_uuid),
            error=str(e),
        )
        return None


async def _search_brave(
    query: str,
    user_uuid: UUID,
    count: int = 5,
    freshness: str | None = None,
    endpoint: str = "web",
) -> list[WebSearchResult]:
    """
    Execute Brave Search if API key is configured.

    Args:
        query: Search query
        user_uuid: User ID for API key lookup
        count: Number of results
        freshness: Brave freshness filter (pd, pw, pm, py)
        endpoint: "web" for general search, "news" for news-specific results

    Returns list of WebSearchResult or empty list if not available.
    """
    try:
        async with get_db_context() as db:
            connector_service = ConnectorService(db)
            credentials = await connector_service.get_api_key_credentials(
                user_id=user_uuid,
                connector_type=ConnectorType.BRAVE_SEARCH,
            )

            if not credentials:
                logger.debug("brave_not_configured", user_id=str(user_uuid))
                return []

            client = BraveSearchClient(
                api_key=credentials.api_key,
                user_id=user_uuid,
            )

            result = await client.search(
                query=query,
                endpoint=endpoint,
                count=count,
                freshness=freshness,
            )

            if not result:
                return []

            # Extract results based on endpoint (different response formats)
            if endpoint == "web":
                raw_results = result.get("web", {}).get("results", [])
            else:
                raw_results = result.get("results", [])

            logger.info(
                "brave_search_success",
                user_id=str(user_uuid),
                query=query[:50],
                endpoint=endpoint,
                results_count=len(raw_results),
            )

            return [
                WebSearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                    source=WEB_SEARCH_SOURCE_BRAVE,
                )
                for item in raw_results[:count]
            ]

    except Exception as e:
        logger.warning(
            "brave_search_failed",
            user_id=str(user_uuid),
            endpoint=endpoint,
            error=str(e),
        )
        return []


async def _search_wikipedia(
    query: str,
    language: str = DEFAULT_LANGUAGE,
) -> WikipediaResult | None:
    """
    Execute Wikipedia search - always available (no auth).

    Returns WikipediaResult or None if no relevant article found.
    """
    try:
        client = WikipediaClient(language=language)

        # First search for the most relevant article
        search_results = await client.search(query=query, limit=1)

        if not search_results:
            logger.debug("wikipedia_no_results", query=query)
            return None

        # Get summary of the first result
        title = search_results[0].get("title", "")
        if not title:
            return None

        # Get article summary (longer than default summary)
        result = await client.get_article(
            title=title,
            extract_chars=settings.wikipedia_summary_max_chars,
        )

        if not result or "error" in result:
            return None

        article_title = result.get("title", title)
        extract = result.get("extract", "")
        url = result.get(
            "fullurl",
            f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}",
        )

        logger.info(
            "wikipedia_search_success",
            query=query,
            title=article_title,
            summary_length=len(extract),
        )

        return WikipediaResult(
            title=article_title,
            summary=extract,
            url=url,
        )

    except Exception as e:
        logger.warning(
            "wikipedia_search_failed",
            query=query,
            error=str(e),
        )
        return None


# ============================================================================
# UNIFIED WEB SEARCH TOOL
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="unified_web_search",
    agent_name=AGENT_WEB_SEARCH,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def unified_web_search_tool(
    query: Annotated[str, "Search query or question"],
    recency: Annotated[
        str | None,
        "Freshness filter: 'day', 'week', 'month', or None (default: None)",
    ] = None,
    force_refresh: Annotated[
        bool,
        "Force bypass cache and fetch fresh results (use when user asks to refresh/update)",
    ] = False,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Comprehensive web search combining three sources in parallel.

    Executes Perplexity AI (synthesis), Brave Search (URLs), and Wikipedia (encyclopedia)
    simultaneously. Returns a unified result set with fallback handling.

    Fallback Chain:
    - If Perplexity fails: Continue with Brave + Wikipedia
    - If Brave fails: Continue with Perplexity + Wikipedia
    - Wikipedia always available (no authentication required)

    Args:
        query: Search query or question (e.g., "recette pates bolognaise", "who is Einstein")
        recency: Optional freshness filter:
            - "day": Last 24 hours
            - "week": Last 7 days
            - "month": Last 30 days
            - None: No time filter (default)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with combined results from all available sources

    Examples:
        - unified_web_search("recette pates bolognaise marmiton")
        - unified_web_search("dernières nouvelles IA", recency="week")
        - unified_web_search("qui est Albert Einstein")
    """
    # Extract user context from runtime
    user_uuid = None

    if runtime and runtime.config:
        configurable = runtime.config.get("configurable") or {}
        user_id_raw = configurable.get("user_id")
        if user_id_raw:
            try:
                user_uuid = parse_user_id(user_id_raw)
            except ValueError as e:
                logger.warning("invalid_user_id_format", error=str(e))

    if not user_uuid:
        return UnifiedToolOutput.failure(
            message=_("User context required for web search"),
            error_code="USER_CONTEXT_MISSING",
            metadata={"query": query},
        )

    # Get user preferences from DB (centralized pattern from runtime_helpers)
    user_timezone, user_language, _locale = await get_user_preferences(runtime)

    # Normalize recency to valid values (planner may pass non-standard values like "7d")
    recency = _normalize_recency(recency)

    # --- Cache check (before external API calls) ---
    if not force_refresh:
        try:
            redis_client = await get_redis_cache()
            cache = WebSearchCache(redis_client)
            cache_result = await cache.get_search(user_uuid, query, recency)
            if cache_result.from_cache and cache_result.data:
                logger.info(
                    "unified_web_search_from_cache",
                    user_id=str(user_uuid),
                    query=query[:50],
                    cache_age_seconds=cache_result.cache_age_seconds,
                )
                # Note: registry_updates not restored from cache (RegistryItem
                # objects cannot be reconstructed from plain dicts without loss).
                # The text message contains all information the agent needs.
                return UnifiedToolOutput.data_success(
                    message=cache_result.data.get("message", ""),
                    metadata={
                        **cache_result.data.get("metadata", {}),
                        "from_cache": True,
                        "cache_age_seconds": cache_result.cache_age_seconds,
                    },
                )
        except Exception as e:
            logger.warning("web_search_cache_check_failed", error=str(e))

    # Convert freshness for Brave API format (pd=24h, pw=7d, pm=31d)
    brave_freshness = _BRAVE_FRESHNESS_MAP.get(recency)

    # Use Brave News endpoint for recent queries (more relevant for news/current events)
    brave_endpoint = "news" if recency in ("day", "week") else "web"

    # Execute all three searches in parallel
    perplexity_task = _search_perplexity(
        query=query,
        user_uuid=user_uuid,
        user_timezone=user_timezone,
        user_language=user_language,
        recency=recency,
    )
    brave_task = _search_brave(
        query=query,
        user_uuid=user_uuid,
        count=5,
        freshness=brave_freshness,
        endpoint=brave_endpoint,
    )
    wikipedia_task = _search_wikipedia(
        query=query,
        language=user_language,
    )

    # Gather with return_exceptions to handle partial failures
    results = await asyncio.gather(
        perplexity_task,
        brave_task,
        wikipedia_task,
        return_exceptions=True,
    )

    # Process results (handle exceptions gracefully)
    perplexity_result = results[0] if not isinstance(results[0], Exception) else None
    brave_results = results[1] if not isinstance(results[1], Exception) else []
    wikipedia_result = results[2] if not isinstance(results[2], Exception) else None

    # Handle exception cases
    if isinstance(results[0], Exception):
        logger.warning("perplexity_exception", error=str(results[0]))
    if isinstance(results[1], Exception):
        logger.warning("brave_exception", error=str(results[1]))
    if isinstance(results[2], Exception):
        logger.warning("wikipedia_exception", error=str(results[2]))

    # Track which sources were used
    all_sources = WEB_SEARCH_ALL_SOURCES
    sources_used = []

    if perplexity_result:
        sources_used.append(WEB_SEARCH_SOURCE_PERPLEXITY)
    if brave_results:
        sources_used.append(WEB_SEARCH_SOURCE_BRAVE)
    if wikipedia_result:
        sources_used.append(WEB_SEARCH_SOURCE_WIKIPEDIA)

    # Check if we have any results
    if not sources_used:
        return UnifiedToolOutput.failure(
            message=_("No search results found from any source for '{query}'").format(query=query),
            error_code="NO_RESULTS",
            metadata={
                "query": query,
                "sources": all_sources,
                "sources_used": [],
            },
        )

    # Build unified output
    unified_output = UnifiedWebSearchOutput(
        query=query,
        synthesis=perplexity_result.get("answer") if perplexity_result else None,
        results=brave_results or [],
        wikipedia=wikipedia_result,
        sources=all_sources,
        sources_used=sources_used,
        related_questions=(
            perplexity_result.get("related_questions", []) if perplexity_result else []
        ),
        citations=perplexity_result.get("citations", []) if perplexity_result else [],
    )

    # Create registry item
    item_id = generate_registry_id(
        RegistryItemType.WEB_SEARCH,
        f"web_search_{query}",
    )

    registry_item = RegistryItem(
        id=item_id,
        type=RegistryItemType.WEB_SEARCH,
        payload={
            "query": query,
            "synthesis": unified_output.synthesis,
            "results": [r.model_dump() for r in unified_output.results],
            "wikipedia": (
                unified_output.wikipedia.model_dump() if unified_output.wikipedia else None
            ),
            "sources": unified_output.sources,
            "sources_used": unified_output.sources_used,
            "related_questions": unified_output.related_questions,
            "citations": unified_output.citations,
            "type": "unified_web_search",
        },
        meta=RegistryItemMeta(
            source="web_search",
            domain=CONTEXT_DOMAIN_WEB_SEARCH,
            tool_name="unified_web_search",
        ),
    )

    # Build summary for LLM
    summary_parts = [
        f"Résultats de recherche web pour '{query}' ({len(sources_used)}/{len(all_sources)} sources):\n"
    ]

    # Perplexity synthesis section
    if unified_output.synthesis:
        summary_parts.append("### Synthesis (Perplexity AI)")
        summary_parts.append(unified_output.synthesis)
        if unified_output.citations:
            summary_parts.append(f"\nSources: {', '.join(unified_output.citations[:3])}")
        summary_parts.append("")

    # Brave results section
    if unified_output.results:
        summary_parts.append(f"### Web Results ({len(unified_output.results)} links)")
        for i, result in enumerate(unified_output.results[:5], 1):
            summary_parts.append(f"  [{i}] {result.title}")
            summary_parts.append(f"      {result.url}")
            if result.snippet:
                snippet = (
                    result.snippet[:100] + "..." if len(result.snippet) > 100 else result.snippet
                )
                summary_parts.append(f"      {snippet}")
        summary_parts.append("")

    # Wikipedia section
    if unified_output.wikipedia:
        summary_parts.append(f"### Wikipedia: {unified_output.wikipedia.title}")
        wiki_summary = unified_output.wikipedia.summary
        if len(wiki_summary) > 500:
            wiki_summary = wiki_summary[:500] + "..."
        summary_parts.append(wiki_summary)
        summary_parts.append(f"\n🔗 {unified_output.wikipedia.url}")
        summary_parts.append("")

    # Related questions
    if unified_output.related_questions:
        summary_parts.append("### Questions connexes")
        for q in unified_output.related_questions[:3]:
            summary_parts.append(f"  - {q}")

    summary = "\n".join(summary_parts)

    logger.info(
        "unified_web_search_success",
        user_id=str(user_uuid),
        query=query[:50],
        sources_used=sources_used,
        results_count=len(unified_output.results),
        has_wikipedia=unified_output.wikipedia is not None,
        has_synthesis=unified_output.synthesis is not None,
    )

    result_metadata = {
        "query": query,
        "sources_used": sources_used,
        "results_count": len(unified_output.results),
        "has_wikipedia": unified_output.wikipedia is not None,
        "has_synthesis": unified_output.synthesis is not None,
        "web_search": unified_output.model_dump(),
        "from_cache": False,
    }

    # --- Cache store (after successful results) ---
    try:
        redis_client = await get_redis_cache()
        cache = WebSearchCache(redis_client)
        await cache.set_search(
            user_id=user_uuid,
            query=query,
            data={
                "message": summary,
                "metadata": result_metadata,
            },
            recency=recency,
        )
    except Exception as e:
        logger.warning("web_search_cache_store_failed", error=str(e))

    return UnifiedToolOutput.data_success(
        message=summary,
        registry_updates={item_id: registry_item},
        metadata=result_metadata,
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "unified_web_search_tool",
    "WebSearchResult",
    "WikipediaResult",
    "UnifiedWebSearchOutput",
]
