"""
Perplexity Content Source for Interest Notifications.

Generates content from Perplexity web search for proactive notifications.
Requires user-configured Perplexity API key (optional connector).

Features:
- Real-time web search with AI synthesis
- Recent news filtering (last week by default)
- Source citations included
- Per-user API key authentication

References:
    - Client: src/domains/connectors/clients/perplexity_client.py
    - Connector: src/domains/connectors/service.py
"""

from uuid import UUID

from src.core.config import settings
from src.core.constants import INTEREST_SOURCE_CONTENT_MAX_LENGTH
from src.core.i18n_types import get_language_name
from src.domains.connectors.clients.perplexity_client import PerplexityClient
from src.domains.connectors.models import ConnectorType
from src.domains.interests.helpers import (
    build_localized_search_query,
    get_connector_api_key,
)
from src.domains.interests.services.content_sources.base import ContentResult
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Search query templates per language (Perplexity-specific: focus on interesting facts)
_SEARCH_QUERY_TEMPLATES: dict[str, str] = {
    "fr": "Actualités récentes et faits intéressants sur {topic}",
    "en": "Recent news and interesting facts about {topic}",
    "es": "Noticias recientes y datos interesantes sobre {topic}",
    "de": "Aktuelle Nachrichten und interessante Fakten über {topic}",
    "it": "Notizie recenti e fatti interessanti su {topic}",
}


class PerplexityContentSource:
    """
    Perplexity content source for interest notifications.

    Generates news and web content by:
    1. Verifying user has Perplexity API key configured
    2. Searching for recent news/articles about the topic
    3. Returning synthesized content with citations

    Requires user to have configured Perplexity connector with API key.

    Example:
        >>> source = PerplexityContentSource()
        >>> result = await source.generate(
        ...     topic="machine learning",
        ...     user_language="fr",
        ...     user_id="uuid-here",
        ... )
        >>> if result:
        ...     print(result.content)
        ...     print(result.citations)
    """

    source_name: str = "perplexity"

    def __init__(self) -> None:
        """Initialize Perplexity content source."""
        self._clients: dict[str, PerplexityClient] = {}

    def _get_client(
        self,
        api_key: str,
        user_id: str,
        user_language: str,
    ) -> PerplexityClient:
        """
        Get or create Perplexity client for a user.

        Args:
            api_key: Perplexity API key
            user_id: User UUID as string
            user_language: User's language code

        Returns:
            PerplexityClient instance
        """
        cache_key = f"{user_id}:{user_language}"
        if cache_key not in self._clients:
            self._clients[cache_key] = PerplexityClient(
                api_key=api_key,
                user_id=UUID(user_id),
                model="sonar",
                user_language=user_language,
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
        Generate content from Perplexity for a topic.

        Searches for recent web content about the topic and synthesizes
        an informative response with citations.

        Args:
            topic: Interest topic to search for
            user_language: User's language code
            existing_embeddings: Not used (dedup handled at generator level)
            user_id: User ID (required for Perplexity - needs API key)

        Returns:
            ContentResult with Perplexity synthesis, or None if not available
        """
        if not user_id:
            logger.debug(
                "perplexity_source_no_user_id",
                topic=topic,
            )
            return None

        try:
            api_key = await get_connector_api_key(user_id, ConnectorType.PERPLEXITY)
            if not api_key:
                logger.debug(
                    "perplexity_source_no_api_key",
                    user_id=user_id,
                    topic=topic,
                )
                return None

            client = self._get_client(api_key, user_id, user_language)

            logger.debug(
                "perplexity_source_searching",
                topic=topic,
                language=user_language,
                user_id=user_id,
            )

            system_prompt = self._build_system_prompt(user_language)

            search_query = self._build_search_query(topic, user_language)

            result = await client.search(
                query=search_query,
                search_recency_filter=settings.interest_perplexity_recency_filter,
                return_citations=True,
                return_related_questions=settings.interest_perplexity_return_related_questions,
                system_prompt=system_prompt,
            )

            answer = result.get("answer", "")
            if not answer:
                logger.debug(
                    "perplexity_source_no_answer",
                    topic=topic,
                    user_id=user_id,
                )
                return None

            citations = result.get("citations", [])

            if len(answer) > INTEREST_SOURCE_CONTENT_MAX_LENGTH:
                answer = answer[:INTEREST_SOURCE_CONTENT_MAX_LENGTH] + "..."

            logger.info(
                "perplexity_source_content_generated",
                topic=topic,
                answer_length=len(answer),
                citations_count=len(citations),
                user_id=user_id,
            )

            return ContentResult(
                content=answer,
                source=self.source_name,
                raw_content=answer,
                citations=citations,
                metadata={
                    "query": search_query,
                    "model": result.get("model", "sonar"),
                    "language": user_language,
                    "recency_filter": settings.interest_perplexity_recency_filter,
                },
            )

        except ValueError as e:
            if "Invalid Perplexity API key" in str(e):
                logger.warning(
                    "perplexity_source_invalid_api_key",
                    user_id=user_id,
                    topic=topic,
                )
            return None

        except Exception as e:
            logger.warning(
                "perplexity_source_generation_failed",
                topic=topic,
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def _build_system_prompt(self, user_language: str) -> str:
        """
        Build system prompt for Perplexity search.

        Args:
            user_language: User's language code

        Returns:
            System prompt string
        """
        lang_name = get_language_name(user_language)

        return (
            f"You are a helpful assistant providing interesting facts and recent news. "
            f"Respond in {lang_name}. Be concise and informative. "
            f"Focus on the most interesting or surprising aspects of the topic. "
            f"Include 1-2 specific facts or recent developments."
        )

    def _build_search_query(self, topic: str, user_language: str) -> str:
        """
        Build search query for Perplexity.

        Args:
            topic: Interest topic
            user_language: User's language code

        Returns:
            Search query string
        """
        return build_localized_search_query(topic, user_language, _SEARCH_QUERY_TEMPLATES)

    def is_available(self, user_id: str | None = None) -> bool:
        """
        Check if Perplexity source is potentially available.

        Note: This only checks if user_id is provided. Actual API key
        verification is done in generate() since it requires async DB access.

        Args:
            user_id: User ID (required for Perplexity)

        Returns:
            True if user_id provided (actual availability checked in generate)
        """
        return user_id is not None

    async def close(self) -> None:
        """Cleanup all HTTP clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
