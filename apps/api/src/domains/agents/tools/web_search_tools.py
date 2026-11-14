"""
LangChain v1 tools for Unified Web Search operations.

Unified Triple Source Search: Perplexity AI + page links + Wikipedia.

The page links come from the person's own Brave key when they configured one,
else from the instance's SearXNG when the operator runs one (lot 18, ADR-307:
the person's choice wins, the instance serves who made none) — chosen in ONE
place, :func:`_search_links`. A link search that failed, whichever service it
asked, is said in what the model reads, never shown as « no links », and that
answer is not kept for the next call. What a search returns, and the text the
model reads of it, live in :mod:`web_search_output`.

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

Fallback Matrix (L = the page links, Brave or the instance's SearXNG):
    | P | L | W | Result                     |
    |---|---|---|----------------------------|
    | Y | Y | Y | Triple source consolidated |
    | Y | Y | N | Perplexity + links         |
    | Y | N | Y | Perplexity + Wikipedia     |
    | N | Y | Y | Links + Wikipedia          |
    | Y | N | N | Perplexity only            |
    | N | Y | N | Links only                 |
    | N | N | Y | Wikipedia only             |
"""

import asyncio
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel

from src.core.config import settings
from src.core.i18n import _
from src.core.time_utils import get_current_datetime_context
from src.domains.agents.constants import (
    AGENT_WEB_SEARCH,
    CONTEXT_DOMAIN_WEB_SEARCH,
    WEB_SEARCH_SOURCE_BRAVE,
    WEB_SEARCH_SOURCE_PERPLEXITY,
    WEB_SEARCH_SOURCE_SEARXNG,
    WEB_SEARCH_SOURCE_WIKIPEDIA,
)
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_user_id_str
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences, parse_user_id
from src.domains.agents.tools.web_search_output import (
    UnifiedWebSearchOutput,
    WebSearchResult,
    WikipediaResult,
    failure_line,
    render_summary,
)
from src.domains.connectors.clients.brave_search_client import BraveSearchClient
from src.domains.connectors.clients.perplexity_client import PerplexityClient
from src.domains.connectors.clients.searxng_client import SearXNGRecency
from src.domains.connectors.clients.wikipedia_client import WikipediaClient, wikipedia_edition
from src.domains.connectors.instance_search import (
    WebLink,
    instance_search_available,
    search_instance,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials
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
# The same words are SearXNG's ``time_range`` (lot 18).
_INSTANCE_RECENCY: dict[str, SearXNGRecency] = {
    "day": "day",
    "week": "week",
    "month": "month",
    "year": "year",
}

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


async def _api_key_credentials(
    user_uuid: UUID, connector_type: ConnectorType
) -> APIKeyCredentials | None:
    """The account's key for a search provider (API-key connector, not OAuth).

    Read in a session of its own, closed before the provider is asked
    (ADR-304): a search can take seconds, and no transaction waits on one.

    Args:
        user_uuid: Whose key.
        connector_type: The search provider.

    Returns:
        The decrypted key, or None when the connector is not configured.
    """
    async with get_db_context() as db:
        return await ConnectorService(db).get_api_key_credentials(
            user_id=user_uuid, connector_type=connector_type
        )


async def _search_perplexity(
    query: str,
    user_uuid: UUID,
    user_timezone: str,
    user_language: str,
    recency: str | None,
) -> dict[str, Any] | None:
    """
    Execute Perplexity search with the person's own key.

    Returns:
        A dict with answer, citations and related_questions, or None when the
        person has no Perplexity key (nobody was asked).

    Raises:
        Exception: The search failed. The caller says so (ADR-303): a None here
            would read as « no key ».
    """
    credentials = await _api_key_credentials(user_uuid, ConnectorType.PERPLEXITY)
    if not credentials:
        logger.debug("perplexity_not_configured", user_id=str(user_uuid))
        return None

    client = PerplexityClient(
        api_key=credentials.api_key,
        user_id=user_uuid,
        model=settings.perplexity_search_model,
    )
    try:
        # Build system prompt with datetime context
        current_datetime = get_current_datetime_context(
            timezone_str=user_timezone,
            language=user_language,
        )
        result = await client.search(
            query=query,
            search_recency_filter=recency if recency in _VALID_RECENCY else None,
            return_citations=True,
            return_related_questions=True,
            system_prompt=f"Current date and time: {current_datetime}",
        )
    finally:
        # Deterministic close of the pooled httpx client (leak fix)
        await client.close()

    logger.info(
        "perplexity_search_success",
        user_id=str(user_uuid),
        query_length=len(query),
        citations_count=len(result.get("citations", [])),
    )

    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "related_questions": result.get("related_questions", []),
    }


