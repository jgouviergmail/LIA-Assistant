"""
Knowledge Enrichment Service - web search integration.

Enriches answers with up-to-date data (Web + News) through Brave Search, with
the person's own key. A person with no key (or whose Brave the administrator
switched off) is enriched by the instance's SearXNG when the operator runs one
(lot 18, ``connectors/instance_search``): recorded as its own capability
(``enrichment:searxng``), cached apart, named for what it is in the prompt.

Architecture:
- Singleton service with lazy Redis init
- User Connector pattern: one API key per user (like Perplexity)
- Non-blocking: returns None when the connector is not configured or disabled
- Global cache: the same results for every user (key built on the endpoint,
  the language and a hash of the query)

Usage:
    service = get_knowledge_enrichment_service()
    context = await service.enrich(
        keywords=["machine learning"],
        is_news_query=False,
        user_id=user_id,
        language="fr",
        tool_deps=tool_deps,
    )
    if context:
        prompt_context = context.to_prompt_context()
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal

from src.core.config import settings
from src.core.constants import (
    BRAVE_SEARCH_MAX_CONTEXT_CHARS,
    BRAVE_SEARCH_MAX_RESULTS,
)
from src.core.i18n import resolve_language
from src.domains.connectors.clients.searxng_client import SearXNGRecency
from src.domains.connectors.instance_search import (
    INSTANCE_SEARCH_SOURCE,
    WebLink,
    instance_search_available,
    search_instance,
)
from src.domains.connectors.models import ConnectorType
from src.infrastructure.cache.base import create_cache_entry, make_query_hash, parse_cache_entry
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from uuid import UUID

    from src.domains.agents.dependencies import ToolDependencies
    from src.domains.connectors.clients.brave_search_client import BraveSearchClient
    from src.domains.connectors.schemas import APIKeyCredentials

logger = get_logger(__name__)

# Redis DI seam — same contract as PlanPatternLearner.RedisProvider: the client
# is resolved on demand and never cached on the instance, so close_redis() is
# honoured and tests can inject a mock (AC-010).
RedisProvider = Callable[[], Awaitable[Any]]

# Type alias for Brave Search endpoints
BraveSearchEndpoint = Literal["web", "news"]

#: The search service of an enrichment, as the cache and the prompt name it.
BRAVE_SOURCE = "brave"
_SOURCE_LABELS: dict[str, str] = {BRAVE_SOURCE: "Brave", INSTANCE_SEARCH_SOURCE: "SearXNG"}
#: How far back the instance's news search looks, as Brave's news freshness does.
_INSTANCE_NEWS_RECENCY: SearXNGRecency = "week"


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass(frozen=True)
class KnowledgeContext:
    """Web search enrichment result for knowledge injection into LLM prompts."""

    keyword: str
    endpoint: str  # "web" or "news"
    results: tuple[dict[str, str], ...]  # Immutable tuple of {title, description, url}
    from_cache: bool
    source: str = BRAVE_SOURCE  # which service found them (lot 18)

    def to_prompt_context(self) -> str:
        """
        Format results for LLM prompt injection.

        Returns:
            Formatted string for system prompt injection, or empty string if no results.

        Example:
            [Source: Brave Web Search - machine learning]
            1. Introduction to ML: Machine learning is a subset of AI...
            2. Deep Learning Guide: Deep learning uses neural networks...
        """
        if not self.results:
            return ""

        # Build context text
        label = _SOURCE_LABELS.get(self.source, self.source)
        parts = [f"[Source: {label} {self.endpoint.title()} Search - {self.keyword}]"]

        for i, result in enumerate(self.results[:3], 1):
            title = result.get("title", "")
            desc = result.get("description", "")
            # Truncate description to max chars
            if len(desc) > BRAVE_SEARCH_MAX_CONTEXT_CHARS:
                desc = desc[:BRAVE_SEARCH_MAX_CONTEXT_CHARS].rsplit(" ", 1)[0] + "..."
            parts.append(f"{i}. {title}: {desc}")

        return "\n".join(parts)


def _cache_key(source: str, keyword: str, endpoint: str, language: str) -> str:
    """One cache key per service: a link one service found is never served as another's."""
    return f"{source}_search:{endpoint}:{language}:{make_query_hash(keyword)}"


