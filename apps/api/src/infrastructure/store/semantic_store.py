"""
Semantic Store Abstraction Layer.

Provides a unified interface for semantic storage operations across:
- Long-term user memories (psychological profiles)
- Future RAG document storage (Drive, local files)
- Tool context persistence

Uses LangGraph's AsyncPostgresStore with pgvector for semantic search.

Architecture:
    - StoreNamespace: Generic namespace configuration
    - MemoryNamespace: Convenience factory for memory namespaces
    - search_semantic: Unified semantic search across any namespace
    - compute_emotional_state: Aggregate emotional weight from memories

Example:
    >>> namespace = MemoryNamespace(user_id="123")
    >>> results = await search_semantic(store, namespace, "préférences")
    >>> state = compute_emotional_state(results)
    >>> # state = EmotionalState.DANGER if negative memories found
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from langgraph.store.base import BaseStore, Item, SearchItem

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class EmotionalState(str, Enum):
    """
    Aggregate emotional state computed from memory search results.

    Used for visual feedback in the UI and context-aware responses.
    """

    COMFORT = "comfort"  # Positive memories dominant (green indicator)
    DANGER = "danger"  # Negative/sensitive memories present (red indicator)
    NEUTRAL = "neutral"  # Factual mode, no strong emotions (gray indicator)


@dataclass
class StoreNamespace:
    """
    Generic namespace configuration for the semantic store.

    Supports hierarchical organization of stored items:
    - (user_id, "memories")           -> User psychological profile
    - (user_id, "documents", source)  -> RAG documents by source
    - (user_id, "context", domain)    -> Tool context by domain

    Attributes:
        user_id: Owner of the stored data
        collection: Primary collection type (memories, documents, context)
        subcategory: Optional sub-classification within collection
    """

    user_id: str
    collection: Literal["memories", "documents", "context"]
    subcategory: str | None = None

    def to_tuple(self) -> tuple[str, ...]:
        """Convert to LangGraph namespace tuple."""
        if self.subcategory:
            return (self.user_id, self.collection, self.subcategory)
        return (self.user_id, self.collection)

    @classmethod
    def for_memories(cls, user_id: str) -> "StoreNamespace":
        """Factory for memory namespace."""
        return cls(user_id=user_id, collection="memories")

    @classmethod
    def for_documents(cls, user_id: str, source: str) -> "StoreNamespace":
        """Factory for document namespace (future RAG)."""
        return cls(user_id=user_id, collection="documents", subcategory=source)

    @classmethod
    def for_context(cls, user_id: str, domain: str) -> "StoreNamespace":
        """Factory for tool context namespace."""
        return cls(user_id=user_id, collection="context", subcategory=domain)


def MemoryNamespace(user_id: str) -> StoreNamespace:
    """
    Convenience factory for memory namespace.

    Shorthand for StoreNamespace.for_memories(user_id).

    Example:
        >>> namespace = MemoryNamespace("user-123")
        >>> # Equivalent to: StoreNamespace(user_id="user-123", collection="memories")
    """
    return StoreNamespace.for_memories(user_id)


async def search_semantic(
    store: BaseStore,
    namespace: StoreNamespace,
    query: str,
    limit: int = 10,
    min_score: float = 0.6,
) -> list[SearchItem]:
    """
    Perform semantic search across a namespace.

    Uses pgvector cosine similarity for ranking results.

    Args:
        store: LangGraph BaseStore with semantic index configured
        namespace: Target namespace for search
        query: Natural language query for semantic matching
        limit: Maximum number of results to return
        min_score: Minimum similarity score threshold (0.0-1.0)

    Returns:
        List of Items sorted by relevance, filtered by min_score

    Example:
        >>> namespace = MemoryNamespace("user-123")
        >>> results = await search_semantic(store, namespace, "préférences réunions")
        >>> for item in results:
        ...     print(f"{item.value['content']} (score: {item.score:.2f})")
    """
    try:
        results = await store.asearch(
            namespace.to_tuple(),
            query=query,
            limit=limit,
        )

        # Filter by minimum score
        filtered = [
            r
            for r in results
            if hasattr(r, "score") and r.score is not None and r.score >= min_score
        ]

        # Log search completion WITHOUT query content (PII protection)
        # Use DEBUG level to avoid log clutter in production
        logger.debug(
            "semantic_search_completed",
            namespace=namespace.to_tuple(),
            query_length=len(query) if query else 0,  # Length only, not content (PII)
            total_results=len(results),
            filtered_results=len(filtered),
            min_score=min_score,
        )

        return list(filtered)

    except Exception as e:
        logger.error(
            "semantic_search_failed",
            namespace=namespace.to_tuple(),
            error=str(e),
        )
        return []


def compute_emotional_state(memories: list[Item]) -> EmotionalState:
    """
    Compute aggregate emotional state from memory search results.

    Algorithm:
    1. If ANY memory has emotional_weight <= -5 -> DANGER (sensitive zone)
    2. If MAJORITY of memories have emotional_weight >= 3 -> COMFORT (positive zone)
    3. Otherwise -> NEUTRAL (factual mode)

    This is used for:
    - Visual feedback in the UI (colored indicator)
    - Context-aware response generation (adjust tone)

    Args:
        memories: List of memory Items from semantic search

    Returns:
        EmotionalState enum value
    """
    if not memories:
        return EmotionalState.NEUTRAL

    emotional_weights = []

    for memory in memories:
        if isinstance(memory.value, dict):
            weight = memory.value.get("emotional_weight", 0)
            if isinstance(weight, int | float):
                emotional_weights.append(weight)

    if not emotional_weights:
        return EmotionalState.NEUTRAL

    # Check for danger zones (any strongly negative memory)
    if any(w <= -5 for w in emotional_weights):
        return EmotionalState.DANGER

    # Check for comfort zone (majority positive)
    positive_count = sum(1 for w in emotional_weights if w >= 3)
    if positive_count > len(emotional_weights) / 2:
        return EmotionalState.COMFORT

    return EmotionalState.NEUTRAL


async def get_all_memories(
    store: BaseStore,
    user_id: str,
    limit: int = 100,
) -> list[Item]:
    """
    Retrieve all memories for a user (non-semantic, for listing).

    Used by the memories API for listing and management.

    Args:
        store: LangGraph BaseStore
        user_id: Target user ID
        limit: Maximum number of memories to return

    Returns:
        List of all memory Items
    """
    try:
        namespace = MemoryNamespace(user_id)
        # Use empty query to get all items
        results = await store.asearch(
            namespace.to_tuple(),
            query="",
            limit=limit,
        )
        return list(results)
    except Exception as e:
        logger.error(
            "get_all_memories_failed",
            user_id=user_id,
            error=str(e),
        )
        return []


async def search_hybrid(
    store: BaseStore,
    namespace: StoreNamespace,
    query: str,
    limit: int = 10,
    min_score: float | None = None,
    alpha: float | None = None,
) -> list[SearchItem]:
    """
    Hybrid search combining semantic (pgvector) and BM25 scoring.

    Uses settings defaults if min_score/alpha not provided.
    Automatically uses singleton BM25IndexManager.

    Formula: final_score = alpha * semantic + (1-alpha) * bm25
    Boost: If both scores > threshold, apply 10% boost.

    Args:
        store: LangGraph store with pgvector
        namespace: Target namespace for search
        query: Natural language query
        limit: Maximum results to return
        min_score: Minimum combined score (default from settings)
        alpha: Semantic weight, 1-alpha for BM25 (default from settings)

    Returns:
        List of Items sorted by hybrid score

    Fallback:
        On error or empty BM25 results, falls back to semantic-only search.
    """
    from src.core.config import get_settings
    from src.infrastructure.observability.metrics import (
        hybrid_search_duration_seconds,
        hybrid_search_total,
    )
    from src.infrastructure.store.bm25_index import (
        get_bm25_manager,
        tokenize_text,
    )

    settings = get_settings()
    min_score = min_score if min_score is not None else settings.memory_hybrid_min_score
    alpha = alpha if alpha is not None else settings.memory_hybrid_alpha
    boost_threshold = settings.memory_hybrid_boost_threshold

    # Check if hybrid search is enabled
    if not settings.memory_hybrid_enabled:
        logger.debug("hybrid_search_disabled_fallback_semantic")
        return await search_semantic(store, namespace, query, limit=limit, min_score=min_score)

    bm25_manager = get_bm25_manager()

    # Initialize before try block to avoid NameError in except handler
    semantic_results: list[SearchItem] = []

    with hybrid_search_duration_seconds.time():
        try:
            # 1. Semantic search (fast, indexed via pgvector)
            semantic_results = await search_semantic(
                store, namespace, query, limit=limit * 3, min_score=0.3
            )

            if not semantic_results:
                hybrid_search_total.labels(status="fallback").inc()
                logger.debug(
                    "hybrid_search_no_semantic_results",
                    namespace=namespace.to_tuple(),
                )
                return []

            # 2. Get all items for BM25 corpus
            all_items = await store.asearch(namespace.to_tuple(), query="", limit=500)

            if not all_items:
                hybrid_search_total.labels(status="fallback").inc()
                return list(semantic_results[:limit])

            # 3. Build/get BM25 index
            documents = [item.value.get("content", "") for item in all_items]
            document_ids = [item.key for item in all_items]

            bm25, _ = bm25_manager.get_or_build_index(namespace.user_id, documents, document_ids)

            # 4. Score query with BM25 (use same tokenizer!)
            query_tokens = tokenize_text(query)

            # Guard: empty query tokens → fallback to semantic only
            if not query_tokens:
                hybrid_search_total.labels(status="fallback").inc()
                logger.debug(
                    "hybrid_search_empty_query_tokens",
                    query_length=len(query),
                    namespace=namespace.to_tuple(),
                )
                return list(semantic_results[:limit])

            bm25_scores = bm25.get_scores(query_tokens)

            # Guard: empty or all-zero scores → avoid division by zero
            max_bm25_raw = max(bm25_scores) if len(bm25_scores) > 0 else 0.0
            max_bm25 = max_bm25_raw if max_bm25_raw > 0 else 1.0

            # 5. Create lookup maps
            semantic_scores = {r.key: r.score for r in semantic_results}
            bm25_score_map = {
                document_ids[i]: bm25_scores[i] / max_bm25 for i in range(len(document_ids))
            }

            # 6. Combine scores
            combined: list[SearchItem] = []
            seen_keys: set[str] = set()

            for item in all_items:
                key = item.key
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                sem_score = semantic_scores.get(key, 0.0) or 0.0
                bm25_score = bm25_score_map.get(key, 0.0)

                # Hybrid scoring formula
                final_score = alpha * sem_score + (1 - alpha) * bm25_score

                # Boost if both scores are high
                if sem_score > boost_threshold and bm25_score > boost_threshold:
                    final_score *= 1.1

                if final_score >= min_score:
                    # Create SearchItem with hybrid score (Item doesn't accept score)
                    combined.append(
                        SearchItem(
                            namespace=item.namespace,
                            key=item.key,
                            value=item.value,
                            created_at=item.created_at,
                            updated_at=item.updated_at,
                            score=final_score,
                        )
                    )

            # 7. Sort and limit
            combined.sort(key=lambda x: x.score or 0.0, reverse=True)

            hybrid_search_total.labels(status="success").inc()
            logger.debug(
                "hybrid_search_completed",
                namespace=namespace.to_tuple(),
                semantic_count=len(semantic_results),
                bm25_corpus_size=len(all_items),
                result_count=len(combined[:limit]),
            )

            return combined[:limit]

        except Exception as e:
            hybrid_search_total.labels(status="error").inc()
            logger.error(
                "hybrid_search_failed",
                namespace=namespace.to_tuple(),
                error=str(e),
            )
            # Fallback to semantic only
            return list(semantic_results[:limit]) if semantic_results else []
