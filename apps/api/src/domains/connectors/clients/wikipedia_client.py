"""
Wikipedia API client.

Provides access to Wikipedia for searching articles and retrieving content.
Uses the MediaWiki API which requires no authentication.

API Reference:
- https://www.mediawiki.org/wiki/API:Main_page
- https://en.wikipedia.org/w/api.php (endpoint documentation)

Features:
- Search articles by keyword
- Get article summaries (extracts)
- Get full article content
- Support for multiple languages

No authentication required - just follow rate limit guidelines:
- https://www.mediawiki.org/wiki/API:Etiquette
"""

import asyncio
from typing import Any
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import HTTP_TIMEOUT_WIKIPEDIA
from src.core.exceptions import MaxRetriesExceededError

logger = structlog.get_logger(__name__)


class WikipediaClient:
    """
    Client for Wikipedia API.

    Provides access to:
    - Article search
    - Article summaries (extracts)
    - Full article content
    - Multi-language support

    Example:
        >>> client = WikipediaClient(language="en")
        >>> results = await client.search("Albert Einstein")
        >>> article = await client.get_article(results[0]["pageid"])
        >>> print(article["extract"][:500])
    """

    def __init__(
        self,
        language: str = "en",
        user_id: UUID | None = None,
        rate_limit_per_second: float | None = None,
    ) -> None:
        """
        Initialize Wikipedia client.

        Args:
            language: Wikipedia language code (e.g., "en", "fr", "de", "es")
            user_id: Optional user ID for logging
            rate_limit_per_second: Max requests per second (None = use settings)
        """
        self.language = language
        self.user_id = user_id
        # Use settings if not explicitly provided
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_wikipedia_per_second
        )
        self._rate_limit_interval = 1.0 / effective_rate_limit
        self._last_request_time = 0.0
        self._http_client: httpx.AsyncClient | None = None

    @property
    def api_base_url(self) -> str:
        """Get API base URL for the configured language."""
        return f"https://{self.language}.wikipedia.org/w/api.php"

    @property
    def rest_api_url(self) -> str:
        """Get REST API URL for the configured language (for summaries)."""
        return f"https://{self.language}.wikipedia.org/api/rest_v1"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_WIKIPEDIA,
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                ),
                headers={
                    # Wikipedia requires a user agent
                    "User-Agent": "LIA/1.0 (https://lia.app; contact@lia.app)",
                },
            )
        return self._http_client

    async def close(self) -> None:
        """Cleanup HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _rate_limit(self) -> None:
        """Apply rate limiting (Wikipedia recommends conservative limits)."""
        import time

        now = time.monotonic()
        elapsed = now - self._last_request_time

        if elapsed < self._rate_limit_interval:
            wait_time = self._rate_limit_interval - elapsed
            await asyncio.sleep(wait_time)

        self._last_request_time = time.monotonic()

    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================

    async def search(
        self,
        query: str,
        limit: int = 10,
        include_snippets: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search Wikipedia for articles matching a query.

        Args:
            query: Search query
            limit: Maximum number of results (default: 10, max: 50)
            include_snippets: Include text snippets in results

        Returns:
            List of search results with title, pageid, snippet

        Example:
            >>> results = await client.search("quantum physics")
            >>> for r in results:
            ...     print(f"{r['title']}: {r.get('snippet', '')[:100]}...")
        """
        limit = min(limit, 20)

        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
            "utf8": 1,
        }

        if include_snippets:
            params["srprop"] = "snippet|titlesnippet|sectiontitle"

        response = await self._make_request(params)

        results = response.get("query", {}).get("search", [])

        logger.info(
            "wikipedia_search_completed",
            user_id=str(self.user_id) if self.user_id else None,
            query=query,
            language=self.language,
            results_count=len(results),
        )

        return results

    async def search_suggestions(
        self,
        query: str,
        limit: int = 10,
    ) -> list[str]:
        """
        Get search suggestions (autocomplete).

        Args:
            query: Partial search query
            limit: Maximum number of suggestions

        Returns:
            List of suggested article titles
        """
        params = {
            "action": "opensearch",
            "search": query,
            "limit": min(limit, 10),
            "namespace": 0,  # Main article namespace only
            "format": "json",
        }

        response = await self._make_opensearch_request(params)

        # OpenSearch returns [query, [titles], [descriptions], [urls]]
        if len(response) >= 2:
            titles = response[1]
            if isinstance(titles, list):
                return [str(t) for t in titles]

        return []

    # =========================================================================
    # ARTICLE RETRIEVAL
    # =========================================================================

    async def get_article_summary(
        self,
        title: str,
    ) -> dict[str, Any]:
        """
        Get a brief summary of an article using the REST API.

        This is the fastest way to get article summaries with:
        - Title and description
        - Short extract (1-2 paragraphs)
        - Thumbnail image URL
        - Article URL

        Args:
            title: Article title (exact match or close match)

        Returns:
            Article summary with title, extract, thumbnail, etc.

        Example:
            >>> summary = await client.get_article_summary("Albert Einstein")
            >>> print(f"{summary['title']}: {summary['extract'][:200]}...")
        """
        # URL-encode the title
        import urllib.parse

        encoded_title = urllib.parse.quote(title.replace(" ", "_"))

        url = f"{self.rest_api_url}/page/summary/{encoded_title}"

        await self._rate_limit()

        client = await self._get_client()

        try:
            response = await client.get(url)
            response.raise_for_status()

            data = response.json()

            logger.info(
                "wikipedia_summary_retrieved",
                user_id=str(self.user_id) if self.user_id else None,
                title=title,
                language=self.language,
            )

            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(
                    "wikipedia_article_not_found",
                    user_id=str(self.user_id) if self.user_id else None,
                    title=title,
                )
                return {"error": "Article not found", "title": title}
            raise

    async def get_article(
        self,
        title: str | None = None,
        pageid: int | None = None,
        sections: bool = True,
        extract_chars: int | None = None,
    ) -> dict[str, Any]:
        """
        Get full article content.

        Args:
            title: Article title (use either title or pageid)
            pageid: Article page ID
            sections: Include section structure
            extract_chars: Limit extract to N characters (None for full)

        Returns:
            Article data with title, pageid, extract (content), sections

        Example:
            >>> article = await client.get_article(title="Python (programming language)")
            >>> print(article["extract"][:1000])
        """
        if not title and not pageid:
            raise ValueError("Either title or pageid must be provided")

        params: dict[str, Any] = {
            "action": "query",
            "prop": "extracts|pageprops|info",
            "format": "json",
            "utf8": 1,
            "explaintext": 1,  # Get plain text instead of HTML
            "inprop": "url",
        }

        if title:
            params["titles"] = title
        else:
            params["pageids"] = pageid

        if extract_chars:
            params["exchars"] = extract_chars

        if sections:
            params["prop"] += "|sections"

        response = await self._make_request(params)

        pages = response.get("query", {}).get("pages", {})

        if not pages:
            return {"error": "Article not found"}

        # Get the first (and should be only) page
        page = list(pages.values())[0]

        # Check if page exists
        if "missing" in page:
            logger.warning(
                "wikipedia_article_missing",
                user_id=str(self.user_id) if self.user_id else None,
                title=title,
                pageid=pageid,
            )
            return {"error": "Article not found", "title": title}

        logger.info(
            "wikipedia_article_retrieved",
            user_id=str(self.user_id) if self.user_id else None,
            title=page.get("title"),
            pageid=page.get("pageid"),
            extract_length=len(page.get("extract", "")),
        )

        return page

    async def get_article_sections(
        self,
        title: str,
    ) -> list[dict[str, Any]]:
        """
        Get article section structure (table of contents).

        Args:
            title: Article title

        Returns:
            List of sections with index, title, level
        """
        params = {
            "action": "parse",
            "page": title,
            "prop": "sections",
            "format": "json",
        }

        response = await self._make_request(params)

        sections = response.get("parse", {}).get("sections", [])

        return sections

    async def get_section_content(
        self,
        title: str,
        section_index: int,
    ) -> str:
        """
        Get content of a specific section.

        Args:
            title: Article title
            section_index: Section index (from get_article_sections)

        Returns:
            Plain text content of the section
        """
        params = {
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "exsectionformat": "plain",
            "explaintext": 1,
            "exsection": section_index,
            "format": "json",
        }

        response = await self._make_request(params)

        pages = response.get("query", {}).get("pages", {})
        if not pages:
            return ""

        page = list(pages.values())[0]
        return page.get("extract", "")

    # =========================================================================
    # RELATED CONTENT
    # =========================================================================

    async def get_related_articles(
        self,
        title: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get articles related to a given article.

        Args:
            title: Article title
            limit: Maximum number of related articles

        Returns:
            List of related articles with title and pageid
        """
        params = {
            "action": "query",
            "titles": title,
            "prop": "links",
            "pllimit": min(limit, 50),
            "plnamespace": 0,  # Main article namespace only
            "format": "json",
        }

        response = await self._make_request(params)

        pages = response.get("query", {}).get("pages", {})
        if not pages:
            return []

        page = list(pages.values())[0]
        links = page.get("links", [])

        return links

    async def get_categories(
        self,
        title: str,
        limit: int = 20,
    ) -> list[str]:
        """
        Get categories for an article.

        Args:
            title: Article title
            limit: Maximum number of categories

        Returns:
            List of category names
        """
        params = {
            "action": "query",
            "titles": title,
            "prop": "categories",
            "cllimit": min(limit, 50),
            "format": "json",
        }

        response = await self._make_request(params)

        pages = response.get("query", {}).get("pages", {})
        if not pages:
            return []

        page = list(pages.values())[0]
        categories = page.get("categories", [])

        # Extract category names (remove "Category:" prefix)
        return [cat["title"].replace("Category:", "") for cat in categories]

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _make_request(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Make request to Wikipedia API (standard dict response).

        Args:
            params: Query parameters

        Returns:
            JSON response as dict
        """
        await self._rate_limit()

        client = await self._get_client()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.get(self.api_base_url, params=params)

                if response.status_code == 429:
                    wait_time = 5 * (attempt + 1)
                    logger.warning(
                        "wikipedia_rate_limited",
                        user_id=str(self.user_id) if self.user_id else None,
                        attempt=attempt + 1,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        "wikipedia_request_failed",
                        user_id=str(self.user_id) if self.user_id else None,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise

                wait_time = 2**attempt
                logger.warning(
                    "wikipedia_request_retry",
                    user_id=str(self.user_id) if self.user_id else None,
                    attempt=attempt + 1,
                    wait_seconds=wait_time,
                )
                await asyncio.sleep(wait_time)

        # Should never reach here, but satisfy type checker
        raise MaxRetriesExceededError(
            operation="wikipedia_request",
            max_retries=3,
        )

    async def _make_opensearch_request(
        self,
        params: dict[str, Any],
    ) -> list[Any]:
        """
        Make opensearch request to Wikipedia API (returns array).

        OpenSearch API returns [query, [titles], [descriptions], [urls]]

        Args:
            params: Query parameters

        Returns:
            JSON response as list
        """
        await self._rate_limit()

        client = await self._get_client()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.get(self.api_base_url, params=params)

                if response.status_code == 429:
                    wait_time = 5 * (attempt + 1)
                    logger.warning(
                        "wikipedia_rate_limited",
                        user_id=str(self.user_id) if self.user_id else None,
                        attempt=attempt + 1,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                result: list[Any] = response.json()
                return result

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        "wikipedia_opensearch_failed",
                        user_id=str(self.user_id) if self.user_id else None,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise

                wait_time = 2**attempt
                logger.warning(
                    "wikipedia_request_retry",
                    user_id=str(self.user_id) if self.user_id else None,
                    attempt=attempt + 1,
                    wait_seconds=wait_time,
                )
                await asyncio.sleep(wait_time)

        # Should never reach here, but satisfy type checker
        raise MaxRetriesExceededError(
            operation="wikipedia_opensearch_request",
            max_retries=3,
        )

    def set_language(self, language: str) -> None:
        """
        Change the Wikipedia language.

        Args:
            language: Wikipedia language code (e.g., "en", "fr", "de")
        """
        self.language = language

    @staticmethod
    def get_supported_languages() -> list[str]:
        """
        Get list of commonly supported Wikipedia languages.

        Returns:
            List of language codes
        """
        return [
            "en",  # English
            "fr",  # French
            "de",  # German
            "es",  # Spanish
            "it",  # Italian
            "pt",  # Portuguese
            "ru",  # Russian
            "ja",  # Japanese
            "zh",  # Chinese
            "ar",  # Arabic
            "nl",  # Dutch
            "pl",  # Polish
            "sv",  # Swedish
            "ko",  # Korean
        ]
