"""
Wikipedia Content Source for Interest Notifications.

Generates content from Wikipedia articles for proactive notifications.
Uses the existing WikipediaClient for API access.

Features:
- Multi-language support (maps user language to Wikipedia domain)
- Article search and summary extraction
- No authentication required (always available)

References:
    - Client: src/domains/connectors/clients/wikipedia_client.py
"""

from src.core.config import settings
from src.domains.connectors.clients.wikipedia_client import WikipediaClient
from src.domains.interests.services.content_sources.base import ContentResult
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Language mapping from user language code to Wikipedia language code
LANGUAGE_MAP = {
    "fr": "fr",
    "en": "en",
    "es": "es",
    "de": "de",
    "it": "it",
    "zh": "zh",
    "zh-CN": "zh",
    "pt": "pt",
    "ru": "ru",
    "ja": "ja",
    "ko": "ko",
    "ar": "ar",
    "nl": "nl",
    "pl": "pl",
    "sv": "sv",
}


class WikipediaContentSource:
    """
    Wikipedia content source for interest notifications.

    Generates encyclopedic content by:
    1. Searching Wikipedia for the interest topic
    2. Retrieving article summary (extract)
    3. Returning formatted content with article URL

    Always available (no authentication required).

    Example:
        >>> source = WikipediaContentSource()
        >>> result = await source.generate("machine learning", "fr")
        >>> if result:
        ...     print(result.content)
        ...     print(result.citations)
    """

    source_name: str = "wikipedia"

    def __init__(self) -> None:
        """Initialize Wikipedia content source."""
        self._clients: dict[str, WikipediaClient] = {}

    def _get_client(self, language: str) -> WikipediaClient:
        """
        Get or create Wikipedia client for a language.

        Args:
            language: Wikipedia language code

        Returns:
            WikipediaClient instance
        """
        if language not in self._clients:
            self._clients[language] = WikipediaClient(language=language)
        return self._clients[language]

    def _map_language(self, user_language: str) -> str:
        """
        Map user language to Wikipedia language code.

        Args:
            user_language: User's language code (e.g., "fr", "en", "zh-CN")

        Returns:
            Wikipedia language code
        """
        # Normalize language code (handle "fr-FR" -> "fr")
        base_lang = user_language.split("-")[0].lower()

        # Check full code first (for "zh-CN"), then base
        return LANGUAGE_MAP.get(user_language, LANGUAGE_MAP.get(base_lang, "en"))

    async def generate(
        self,
        topic: str,
        user_language: str,
        existing_embeddings: list[list[float]] | None = None,
    ) -> ContentResult | None:
        """
        Generate content from Wikipedia for a topic.

        Args:
            topic: Interest topic to search for
            user_language: User's language code
            existing_embeddings: Not used (dedup handled at generator level)

        Returns:
            ContentResult with Wikipedia excerpt, or None if not found
        """
        try:
            wiki_lang = self._map_language(user_language)
            client = self._get_client(wiki_lang)

            logger.debug(
                "wikipedia_source_searching",
                topic=topic,
                language=wiki_lang,
            )

            # Search for articles matching the topic
            search_results = await client.search(
                query=topic,
                limit=settings.interest_wikipedia_search_limit,
                include_snippets=True,
            )

            if not search_results:
                logger.debug(
                    "wikipedia_source_no_results",
                    topic=topic,
                    language=wiki_lang,
                )
                return None

            # Get the best matching article (first result)
            best_match = search_results[0]
            article_title = best_match.get("title", "")

            if not article_title:
                return None

            # Get article summary
            summary = await client.get_article_summary(article_title)

            if "error" in summary:
                logger.debug(
                    "wikipedia_source_article_error",
                    topic=topic,
                    title=article_title,
                    error=summary.get("error"),
                )
                return None

            extract = summary.get("extract", "")
            if not extract:
                return None

            # Build article URL
            article_url = summary.get("content_urls", {}).get("desktop", {}).get("page", "")

            if not article_url:
                # Fallback URL construction
                encoded_title = article_title.replace(" ", "_")
                article_url = f"https://{wiki_lang}.wikipedia.org/wiki/{encoded_title}"

            # Truncate extract if too long (keep first ~1000 chars for LLM processing)
            if len(extract) > 1000:
                extract = extract[:1000] + "..."

            logger.info(
                "wikipedia_source_content_generated",
                topic=topic,
                title=article_title,
                extract_length=len(extract),
                language=wiki_lang,
            )

            return ContentResult(
                content=extract,
                source=self.source_name,
                raw_content=extract,
                citations=[article_url] if article_url else [],
                metadata={
                    "title": article_title,
                    "language": wiki_lang,
                    "pageid": best_match.get("pageid"),
                    "description": summary.get("description", ""),
                },
            )

        except Exception as e:
            logger.warning(
                "wikipedia_source_generation_failed",
                topic=topic,
                language=user_language,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def is_available(self, user_id: str | None = None) -> bool:
        """
        Check if Wikipedia source is available.

        Wikipedia API is always available (no auth required).

        Args:
            user_id: Not used (Wikipedia doesn't need per-user auth)

        Returns:
            Always True
        """
        return True

    async def close(self) -> None:
        """Cleanup all HTTP clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
