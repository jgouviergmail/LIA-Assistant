"""
Helper functions for the Interests domain.

Provides shared utilities for:
- Embedding generation for topics and content
- Connector API key retrieval for content sources
- Localized search query building
- Common operations across services and routers
"""

from uuid import UUID

from src.core.i18n import resolve_language
from src.domains.connectors.models import ConnectorType
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def get_connector_api_key(
    user_id: str,
    connector_type: ConnectorType,
) -> str | None:
    """
    Get a user's API key for a given connector type.

    Shared by content sources (Brave Search, Perplexity) that require
    per-user API key authentication via the connectors system.

    Args:
        user_id: User UUID as string
        connector_type: Connector type enum (e.g., ConnectorType.BRAVE_SEARCH)

    Returns:
        API key string if configured and active, None otherwise
    """
    try:
        from src.domains.connectors.service import ConnectorService
        from src.infrastructure.database import get_db_context

        async with get_db_context() as db:
            service = ConnectorService(db)
            credentials = await service.get_api_key_credentials(
                user_id=UUID(user_id),
                connector_type=connector_type,
            )

            if credentials and credentials.api_key:
                return credentials.api_key

            return None

    except Exception as e:
        logger.debug(
            "connector_api_key_check_failed",
            user_id=user_id,
            connector_type=connector_type.value,
            error=str(e),
        )
        return None


# Locality suffixes for locally-anchored interest content (P9, Lot 6).
# Appended to the localized search query when a city is resolved and the
# INTERESTS_LOCAL_ANCHOR_ENABLED flag is on ("jazz near Lyon this week").
LOCALITY_SUFFIX_TEMPLATES: dict[str, str] = {
    "fr": " près de {locality} cette semaine",
    "en": " near {locality} this week",
    "es": " cerca de {locality} esta semana",
    "de": " in der Nähe von {locality} diese Woche",
    "it": " vicino a {locality} questa settimana",
    "zh-CN": "，{locality}附近，本周",
}


def anchor_topic_locally(topic: str, user_language: str, locality: str | None) -> str:
    """Append the localized "near {city} this week" suffix to a topic (P9).

    Identity when ``locality`` is None — sources keep their historical
    queries. Applied ONCE at the generator level so every source strategy
    (Brave, Perplexity, LLM reflection) benefits without signature churn.
    """
    if not locality:
        return topic
    suffix = LOCALITY_SUFFIX_TEMPLATES[resolve_language(user_language)]
    return topic + suffix.format(locality=locality)


def build_localized_search_query(
    topic: str,
    user_language: str,
    templates: dict[str, str],
) -> str:
    """
    Build a search query using language-specific templates.

    Shared by content sources that need localized search queries
    (Brave Search, Perplexity).

    Args:
        topic: Interest topic to search for
        user_language: User's language code (e.g., "fr", "fr-FR", "en-US")
        templates: Dict mapping every canonical language code to a query
            template with a ``{topic}`` placeholder

    Returns:
        Localized search query string

    Example:
        With a table keyed on every canonical code, ``"fr-FR"`` reads the
        ``"fr"`` template, an absent code the declared language's, and a code
        no supported language matches the instance default's (ADR-323).
    """
    return templates[resolve_language(user_language)].format(topic=topic)


async def generate_interest_embedding(text: str) -> list[float] | None:
    """Generate embedding for interest topic or content.

    Used for semantic deduplication of interests and content notifications.
    Shared by:
    - Manual interest creation (router.py)
    - Automatic interest extraction (extraction_service.py)
    - Content notification deduplication (content_generator.py)

    All callers run on async paths, so this uses the native async embedding
    API (a blocking HTTP call here would freeze the event loop).

    Args:
        text: Topic or content text to embed.

    Returns:
        Embedding vector, or None if generation fails.

    Example:
        >>> embedding = await generate_interest_embedding("machine learning")
        >>> if embedding:
        ...     print(f"Generated {len(embedding)}-dim embedding")
    """
    try:
        from src.domains.interests.embedding import get_interest_embeddings

        embeddings = get_interest_embeddings()
        # Use aembed_documents for storage (task_type=RETRIEVAL_DOCUMENT with Gemini)
        results = await embeddings.aembed_documents([text])
        return results[0] if results else None
    except Exception as e:
        logger.warning(
            "interest_embedding_generation_failed",
            text_length=len(text) if text else 0,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None
