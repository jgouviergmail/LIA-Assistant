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
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal
from uuid import UUID

import httpx

from src.core.config import settings
from src.core.constants import HTTP_TIMEOUT_BRAVE_SEARCH
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class BraveSearchClient:
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

    api_base_url = "https://api.search.brave.com/res/v1"

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
            user_id: Optional user ID for logging
            rate_limit_per_second: Max requests per second (None = use settings)
        """
        self.api_key = api_key
        self.language = language
        self.user_id = user_id
        # Use settings if not explicitly provided
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_brave_search_per_second
        )
        self._rate_limit_interval = 1.0 / effective_rate_limit
        self._last_request_time = 0.0
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(HTTP_TIMEOUT_BRAVE_SEARCH),
                headers={"X-Subscription-Token": self.api_key},
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client connection."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _rate_limit(self) -> None:
        """Local rate limiting (time-based throttle)."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self._rate_limit_interval:
            await asyncio.sleep(self._rate_limit_interval - time_since_last)
        self._last_request_time = time.time()

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
            API response dict or None if error

        Example:
            >>> result = await client.search("AI news", endpoint="news", freshness="pw")
            >>> print(result["results"][0]["title"])
        """
        await self._rate_limit()

        # Validate endpoint
        if endpoint not in ("web", "news"):
            logger.error("brave_search_invalid_endpoint", endpoint=endpoint)
            return None

        # Build URL
        url = f"{self.api_base_url}/{endpoint}/search"

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

        # Make request with retry
        client = await self._get_client()
        attempt = 0
        max_retries = 3

        while attempt < max_retries:
            try:
                logger.info(
                    "brave_search_request",
                    endpoint=endpoint,
                    query=query[:50],
                    attempt=attempt + 1,
                    user_id=str(self.user_id) if self.user_id else None,
                )

                response = await client.get(url, params=params)

                if response.status_code == 200:
                    data = response.json()
                    # Count results based on endpoint
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

                elif response.status_code == 429:
                    # Rate limit - exponential backoff
                    wait_time = 2**attempt
                    logger.warning(
                        "brave_search_rate_limit",
                        endpoint=endpoint,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    attempt += 1
                    continue

                else:
                    logger.error(
                        "brave_search_error",
                        endpoint=endpoint,
                        status_code=response.status_code,
                        text=response.text[:200],
                    )
                    return None

            except httpx.TimeoutException:
                logger.warning(
                    "brave_search_timeout",
                    endpoint=endpoint,
                    query=query[:50],
                    attempt=attempt + 1,
                )
                attempt += 1
                if attempt >= max_retries:
                    return None
                # Retry with exponential backoff
                wait_time = 2**attempt
                await asyncio.sleep(wait_time)

            except Exception as e:
                logger.error(
                    "brave_search_exception",
                    endpoint=endpoint,
                    query=query[:50],
                    error=str(e),
                )
                return None

        # Max retries exceeded
        return None