def _instance_result(link: WebLink) -> dict[str, str]:
    """A link of the instance's search as the prompt reads one, its engine line first."""
    return {"title": link.title, "description": link.excerpt, "url": link.url}


# =============================================================================
# SINGLETON SERVICE
# =============================================================================


class KnowledgeEnrichmentService:
    """
    Singleton service enriching knowledge through Brave Search.

    Pattern: singleton with lazy Redis init (like PlanPatternLearner).
    Note: uses the ToolDependencies injected through the config for database
    access (no session of its own).

    Thread Safety:
        The service uses ToolDependencies, which provides
        ConcurrencySafeConnectorService and so serialises concurrent database access.
    """

    def __init__(self, redis_provider: RedisProvider | None = None) -> None:
        """Initialize service (Redis resolved lazily via the provider seam)."""
        # None => fetch the process-wide client fresh on each call (never
        # cached, so close_redis() is honoured — AC-010). Tests inject a mock.
        self._redis_provider = redis_provider

    async def _ensure_redis(self) -> Any:
        """Resolve the Redis client via the provider (never cached — AC-010)."""
        try:
            if self._redis_provider is not None:
                return await self._redis_provider()

            from src.infrastructure.cache.redis import get_redis_cache

            return await get_redis_cache()
        except Exception as e:
            logger.debug(
                "knowledge_enrichment_redis_unavailable",
                error=str(e),
            )
            return None

    @staticmethod
    def _new_client(
        credentials: APIKeyCredentials,
        user_id: UUID,
        language: str | None = None,
    ) -> BraveSearchClient:
        """
        A Brave Search client for ONE search — the caller closes it.

        Never cached: the service is a process singleton, and a cache keyed
        by person kept a rotated key for the life of the process, never
        closed its connection pools and grew without bound.

        Args:
            credentials: Pre-fetched credentials from ConnectorService
            user_id: User ID for logging
            language: Language code for search; the declared language
                when absent (ADR-323)

        Returns:
            A new BraveSearchClient.
        """
        from src.domains.connectors.clients.brave_search_client import BraveSearchClient

        return BraveSearchClient(
            api_key=credentials.api_key,
            language=language or resolve_language(),
            user_id=user_id,
        )

    async def enrich(
        self,
        keywords: list[str],
        is_news_query: bool = False,
        user_id: UUID | None = None,
        language: str | None = None,
        tool_deps: ToolDependencies | None = None,
    ) -> KnowledgeContext | None:
        """
        Enrich through Brave Search (Web or News, per is_news_query).

        Non-blocking: returns None when the connector is not configured or is disabled.

        Args:
            keywords: Keywords extracted by the QueryAnalyzer
            is_news_query: True when the query asks for news (uses the News endpoint)
            user_id: User ID (required for user-specific API key)
            language: The person's language code; the declared language when
                absent (ADR-323)
            tool_deps: ToolDependencies injected from config (for ConnectorService access)

        Returns:
            KnowledgeContext or None if no enrichment available

        Note:
            This method is designed to be non-blocking. If any prerequisite is missing
            (feature disabled, no user_id, no tool_deps, connector not configured),
            it returns None immediately without raising exceptions.
        """
        language = language or resolve_language()
        # Check if feature enabled globally
        if not settings.knowledge_enrichment_enabled:
            logger.debug("knowledge_enrichment_disabled")
            return None

        # User ID required for user-specific API key
        if user_id is None:
            logger.debug("knowledge_enrichment_no_user_id")
            return None

        # ToolDependencies required for DB access
        if tool_deps is None:
            logger.debug("knowledge_enrichment_no_deps")
            return None

        # Combine keywords (max 3 for better context)
        if not keywords:
            logger.debug("knowledge_enrichment_no_keywords")
            return None

        # Combine top 3 keywords for richer search query
        keyword = " ".join(keywords[:3])
        endpoint: BraveSearchEndpoint = "news" if is_news_query else "web"

        # For non-news queries (encyclopedic), append current year to get recent info
        # This helps with time-sensitive questions like "when is Chinese New Year"
        if not is_news_query:
            current_year = datetime.now(UTC).year
            keyword = f"{keyword} {current_year}"

        # The person's own key wins (ADR-307); without one, the instance's search
        credentials = await self._brave_credentials(user_id, tool_deps)
        redis = await self._ensure_redis()
        if credentials is None:
            return await self._enrich_from_instance(
                keyword=keyword,
                endpoint=endpoint,
                is_news_query=is_news_query,
                user_id=user_id,
                language=language,
                redis=redis,
            )

        # Try cache first (global cache - same results for all users)
        if redis:
            cache_result = await self._check_cache(redis, keyword, endpoint, language)
            if cache_result:
                return cache_result

        # Call Brave Search API
        return await self._call_api(
            keyword=keyword,
            endpoint=endpoint,
            is_news_query=is_news_query,
            user_id=user_id,
            language=language,
            credentials=credentials,
            redis=redis,
        )

    async def _brave_credentials(
        self, user_id: UUID, tool_deps: ToolDependencies
    ) -> APIKeyCredentials | None:
        """The person's Brave key, when they configured one and the administrator allows Brave.

        Args:
            user_id: Whose key.
            tool_deps: ToolDependencies for ConnectorService access.

        Returns:
            The key, or None: not configured, switched off, or unreadable.
        """
        if not await self._check_connector_enabled(tool_deps):
            logger.debug("brave_search_connector_disabled_by_admin")
            return None
        try:
            connector_service = await tool_deps.get_connector_service()
            credentials: APIKeyCredentials | None = await connector_service.get_api_key_credentials(
                user_id, ConnectorType.BRAVE_SEARCH
            )
        except Exception as exc:
            # A revoked or unreadable key is no usable key; the type, never the text.
            logger.warning("brave_search_credentials_unreadable", error_type=type(exc).__name__)
            return None
        if credentials is None:
            logger.debug("brave_search_connector_not_configured", user_id=str(user_id))
        return credentials

    async def _enrich_from_instance(
        self,
        *,
        keyword: str,
        endpoint: BraveSearchEndpoint,
        is_news_query: bool,
        user_id: UUID,
        language: str,
        redis: Any,
    ) -> KnowledgeContext | None:
        """Enrich through the instance's SearXNG (lot 18), for a person with no Brave key.

        Args:
            keyword: Search keyword.
            endpoint: "web" or "news".
            is_news_query: True for news (the news category, the last week).
            user_id: Whose search.
            language: Language code.
            redis: Redis client (may be None).

        Returns:
            KnowledgeContext, or None: no instance search, a failure, or nothing found.
        """
        if not await instance_search_available():
            logger.debug("knowledge_enrichment_no_search_source", user_id=str(user_id))
            return None
        if redis:
            cached = await self._check_cache(
                redis, keyword, endpoint, language, source=INSTANCE_SEARCH_SOURCE
            )
            if cached:
                return cached
        from src.domains.agents.effects.treatments import record_treatment

        started = perf_counter()
        succeeded = False
        try:
            links = await search_instance(
                keyword,
                user_id=user_id,
                language=language,
                count=BRAVE_SEARCH_MAX_RESULTS,
                recency=_INSTANCE_NEWS_RECENCY if is_news_query else None,
                news=is_news_query,
            )
            succeeded = True
        except Exception:
            # Counted and logged by the door: an enrichment never fails a turn.
            return None
        finally:
            # Recorded through a cancellation too: success is only set by an answer.
            record_treatment(
                f"enrichment:{INSTANCE_SEARCH_SOURCE}",
                None,
                succeeded=succeeded,
                duration_ms=int((perf_counter() - started) * 1000),
            )
        results = [_instance_result(link) for link in links if link.title and link.excerpt]
        if not results:
            return None
        if redis:
            await self._cache_results(
                redis, keyword, endpoint, language, results, source=INSTANCE_SEARCH_SOURCE
            )
        return KnowledgeContext(
            keyword=keyword,
            endpoint=endpoint,
            results=tuple(results),
            from_cache=False,
            source=INSTANCE_SEARCH_SOURCE,
        )

    async def _check_cache(
        self,
        redis: Any,
        keyword: str,
        endpoint: BraveSearchEndpoint,
        language: str,
        source: str = BRAVE_SOURCE,
    ) -> KnowledgeContext | None:
        """
        Check cache for existing results.

        Args:
            redis: Redis client
            keyword: Search keyword
            endpoint: "web" or "news"
            language: Language code
            source: The service whose results are read: a link one service
                found is never served as another's.

        Returns:
            KnowledgeContext if cache hit, None otherwise
        """
        cache_key = _cache_key(source, keyword, endpoint, language)

        try:
            cached = await redis.get(cache_key)
            if cached:
                cache_result = parse_cache_entry(
                    cached_json=cached,
                    cache_type=f"{source}_search",
                    context_info={"keyword": keyword, "endpoint": endpoint},
                )
                if (
                    cache_result.from_cache
                    and cache_result.data
                    and cache_result.data.get("results")
                ):
                    logger.info(
                        "knowledge_enrichment_cache_hit",
                        keyword_length=len(keyword),
                        endpoint=endpoint,
                        cache_age_seconds=cache_result.cache_age_seconds,
                    )
                    return KnowledgeContext(
                        keyword=keyword,
                        endpoint=endpoint,
                        results=tuple(cache_result.data["results"]),
                        from_cache=True,
                        source=source,
                    )
        except Exception as e:
            logger.warning("knowledge_enrichment_cache_error", error=str(e))

        return None

    async def _call_api(
        self,
        keyword: str,
        endpoint: BraveSearchEndpoint,
        is_news_query: bool,
        user_id: UUID,
        language: str,
        credentials: APIKeyCredentials,
        redis: Any,
    ) -> KnowledgeContext | None:
        """
        Call Brave Search API with the person's key and cache results.

        Args:
            keyword: Search keyword
            endpoint: "web" or "news"
            is_news_query: True for news endpoint
            user_id: Whose search
            language: Language code
            credentials: The person's Brave key (:meth:`_brave_credentials`)
            redis: Redis client (may be None)

        Returns:
            KnowledgeContext or None if error/no results
        """
        try:
            # One client for this search, closed right after it.
            client = self._new_client(credentials, user_id, language)

            # Call API with timeout + auto-set freshness for news queries (last 7 days)
            freshness = "pw" if is_news_query else None

            # Recorded: this search reaches Brave through its CLIENT, so the
            # tool gate that fills the consultation register never sees it —
            # the same query is registered when the person asks for it through
            # brave_search_tool and silent when a node decides to run it. The
            # capability is what the register names, never the query.
            _started = perf_counter()
            _search_succeeded = False
            try:
                api_response = await asyncio.wait_for(
                    client.search(
                        query=keyword,
                        endpoint=endpoint,
                        count=BRAVE_SEARCH_MAX_RESULTS,
                        freshness=freshness,
                    ),
                    timeout=settings.brave_search_enrichment_timeout_seconds,
                )
                # The client answers None for a refusal it swallowed — a 403, a
                # 429, a 5xx, a network error (its None-on-error contract) — so
                # an answer is a response, never merely a return.
                _search_succeeded = api_response is not None
            finally:
                # Recorded BEFORE the close: a close that fails, or a second
                # cancellation arriving during it, must not lose the row. A
                # cancelled search did not succeed either — success is only
                # ever set by an answer.
                from src.domains.agents.effects.treatments import record_treatment

                record_treatment(
                    "enrichment:brave",
                    None,
                    succeeded=_search_succeeded,
                    duration_ms=int((perf_counter() - _started) * 1000),
                )
                try:
                    await client.close()
                except Exception as exc:  # noqa: BLE001 — the answer is already in hand
                    logger.warning(
                        "knowledge_enrichment_client_close_failed",
                        error_type=type(exc).__name__,
                    )

            if not api_response:
                logger.info(
                    "knowledge_enrichment_no_results",
                    keyword_length=len(keyword),
                    endpoint=endpoint,
                )
                return None

            # Parse results
            results = self._parse_results(api_response, endpoint)

            if not results:
                return None

            # Cache results (if Redis available)
            if redis:
                await self._cache_results(redis, keyword, endpoint, language, results)

            logger.info(
                "knowledge_enrichment_success",
                keyword_length=len(keyword),
                endpoint=endpoint,
                results_count=len(results),
            )

            return KnowledgeContext(
                keyword=keyword,
                endpoint=endpoint,
                results=tuple(results),
                from_cache=False,
            )

        except TimeoutError:
            logger.warning(
                "knowledge_enrichment_api_timeout",
                keyword_length=len(keyword),
                endpoint=endpoint,
                timeout=settings.brave_search_enrichment_timeout_seconds,
            )
            return None

        except Exception as e:
            logger.warning(
                "knowledge_enrichment_error",
                keyword_length=len(keyword),
                endpoint=endpoint,
                error=str(e),
            )
            return None

    async def _cache_results(
        self,
        redis: Any,
        keyword: str,
        endpoint: str,
        language: str,
        results: list[dict[str, str]],
        source: str = BRAVE_SOURCE,
    ) -> None:
        """
        Cache search results to Redis.

        Args:
            redis: Redis client
            keyword: Search keyword
            endpoint: "web" or "news"
            language: Language code
            results: Parsed results to cache
            source: The service that found them (its own key space)
        """
        try:
            cache_key = _cache_key(source, keyword, endpoint, language)

            cache_entry = create_cache_entry(
                {"results": results},
                ttl_seconds=settings.brave_search_cache_ttl_seconds,
            )
            await redis.set(
                cache_key,
                json.dumps(cache_entry),
                ex=settings.brave_search_cache_ttl_seconds,
            )
        except Exception as e:
            logger.warning("knowledge_enrichment_cache_write_error", error=str(e))

    def _parse_results(self, api_response: dict, endpoint: str) -> list[dict[str, str]]:
        """
        Parse Brave API response to extract results.

        Args:
            api_response: Raw API response
            endpoint: "web" or "news"

        Returns:
            List of {title, description, url}
        """
        results: list[dict[str, str]] = []

        if endpoint == "web":
            # Web search: results in web.results
            web_data = api_response.get("web", {})
            raw_results = web_data.get("results", [])
        else:
            # News search: results in top-level results
            raw_results = api_response.get("results", [])

        for item in raw_results[:BRAVE_SEARCH_MAX_RESULTS]:
            title = item.get("title", "")
            description = item.get("description", "")
            url = item.get("url", "")

            if title and description:
                results.append(
                    {
                        "title": title,
                        "description": description,
                        "url": url,
                    }
                )

        return results

    async def _check_connector_enabled(
        self,
        tool_deps: ToolDependencies,
    ) -> bool:
        """
        Check if Brave Search connector is globally enabled (admin control).

        Args:
            tool_deps: ToolDependencies for ConnectorService access

        Returns:
            True if enabled, False if disabled by admin
        """
        try:
            connector_service = await tool_deps.get_connector_service()
            # ConcurrencySafeConnectorService delegates to underlying service via __getattr__
            config = await connector_service.get_global_config(ConnectorType.BRAVE_SEARCH)

            # If no config exists, assume enabled (default)
            if config and not config.is_enabled:
                logger.info("brave_search_connector_disabled")
                return False

            return True
        except Exception as e:
            # If error checking config, assume enabled (fail-open)
            logger.warning("brave_search_config_check_error", error=str(e))
            return True


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_knowledge_enrichment_service: KnowledgeEnrichmentService | None = None


def get_knowledge_enrichment_service() -> KnowledgeEnrichmentService:
    """Get singleton instance."""
    global _knowledge_enrichment_service
    if _knowledge_enrichment_service is None:
        _knowledge_enrichment_service = KnowledgeEnrichmentService()
    return _knowledge_enrichment_service


def reset_knowledge_enrichment_service() -> None:
    """Reset singleton (for testing)."""
    global _knowledge_enrichment_service
    _knowledge_enrichment_service = None
