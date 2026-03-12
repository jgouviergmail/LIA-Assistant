"""
Knowledge Enrichment Service - Brave Search API integration.

Enrichit les réponses avec des données actualisées (Web + News) via Brave Search.

Architecture:
- Singleton service avec lazy Redis init
- User Connector pattern: API key par utilisateur (comme Perplexity)
- Non-bloquant: retourne None si connecteur non configuré/désactivé
- Cache global: mêmes résultats pour tous les utilisateurs (clé basée sur query+endpoint)

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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from src.core.config import settings
from src.core.constants import (
    BRAVE_SEARCH_ENRICHMENT_TIMEOUT,
    BRAVE_SEARCH_MAX_CONTEXT_CHARS,
    BRAVE_SEARCH_MAX_RESULTS,
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

# Type alias for Brave Search endpoints
BraveSearchEndpoint = Literal["web", "news"]


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass(frozen=True)
class KnowledgeContext:
    """Brave Search enrichment result for knowledge injection into LLM prompts."""

    keyword: str
    endpoint: str  # "web" or "news"
    results: tuple[dict[str, str], ...]  # Immutable tuple of {title, description, url}
    from_cache: bool

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
        parts = [f"[Source: Brave {self.endpoint.title()} Search - {self.keyword}]"]

        for i, result in enumerate(self.results[:3], 1):
            title = result.get("title", "")
            desc = result.get("description", "")
            # Truncate description to max chars
            if len(desc) > BRAVE_SEARCH_MAX_CONTEXT_CHARS:
                desc = desc[:BRAVE_SEARCH_MAX_CONTEXT_CHARS].rsplit(" ", 1)[0] + "..."
            parts.append(f"{i}. {title}: {desc}")

        return "\n".join(parts)


# =============================================================================
# SINGLETON SERVICE
# =============================================================================


class KnowledgeEnrichmentService:
    """
    Service singleton pour l'enrichissement des connaissances via Brave Search.

    Pattern: Singleton avec lazy Redis init (comme PlanPatternLearner).
    Note: Utilise ToolDependencies injecté via config pour accès DB (pas de session propre).

    Thread Safety:
        Le service utilise ToolDependencies qui fournit ConcurrencySafeConnectorService,
        garantissant la sérialisation des accès DB concurrent.
    """

    def __init__(self) -> None:
        """Initialize service (Redis lazy-loaded)."""
        self._redis: Any = None
        # Per-user per-language clients (user_id:language → client)
        self._clients: dict[str, BraveSearchClient] = {}

    async def _ensure_redis(self) -> Any:
        """Lazy-load Redis client."""
        if self._redis is not None:
            return self._redis

        try:
            from src.infrastructure.cache.redis import get_redis_cache

            self._redis = await get_redis_cache()
            return self._redis
        except Exception as e:
            logger.debug(
                "knowledge_enrichment_redis_unavailable",
                error=str(e),
            )
            return None

    async def _get_client(
        self,
        credentials: APIKeyCredentials,
        user_id: UUID,
        language: str = "fr",
    ) -> BraveSearchClient:
        """
        Get or create Brave Search client for user.

        Args:
            credentials: Pre-fetched credentials from ConnectorService
            user_id: User ID for logging
            language: Language code for search

        Returns:
            BraveSearchClient instance (cached by user+language)
        """
        # Cache key: user_id:language
        cache_key = f"{user_id}:{language}"
        if cache_key not in self._clients:
            from src.domains.connectors.clients.brave_search_client import BraveSearchClient

            self._clients[cache_key] = BraveSearchClient(
                api_key=credentials.api_key,
                language=language,
                user_id=user_id,
            )
        return self._clients[cache_key]

    async def enrich(
        self,
        keywords: list[str],
        is_news_query: bool = False,
        user_id: UUID | None = None,
        language: str = "fr",
        tool_deps: ToolDependencies | None = None,
    ) -> KnowledgeContext | None:
        """
        Enrichir via Brave Search (Web ou News selon is_news_query).

        Non-bloquant: retourne None si connecteur non configuré/désactivé.

        Args:
            keywords: Liste de keywords extraits par QueryAnalyzer
            is_news_query: True si query demande des actualités (utilise News endpoint)
            user_id: User ID (required for user-specific API key)
            language: Language code (fr, en, etc.)
            tool_deps: ToolDependencies injecté depuis config (pour accès ConnectorService)

        Returns:
            KnowledgeContext or None if no enrichment available

        Note:
            This method is designed to be non-blocking. If any prerequisite is missing
            (feature disabled, no user_id, no tool_deps, connector not configured),
            it returns None immediately without raising exceptions.
        """
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

        # Check connector global config (admin can disable)
        if not await self._check_connector_enabled(tool_deps):
            logger.debug("brave_search_connector_disabled_by_admin")
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
            from datetime import datetime

            current_year = datetime.now().year
            keyword = f"{keyword} {current_year}"

        # Try cache first (global cache - same results for all users)
        redis = await self._ensure_redis()
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
            tool_deps=tool_deps,
            redis=redis,
        )

    async def _check_cache(
        self,
        redis: Any,
        keyword: str,
        endpoint: BraveSearchEndpoint,
        language: str,
    ) -> KnowledgeContext | None:
        """
        Check cache for existing results.

        Args:
            redis: Redis client
            keyword: Search keyword
            endpoint: "web" or "news"
            language: Language code

        Returns:
            KnowledgeContext if cache hit, None otherwise
        """
        query_hash = make_query_hash(keyword)
        cache_key = f"brave_search:{endpoint}:{language}:{query_hash}"

        try:
            cached = await redis.get(cache_key)
            if cached:
                cache_result = parse_cache_entry(
                    cached_json=cached,
                    cache_type="brave_search",
                    context_info={"keyword": keyword, "endpoint": endpoint},
                )
                if (
                    cache_result.from_cache
                    and cache_result.data
                    and cache_result.data.get("results")
                ):
                    logger.info(
                        "knowledge_enrichment_cache_hit",
                        keyword=keyword,
                        endpoint=endpoint,
                        cache_age_seconds=cache_result.cache_age_seconds,
                    )
                    return KnowledgeContext(
                        keyword=keyword,
                        endpoint=endpoint,
                        results=tuple(cache_result.data["results"]),
                        from_cache=True,
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
        tool_deps: ToolDependencies,
        redis: Any,
    ) -> KnowledgeContext | None:
        """
        Call Brave Search API and cache results.

        Args:
            keyword: Search keyword
            endpoint: "web" or "news"
            is_news_query: True for news endpoint
            user_id: User ID for credentials lookup
            language: Language code
            tool_deps: ToolDependencies for DB access
            redis: Redis client (may be None)

        Returns:
            KnowledgeContext or None if error/no results
        """
        try:
            # Get credentials via ConnectorService (from ToolDependencies)
            connector_service = await tool_deps.get_connector_service()
            credentials = await connector_service.get_api_key_credentials(
                user_id, ConnectorType.BRAVE_SEARCH
            )

            if credentials is None:
                # Non-blocking: user hasn't configured Brave Search connector
                logger.debug(
                    "brave_search_connector_not_configured",
                    user_id=str(user_id),
                )
                return None

            # Get or create client
            client = await self._get_client(credentials, user_id, language)

            # Call API with timeout + auto-set freshness for news queries (last 7 days)
            freshness = "pw" if is_news_query else None

            api_response = await asyncio.wait_for(
                client.search(
                    query=keyword,
                    endpoint=endpoint,
                    count=BRAVE_SEARCH_MAX_RESULTS,
                    freshness=freshness,
                ),
                timeout=BRAVE_SEARCH_ENRICHMENT_TIMEOUT,
            )

            if not api_response:
                logger.info("knowledge_enrichment_no_results", keyword=keyword, endpoint=endpoint)
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
                keyword=keyword,
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
                keyword=keyword,
                endpoint=endpoint,
                timeout=BRAVE_SEARCH_ENRICHMENT_TIMEOUT,
            )
            return None

        except Exception as e:
            logger.warning(
                "knowledge_enrichment_error",
                keyword=keyword,
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
    ) -> None:
        """
        Cache search results to Redis.

        Args:
            redis: Redis client
            keyword: Search keyword
            endpoint: "web" or "news"
            language: Language code
            results: Parsed results to cache
        """
        try:
            query_hash = make_query_hash(keyword)
            cache_key = f"brave_search:{endpoint}:{language}:{query_hash}"

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
                logger.info("brave_search_connector_disabled", reason=config.disabled_reason)
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
