"""
Brave Search Content Source for Interest Notifications.

Generates content from Brave web search for proactive notifications.
Requires user-configured Brave Search API key (optional connector).

Features:
- Web search with freshness filtering (past week by default)
- Varied results across calls (better dedup than static encyclopedic content)
- Source citations included
- Per-user API key authentication

References:
    - Client: src/domains/connectors/clients/brave_search_client.py
    - Connector: src/domains/connectors/service.py
"""

from uuid import UUID

from src.core.constants import (
    BRAVE_SEARCH_DEFAULT_COUNT,
    BRAVE_SEARCH_DEFAULT_FRESHNESS,
    INTEREST_SOURCE_CONTENT_MAX_LENGTH,
)
from src.domains.agents.display.components.base import html_to_text
from src.domains.connectors.clients.brave_search_client import BraveSearchClient
from src.domains.connectors.models import ConnectorType
from src.domains.interests.helpers import (
    build_localized_search_query,
    get_connector_api_key,
    normalize_language_code,
)
from src.domains.interests.services.content_sources.base import ContentResult
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Search query templates per language
_SEARCH_QUERY_TEMPLATES: dict[str, str] = {
    "fr": "Actualités et informations récentes sur {topic}",
    "en": "Recent news and information about {topic}",
    "es": "Noticias recientes e información sobre {topic}",
    "de": "Aktuelle Nachrichten und Informationen über {topic}",
    "it": "Notizie recenti e informazioni su {topic}",
}


class BraveSearchContentSource:
    """
    Brave Search content source for interest notifications.

    Generates web content by:
    1. Verifying user has Brave Search API key configured
    2. Searching for recent web content about the topic
    3. Formatting results into structured content with citations

    Requires user to have configured Brave Search connector with API key.

    Example:
        >>> source = BraveSearchContentSource()
        >>> result = await source.generate(
        ...     topic="machine learning",
        ...     user_language="fr",
        ...     user_id="uuid-here",
        ... )
        >>> if result:
        ...     print(result.content)
        ...     print(result.citations)
    """

    source_name: str = "brave"

    def __init__(self) -> None:
        """Initialize Brave Search content source."""
        self._clients: dict[str, BraveSearchClient] = {}

    def _get_client(
        self,
        api_key: str,
        user_id: str,
        language: str,
    ) -> BraveSearchClient:
        """
        Get or create Brave Search client for a user.

        Args:
            api_key: Brave Search API key
            user_id: User UUID as string
            language: Language code for search_lang parameter

        Returns:
            BraveSearchClient instance
        """
        cache_key = f"{user_id}:{language}"
        if cache_key not in self._clients:
            self._clients[cache_key] = BraveSearchClient(
                api_key=api_key,
                language=language,
                user_id=UUID(user_id),
            )
        return self._clients[cache_key]

    async def generate(
        self,
        topic: str,
        user_language: str,
        existing_embeddings: list[list[float]] | None = None,
        user_id: str | None = None,
    ) -> ContentResult | None:
        """
        Generate content from Brave Search for a topic.

        Searches for recent web content about the topic and returns
        structured results with citations.

        Args:
            topic: Interest topic to search for
            user_language: User's language code
            existing_embeddings: Not used (dedup handled at generator level)
            user_id: User ID (required for Brave - needs API key)

        Returns:
            ContentResult with Brave search results, or None if not available
        """
        if not user_id:
            logger.debug(
                "brave_source_no_user_id",
                topic=topic,
            )
            return None

        try:
            api_key = await get_connector_api_key(user_id, ConnectorType.BRAVE_SEARCH)
            if not api_key:
                logger.debug(
                    "brave_source_no_api_key",
                    user_id=user_id,
                    topic=topic,
                )
                return None

            language = normalize_language_code(user_language)
            client = self._get_client(api_key, user_id, language)

            logger.debug(
                "brave_source_searching",
                topic=topic,
                language=language,
                user_id=user_id,
            )

            search_query = build_localized_search_query(
                topic, user_language, _SEARCH_QUERY_TEMPLATES
            )

            data = await client.search(
                query=search_query,
                endpoint="web",
                count=BRAVE_SEARCH_DEFAULT_COUNT,
                freshness=BRAVE_SEARCH_DEFAULT_FRESHNESS,
            )

            if not data:
                logger.debug(
                    "brave_source_no_data",
                    topic=topic,
                    user_id=user_id,
                )
                return None

            results = data.get("web", {}).get("results", [])
            if not results:
                logger.debug(
                    "brave_source_no_results",
                    topic=topic,
                    user_id=user_id,
                )
                return None

            formatted_content = self._format_results(results)
            citations = [r["url"] for r in results if r.get("url")]

            logger.info(
                "brave_source_content_generated",
                topic=topic,
                results_count=len(results),
                content_length=len(formatted_content),
                user_id=user_id,
            )

            return ContentResult(
                content=formatted_content,
                source=self.source_name,
                raw_content=formatted_content,
                citations=citations,
                metadata={
                    "query": search_query,
                    "results_count": len(results),
                    "freshness": BRAVE_SEARCH_DEFAULT_FRESHNESS,
                    "language": language,
                },
            )

        except Exception as e:
            logger.warning(
                "brave_source_generation_failed",
                topic=topic,
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def _format_results(self, results: list[dict]) -> str:
        """
        Format Brave search results into structured content.

        Produces content suitable for:
        - Embedding generation (varied across calls = good dedup behavior)
        - LLM presentation step (enough context to write a notification)

        Args:
            results: List of Brave search result dicts with title/description

        Returns:
            Formatted content string, truncated to max source content length
        """
        parts: list[str] = []

        for i, result in enumerate(results, 1):
            title = html_to_text(result.get("title", "")).strip()
            description = html_to_text(result.get("description", "")).strip()

            if not title:
                continue

            if description:
                parts.append(f"{i}. {title}\n   {description}")
            else:
                parts.append(f"{i}. {title}")

        content = "\n\n".join(parts)

        if len(content) > INTEREST_SOURCE_CONTENT_MAX_LENGTH:
            content = content[:INTEREST_SOURCE_CONTENT_MAX_LENGTH] + "..."

        return content

    def is_available(self, user_id: str | None = None) -> bool:
        """
        Check if Brave Search source is potentially available.

        Note: This only checks if user_id is provided. Actual API key
        verification is done in generate() since it requires async DB access.

        Args:
            user_id: User ID (required for Brave Search)

        Returns:
            True if user_id provided (actual availability checked in generate)
        """
        return user_id is not None

    async def close(self) -> None:
        """Cleanup all HTTP clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
