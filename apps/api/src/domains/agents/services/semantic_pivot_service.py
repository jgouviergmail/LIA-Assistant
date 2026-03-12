"""
Semantic Pivot Service - Centralized Query Translation.

Architecture v3 - Intelligence, Autonomie, Pertinence.

The Semantic Pivot translates user queries from any language to English
for optimal LLM and embedding processing efficiency. English is the
internal processing language; output is returned in the user's language.

Benefits:
1. Improved embedding matching (embeddings work best in English)
2. Consistent LLM performance across languages
3. Reduced hallucination from language mixing
4. Better tool selection accuracy

Usage:
    from src.domains.agents.services.semantic_pivot_service import (
        translate_to_english,
        get_semantic_pivot_service,
    )

    # Simple function call (with config for token tracking)
    english_query = await translate_to_english("mes derniers emails", base_config=config)
    # -> "Get my latest emails"

    # Or via service
    service = get_semantic_pivot_service()
    english_query = await service.translate(query, base_config=config)

Token Tracking Note:
    The `base_config` parameter is critical for proper token tracking.
    When provided, callbacks (TokenTrackingCallback, Langfuse, etc.) from
    the parent config are preserved, ensuring LLM token consumption is
    properly tracked to the database.

    Pattern follows: memory_reference_resolution_service.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.cache.llm_cache import cache_llm_response
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

logger = get_logger(__name__)


@cache_llm_response(ttl_seconds=300)
async def _cached_translate_llm_call(
    query: str,
    system_prompt: str,
    config: RunnableConfig | None = None,
) -> str:
    """
    Internal cached LLM call for semantic pivot translation.

    This function is decorated with @cache_llm_response to cache identical
    query translations in Redis (TTL: 5 minutes).

    Args:
        query: User query to translate
        system_prompt: System prompt for translation
        config: RunnableConfig with callbacks for token tracking

    Returns:
        English translation of the query
    """
    from src.infrastructure.llm import get_llm

    llm = get_llm("semantic_pivot")  # Fast LLM for query translation
    prompt = f"{system_prompt}\n\nQuery: {query}\nEnglish intent:"

    result = await llm.ainvoke(prompt, config=config)
    english_query = (
        str(result.content).strip() if hasattr(result, "content") else str(result).strip()
    )

    # Clean up any quotes or extra formatting
    return english_query.strip("\"'")


async def translate_to_english(
    query: str,
    base_config: RunnableConfig | None = None,
) -> str:
    """
    Semantic Pivot: Translate user query to English intent.

    Cached via Redis LLM cache for performance (same query returns cached translation).
    Uses a fast LLM (gpt-4.1-mini) to convert any language query into a clear
    English intent phrase.

    Cache behavior:
    - TTL: 5 minutes (300 seconds)
    - Key: SHA256(query + system_prompt)
    - Cache HIT: ~5ms (Redis lookup)
    - Cache MISS: ~500-1000ms (LLM API call)

    Args:
        query: User query in any language
        base_config: Optional parent RunnableConfig to preserve callbacks
            (TokenTrackingCallback, Langfuse, etc.). When provided, callbacks
            are preserved ensuring LLM token consumption is tracked to database.
            Pattern follows memory_reference_resolution_service.py.

    Returns:
        English intent phrase (e.g., "Get my last 2 emails")

    Example:
        >>> await translate_to_english("mes 2 derniers emails reçus", base_config=config)
        "Get my last 2 received emails"
        >>> await translate_to_english("Schick mir die letzten 2 E-Mails")
        "Get my last 2 emails"
    """
    try:
        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

        # Load prompt from versioned file
        system_prompt = load_prompt("semantic_pivot_prompt", version="v1")

        # Enrich config with node metadata while preserving parent callbacks
        # Critical: Use base_config (not {}) to preserve TokenTrackingCallback
        # This ensures token tracking works for semantic pivot LLM calls
        config = enrich_config_with_node_metadata(base_config or {}, "semantic_pivot")

        # Call cached LLM function
        english_query = await _cached_translate_llm_call(
            query=query,
            system_prompt=system_prompt,
            config=config,
        )

        logger.info(
            "semantic_pivot_translation",
            original_query=query[:80],
            english_query=english_query[:80],
        )

        return english_query

    except Exception as e:
        logger.warning(
            "semantic_pivot_translation_failed",
            error=str(e),
            fallback="using original query",
        )
        return query  # Fallback to original query


class SemanticPivotService:
    """
    Service wrapper for semantic pivot operations.

    Provides a class-based interface for semantic pivot operations
    with potential future extensions (caching stats, batch translation, etc.).
    """

    async def translate(
        self,
        query: str,
        base_config: RunnableConfig | None = None,
    ) -> str:
        """
        Translate query to English.

        Args:
            query: User query in any language
            base_config: Optional parent RunnableConfig to preserve callbacks
                (TokenTrackingCallback, etc.) for proper token tracking.

        Returns:
            English intent phrase
        """
        return await translate_to_english(query, base_config=base_config)

    async def translate_batch(
        self,
        queries: list[str],
        base_config: RunnableConfig | None = None,
    ) -> list[str]:
        """
        Translate multiple queries to English.

        Args:
            queries: List of user queries in any language
            base_config: Optional parent RunnableConfig to preserve callbacks

        Returns:
            List of English intent phrases
        """
        import asyncio

        return await asyncio.gather(
            *[translate_to_english(q, base_config=base_config) for q in queries]
        )


# Singleton
_service: SemanticPivotService | None = None


def get_semantic_pivot_service() -> SemanticPivotService:
    """Get singleton SemanticPivotService instance."""
    global _service
    if _service is None:
        _service = SemanticPivotService()
    return _service


def reset_semantic_pivot_service() -> None:
    """Reset service for testing."""
    global _service
    _service = None
