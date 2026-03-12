"""
Helper functions for the Interests domain.

Provides shared utilities for:
- Embedding generation for topics and content
- Connector API key retrieval for content sources
- Localized search query building
- Common operations across services and routers
"""

from uuid import UUID

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
        templates: Dict mapping base language codes to query templates
            with a ``{topic}`` placeholder

    Returns:
        Localized search query string (falls back to "en" template)

    Example:
        >>> templates = {"fr": "Actualités sur {topic}", "en": "News about {topic}"}
        >>> build_localized_search_query("IA", "fr-FR", templates)
        'Actualités sur IA'
    """
    base_lang = user_language.split("-")[0].lower()
    template = templates.get(base_lang, templates.get("en", "Recent news about {topic}"))
    return template.format(topic=topic)


def normalize_language_code(language: str) -> str:
    """
    Extract base language code from a locale string (ISO 639-1).

    Handles various formats: "fr", "fr-FR", "en_US", "zh-CN".

    Args:
        language: Language/locale string

    Returns:
        Base language code (e.g., "fr", "en", "zh")
    """
    return language.lower().replace("_", "-").split("-")[0]


def generate_interest_embedding(text: str) -> list[float] | None:
    """
    Generate E5-small embedding (384 dims) for interest topic or content.

    Used for semantic deduplication of interests and content notifications.
    Shared by:
    - Manual interest creation (router.py)
    - Automatic interest extraction (extraction_service.py)
    - Content notification deduplication (content_generator.py)

    Args:
        text: Topic or content text to embed

    Returns:
        384-dimensional embedding vector, or None if generation fails

    Example:
        >>> embedding = generate_interest_embedding("machine learning")
        >>> if embedding:
        ...     print(f"Generated {len(embedding)}-dim embedding")
    """
    try:
        from src.infrastructure.llm.local_embeddings import get_local_embeddings

        embeddings = get_local_embeddings()
        return embeddings.embed_query(text)
    except Exception as e:
        logger.warning(
            "interest_embedding_generation_failed",
            text_preview=text[:50] if text else "empty",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None