async def _search_brave(
    query: str,
    credentials: APIKeyCredentials,
    *,
    user_uuid: UUID,
    count: int = 5,
    freshness: str | None = None,
    endpoint: Literal["web", "news"] = "web",
) -> list[WebSearchResult]:
    """
    Execute Brave Search with the person's own key.

    Args:
        query: Search query
        credentials: The person's Brave key
        user_uuid: Whose search (logging, rate-limit scope)
        count: Number of results
        freshness: Brave freshness filter (pd, pw, pm, py)
        endpoint: "web" for general search, "news" for news-specific results

    Returns:
        The links Brave found; none is an answer.

    Raises:
        Exception: The search failed. The caller says so (ADR-303): the client's
            None-on-error door would read as « no links ».
    """
    client = BraveSearchClient(
        api_key=credentials.api_key,
        user_id=user_uuid,
    )
    try:
        result = await client.search_or_raise(
            query=query,
            endpoint=endpoint,
            count=count,
            freshness=freshness,
        )
    finally:
        # Deterministic close of the pooled httpx client (leak fix)
        await client.close()

    # Extract results based on endpoint (different response formats)
    if endpoint == "web":
        raw_results = result.get("web", {}).get("results", [])
    else:
        raw_results = result.get("results", [])

    logger.info(
        "brave_search_success",
        user_id=str(user_uuid),
        query_length=len(query),
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


@dataclass(frozen=True)
class _LinkSearch:
    """The page links of one search, and which service was asked for them.

    Attributes:
        source: ``brave``, ``searxng``, or None when this account has neither.
        results: The links found.
        failed: The service was asked and did not answer.
    """

    source: str | None
    results: list[WebSearchResult] = field(default_factory=list)
    failed: bool = False


def _instance_result(link: WebLink) -> WebSearchResult:
    """A link of the instance's search, its engine line (a news item's age and outlet) first."""
    return WebSearchResult(
        title=link.title, url=link.url, snippet=link.excerpt, source=WEB_SEARCH_SOURCE_SEARXNG
    )


async def _search_links(
    query: str,
    user_uuid: UUID,
    user_language: str,
    recency: str | None,
) -> _LinkSearch:
    """The page links of a search: the person's Brave key wins, else the instance's search.

    Args:
        query: Search query.
        user_uuid: Whose search.
        user_language: The person's language (the instance's search reads it).
        recency: Normalized freshness (day/week/month/year) or None.

    Returns:
        The links and the service that found them — or why there are none.
    """
    # Recent queries (news, current events) read each service's news side
    recent = recency in ("day", "week")
    credentials = await _api_key_credentials(user_uuid, ConnectorType.BRAVE_SEARCH)
    if credentials is not None:
        try:
            results = await _search_brave(
                query,
                credentials,
                user_uuid=user_uuid,
                count=5,
                freshness=_BRAVE_FRESHNESS_MAP.get(recency or ""),
                endpoint="news" if recent else "web",
            )
        except Exception as error:
            # The person's choice stands: nobody answers in its place (ADR-382),
            # and its failure is one the model is told. The type, never the
            # message, which can quote the query (ADR-317).
            logger.warning(
                "brave_search_failed",
                user_id=str(user_uuid),
                error_type=type(error).__name__,
            )
            return _LinkSearch(WEB_SEARCH_SOURCE_BRAVE, failed=True)
        return _LinkSearch(WEB_SEARCH_SOURCE_BRAVE, results)
    if not await instance_search_available():
        logger.debug("web_links_no_source", user_id=str(user_uuid))
        return _LinkSearch(None)
    try:
        links = await search_instance(
            query,
            user_id=user_uuid,
            language=user_language,
            count=5,
            recency=_INSTANCE_RECENCY.get(recency or ""),
            news=recent,
        )
    except Exception:
        # Counted and logged by the door; here it is a failure the model is told.
        return _LinkSearch(WEB_SEARCH_SOURCE_SEARXNG, failed=True)
    return _LinkSearch(WEB_SEARCH_SOURCE_SEARXNG, [_instance_result(link) for link in links])


@dataclass(frozen=True)
class _Gathered:
    """What the three searches of one query brought back, and each source's part.

    Attributes:
        perplexity: Perplexity's answer, or None (no key, nothing, or it raised).
        links: The page-link search; a search that raised reads as failed.
        wikipedia: The Wikipedia article, or None (no article, or it raised).
        link_source: The service that holds the links (Brave when none answered).
        asked: Every source the search stands for, links included.
        used: The sources that brought something.
        failed: The sources that were asked and did not answer, in asking order.
    """

    perplexity: dict[str, Any] | None
    links: _LinkSearch
    wikipedia: WikipediaResult | None
    link_source: str
    asked: list[str]
    used: list[str]
    failed: list[str]


def _gathered(outcomes: list[Any]) -> _Gathered:
    """Type the three outcomes of ``asyncio.gather`` and account for each source.

    A source that raised is logged by its type, never its message, which can quote
    the query (ADR-317), and it FAILED: never « no key », « no links » or « no
    article » (ADR-303).

    Args:
        outcomes: Perplexity's, the links' and Wikipedia's results, in that order.

    Returns:
        The typed results and which sources were asked, used and failed.
    """
    raised = [isinstance(outcome, BaseException) for outcome in outcomes]
    for source_name, outcome in zip(("perplexity", "links", "wikipedia"), outcomes, strict=True):
        if isinstance(outcome, BaseException):
            logger.warning(
                "web_search_source_exception",
                source=source_name,
                error_type=type(outcome).__name__,
            )
    perplexity, raw_links, wikipedia = (
        None if isinstance(outcome, BaseException) else outcome for outcome in outcomes
    )
    links = raw_links if isinstance(raw_links, _LinkSearch) else _LinkSearch(None, failed=True)
    link_source = links.source or WEB_SEARCH_SOURCE_BRAVE
    brought = (
        (WEB_SEARCH_SOURCE_PERPLEXITY, perplexity, raised[0]),
        (link_source, links.results, links.failed),
        (WEB_SEARCH_SOURCE_WIKIPEDIA, wikipedia, raised[2]),
    )
    return _Gathered(
        perplexity=perplexity,
        links=links,
        wikipedia=wikipedia,
        link_source=link_source,
        asked=[source for source, _found, _failed in brought],
        used=[source for source, found, _failed in brought if found],
        failed=[source for source, _found, failed in brought if failed],
    )


async def _kept_search(
    user_uuid: UUID, query: str, recency: str | None
) -> UnifiedToolOutput | None:
    """The answer kept for this question, when it was asked shortly before (best effort).

    The registry items are not kept (they cannot be rebuilt from plain data
    without loss): the message holds everything the agent needs.

    Args:
        user_uuid: Whose search.
        query: Search query.
        recency: Normalized freshness, part of the key.

    Returns:
        The kept answer marked as such, or None when there is none to serve.
    """
    try:
        found = await WebSearchCache(await get_redis_cache()).get_search(user_uuid, query, recency)
    except Exception as e:
        logger.warning("web_search_cache_check_failed", error=str(e))
        return None
    if not (found.from_cache and found.data):
        return None
    logger.info(
        "unified_web_search_from_cache",
        user_id=str(user_uuid),
        query_length=len(query),
        cache_age_seconds=found.cache_age_seconds,
    )
    return UnifiedToolOutput.data_success(
        message=found.data.get("message", ""),
        metadata={
            **found.data.get("metadata", {}),
            "from_cache": True,
            "cache_age_seconds": found.cache_age_seconds,
        },
    )


async def _keep_search(
    user_uuid: UUID,
    query: str,
    recency: str | None,
    summary: str,
    metadata: dict[str, Any],
) -> None:
    """Keep a search's answer for the same question asked again shortly (best effort).

    Args:
        user_uuid: Whose search.
        query: Search query.
        recency: Normalized freshness, part of the key.
        summary: What the model read.
        metadata: What the tool returned beside it.
    """
    try:
        cache = WebSearchCache(await get_redis_cache())
        await cache.set_search(
            user_id=user_uuid,
            query=query,
            data={"message": summary, "metadata": metadata},
            recency=recency,
        )
    except Exception as e:
        logger.warning("web_search_cache_store_failed", error=str(e))


async def _search_wikipedia(
    query: str,
    language: str | None = None,
) -> WikipediaResult | None:
    """
    Execute Wikipedia search - always available (no auth).

    Returns:
        The most relevant article, or None when the encyclopedia has none.

    Raises:
        Exception: The search failed. The caller says so (ADR-303): a None here
            would read as « no article ».
    """
    language = wikipedia_edition(language)
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
        query_length=len(query),
        summary_length=len(extract),
    )

    return WikipediaResult(
        title=article_title,
        summary=extract,
        url=url,
    )


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
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Comprehensive web search combining three sources in parallel.

    Executes Perplexity AI (synthesis), Brave Search (URLs), and Wikipedia (encyclopedia)
    simultaneously. Returns a unified result set with fallback handling.

    Fallback Chain:
    - If Perplexity fails: Continue with Brave + Wikipedia
    - If Brave fails: Continue with Perplexity + Wikipedia
    - Wikipedia is always queried (it needs no per-account key)

    Args:
        query: Search query or question (e.g., "bolognese pasta recipe", "who is Einstein")
        recency: Optional freshness filter:
            - "day": Last 24 hours
            - "week": Last 7 days
            - "month": Last 30 days
            - None: No time filter (default)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with combined results from all available sources

    Examples:
        - unified_web_search("bolognese pasta recipe allrecipes")
        - unified_web_search("latest AI news", recency="week")
        - unified_web_search("who is Albert Einstein")
    """
    # Extract user context from runtime
    user_uuid = None

    if runtime and runtime.config:
        user_id_raw = tool_user_id_str(runtime)
        if user_id_raw:
            try:
                user_uuid = parse_user_id(user_id_raw)
            except ValueError as e:
                logger.warning("invalid_user_id_format", error=str(e))

    if not user_uuid:
        return UnifiedToolOutput.failure(
            message="User context required for web search",  # internal, for the model
            error_code="USER_CONTEXT_MISSING",
            metadata={"query": query},
        )

    # Get user preferences from DB (centralized pattern from runtime_helpers)
    user_timezone, user_language, _locale = await get_user_preferences(runtime)

    # Normalize recency to valid values (planner may pass non-standard values like "7d")
    recency = _normalize_recency(recency)

    # The same question asked again shortly is answered from what was kept
    kept = None if force_refresh else await _kept_search(user_uuid, query, recency)
    if kept is not None:
        return kept

    # Execute all three searches in parallel
    perplexity_task = _search_perplexity(
        query=query,
        user_uuid=user_uuid,
        user_timezone=user_timezone,
        user_language=user_language,
        recency=recency,
    )
    # The page links: the person's Brave key, else the instance's search (lot 18)
    links_task = _search_links(
        query=query,
        user_uuid=user_uuid,
        user_language=user_language,
        recency=recency,
    )
    wikipedia_task = _search_wikipedia(
        query=query,
        language=user_language,
    )

    # Gather with return_exceptions to handle partial failures
    results = await asyncio.gather(
        perplexity_task,
        links_task,
        wikipedia_task,
        return_exceptions=True,
    )

    # The three outcomes, typed, and which sources were asked, used and failed
    gathered = _gathered(list(results))
    perplexity_result, link_search = gathered.perplexity, gathered.links
    wikipedia_result = gathered.wikipedia
    all_sources, sources_used = gathered.asked, gathered.used
    sources_failed = gathered.failed

    # Check if we have any results
    if not sources_used:
        message = _("No search results found from any source for '{query}'").format(query=query)
        # « Nothing found » and « nobody answered » are two answers: each failure is said.
        message = " ".join([message, *(failure_line(source) for source in sources_failed)])
        return UnifiedToolOutput.failure(
            message=message,
            error_code="NO_RESULTS",
            metadata={
                "query": query,
                "sources": all_sources,
                "sources_used": [],
                "sources_failed": sources_failed,
            },
        )

    # Build unified output
    answer = perplexity_result or {}
    unified_output = UnifiedWebSearchOutput(
        query=query,
        synthesis=answer.get("answer"),
        results=link_search.results,
        wikipedia=wikipedia_result,
        sources=all_sources,
        sources_used=sources_used,
        related_questions=answer.get("related_questions", []),
        citations=answer.get("citations", []),
    )

    # Create registry item
    item_id = generate_registry_id(
        RegistryItemType.WEB_SEARCH,
        f"web_search_{query}",
    )

    registry_item = RegistryItem(
        id=item_id,
        type=RegistryItemType.WEB_SEARCH,
        # The output's own fields, in their order, then what kind of item this is
        payload={**unified_output.model_dump(), "type": "unified_web_search"},
        meta=RegistryItemMeta(
            source="web_search",
            domain=CONTEXT_DOMAIN_WEB_SEARCH,
            tool_name="unified_web_search",
        ),
    )

    # What the model reads: each provider's words wrapped, each source's failure said
    summary = render_summary(unified_output, failed_sources=sources_failed)

    logger.info(
        "unified_web_search_success",
        user_id=str(user_uuid),
        query_length=len(query),
        sources_used=sources_used,
        results_count=len(unified_output.results),
        has_wikipedia=unified_output.wikipedia is not None,
        has_synthesis=unified_output.synthesis is not None,
    )

    result_metadata = {
        "query": query,
        "sources_used": sources_used,
        "results_count": len(unified_output.results),
        "sources_failed": sources_failed,
        "has_wikipedia": unified_output.wikipedia is not None,
        "has_synthesis": unified_output.synthesis is not None,
        "web_search": unified_output.model_dump(),
        "from_cache": False,
    }

    # A search one of whose sources failed is not kept: the next identical call is
    # the retry, and « did not answer this time » is not true of a later one.
    if not sources_failed:
        await _keep_search(user_uuid, query, recency, summary, result_metadata)

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
