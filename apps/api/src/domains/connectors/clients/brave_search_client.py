"""
Brave Search API Client - Web & News Search.

Provides access to Brave Search API for knowledge enrichment.
Uses both Web Search and News Search endpoints.

API Reference:
- https://api.search.brave.com/app/documentation/web-search
- https://api.search.brave.com/app/documentation/news-search

Authentication:
- X-Subscription-Token header (user-specific API key from connector settings)
- Get key from: https://api.search.brave.com/register

Built on BaseAPIKeyClient (F2 migration): Redis-backed rate limiting with
local fallback, circuit breaker, retry with backoff, connection pooling.
The public contract is unchanged: ``search()`` returns the parsed response
dict, or **None on any error** — callers rely on the None-on-error contract
(``if not result: return []``).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from src.core.config import settings
from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class BraveSearchClient(BaseAPIKeyClient):
    """
    Client for Brave Search API (Web + News).

    Supports 2 endpoints:
    - Web Search: General encyclopedic knowledge
    - News Search: Recent news and current events

    Authentication: X-Subscription-Token header (user-specific API key from DB)

    Example:
        >>> client = BraveSearchClient(api_key="BSA...", user_id=uuid)
        >>> result = await client.search("Python programming", endpoint="web")
        >>> print(result["web"]["results"])
    """

    connector_type = ConnectorType.BRAVE_SEARCH
    api_base_url = "https://api.search.brave.com/res/v1"

    # Raw API key in a dedicated header (no Bearer prefix)
    auth_header_name = "X-Subscription-Token"
    auth_header_prefix = ""
    auth_method = "header"
    follow_redirects = True

    def __init__(
        self,
        api_key: str,
        language: str = "fr",
        user_id: UUID | None = None,
        rate_limit_per_second: float | None = None,
    ) -> None:
        """
        Initialize Brave Search client.

        Args:
            api_key: Brave Search API key (from user's connector settings)
            language: Language code for search_lang parameter (ISO 639-1: fr, en, etc.)
            user_id: Optional user ID for logging and rate-limit scoping
            rate_limit_per_second: Max requests per second (None = use settings)
        """
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_brave_search_per_second
        )
        super().__init__(
            user_id=user_id,
            credentials=APIKeyCredentials(api_key=api_key),
            rate_limit_per_second=effective_rate_limit,
        )
        self.api_key = api_key
        self.language = language

    def _get_http_timeout(self) -> float:
        """Brave has a dedicated (short) search timeout setting."""
        return float(settings.http_timeout_brave_search)

    async def search(
        self,
        query: str,
        endpoint: Literal["web", "news"] = "web",
        count: int = 5,
        freshness: str | None = None,
        country: str | None = None,
    ) -> dict | None:
        """
        Search via Brave API (Web or News).

        Args:
            query: Search query (keywords)
            endpoint: "web" for general search, "news" for news search
            count: Number of results (max 20 for web, 50 for news)
            freshness: Date filter (pd=24h, pw=7d, pm=31d, py=1y, or custom YYYY-MM-DDtoYYYY-MM-DD)
            country: 2-character country code (fr, us, etc.)

        Returns:
            API response dict or None if error (callers rely on None-on-error)

        Example:
            >>> result = await client.search("AI news", endpoint="news", freshness="pw")
            >>> print(result["results"][0]["title"])
        """
        # Validate endpoint
        if endpoint not in ("web", "news"):
            logger.error("brave_search_invalid_endpoint", endpoint=endpoint)
            return None

        # Build params
        params: dict = {
            "q": query,
            "count": min(count, 20 if endpoint == "web" else 50),
            "search_lang": self.language,
        }
        if freshness:
            params["freshness"] = freshness
        if country:
            params["country"] = country

        logger.info(
            "brave_search_request",
            endpoint=endpoint,
            query=query[:50],
            user_id=str(self.user_id) if self.user_id else None,
        )

        try:
            data = await self._make_request("GET", f"{endpoint}/search", params=params)
        except Exception as e:  # noqa: BLE001 — None-on-error contract
            # Retries/backoff/circuit breaker already handled by _make_request;
            # callers expect None on failure, never an exception.
            logger.warning(
                "brave_search_failed",
                endpoint=endpoint,
                query=query[:50],
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

        # Count results based on endpoint (response formats differ)
        if endpoint == "web":
            results_count = len(data.get("web", {}).get("results", []))
        else:
            results_count = len(data.get("results", []))

        logger.info(
            "brave_search_success",
            endpoint=endpoint,
            query=query[:50],
            results_count=results_count,
        )
        return data
