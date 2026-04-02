"""
Context Variables for Embedding Token Tracking.

Provides a mechanism to propagate user context to GeminiRetrievalEmbeddings
for database persistence of embedding token costs.

Problem:
    LangGraph's AsyncPostgresStore calls embeddings "behind the scenes"
    during asearch() and aput() operations. The embeddings wrapper doesn't
    have access to user_id, conversation_id, etc. needed for DB persistence.

Solution:
    Use Python ContextVar to propagate context from the calling code
    (memory_extractor.py) to the embeddings wrapper. The wrapper reads
    the context and persists tokens to the database.

Architecture:
    memory_extractor.py                 GeminiRetrievalEmbeddings
         │                                      │
         ├─► set_embedding_context()            │
         │                                      │
         ├─► store.asearch()  ─────────────────►├─► embed_query()
         │                                      │     │
         │                                      │     ├─► get_embedding_context()
         │                                      │     │
         │                                      │     └─► _persist_embedding_tokens()
         │                                      │
         └─► clear_embedding_context()          │

Usage:
    >>> from src.infrastructure.llm.embedding_context import (
    ...     set_embedding_context,
    ...     clear_embedding_context,
    ... )
    >>>
    >>> # Set context before store operations
    >>> set_embedding_context(
    ...     user_id="user-123",
    ...     session_id="session-456",
    ...     conversation_id="conv-789",
    ... )
    >>>
    >>> # Store operations will now track embedding tokens to DB
    >>> await store.asearch(namespace, query="...")
    >>> await store.aput(namespace, key="...", value={...})
    >>>
    >>> # Clear context when done
    >>> clear_embedding_context()

References:
    - Python ContextVars: https://docs.python.org/3/library/contextvars.html
    - Similar pattern: LangChain callbacks use contextvars
"""

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EmbeddingTrackingContext:
    """
    Context data for embedding token tracking.

    Contains all information needed to persist embedding tokens
    to the database for user statistics.

    Attributes:
        user_id: User ID for statistics attribution
        session_id: Session ID for logging/grouping
        conversation_id: Optional conversation UUID for linking
    """

    user_id: str
    session_id: str
    conversation_id: str | None = None
    run_id: str | None = None


# Global ContextVar for embedding tracking
# None means no tracking context is set (embeddings won't persist to DB)
_embedding_context: ContextVar[EmbeddingTrackingContext | None] = ContextVar(
    "embedding_tracking_context",
    default=None,
)


def set_embedding_context(
    user_id: str,
    session_id: str,
    conversation_id: str | None = None,
    run_id: str | None = None,
) -> None:
    """
    Set embedding tracking context for the current async context.

    Call this BEFORE any store operations (asearch, aput) that
    trigger embeddings. The GeminiRetrievalEmbeddings wrapper will
    read this context and persist tokens to the database.

    Args:
        user_id: User ID for statistics
        session_id: Session ID for logging
        conversation_id: Optional conversation UUID
        run_id: Optional run ID to merge costs into an existing
            TrackingContext (e.g. the main conversation run_id).
            If None, persist_embedding_tokens generates its own.
    """
    context = EmbeddingTrackingContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        run_id=run_id,
    )
    _embedding_context.set(context)

    logger.debug(
        "embedding_context_set",
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
        run_id=run_id,
    )


def get_embedding_context() -> EmbeddingTrackingContext | None:
    """
    Get current embedding tracking context.

    Returns None if no context is set.
    Used by GeminiRetrievalEmbeddings to check if DB persistence is needed.

    Returns:
        Current EmbeddingTrackingContext or None
    """
    return _embedding_context.get()


def clear_embedding_context() -> None:
    """
    Clear embedding tracking context.

    Call this after store operations are complete to prevent
    accidental token attribution to the wrong user.
    """
    _embedding_context.set(None)
    logger.debug("embedding_context_cleared")


async def persist_embedding_tokens(
    model_name: str,
    token_count: int,
    cost_usd: float,
    operation: str,
    duration_ms: float = 0.0,
) -> None:
    """
    Record embedding tokens for tracking and billing.

    Two strategies (in priority order):
    1. If a conversation TrackingContext is active (via current_tracker ContextVar),
       record directly into it. This makes embedding calls visible in the debug panel
       and ensures they are persisted with the conversation's run_id.
    2. Fallback: if no conversation tracker exists (background operations like RAG
       indexing), create a standalone TrackingContext for separate DB persistence.

    Called by GeminiRetrievalEmbeddings after successful embedding.
    Prometheus metrics are emitted independently by GeminiRetrievalEmbeddings.

    Args:
        model_name: Embedding model used (e.g., "gemini-embedding-001")
        token_count: Number of tokens consumed
        cost_usd: Cost in USD
        operation: Operation type (embed_query, embed_documents)
        duration_ms: Embedding API call duration in milliseconds
    """
    # Skip zero-token operations
    if token_count == 0:
        return

    # =========================================================================
    # Strategy 1: Record into conversation's main TrackingContext
    # Makes embedding calls visible in debug panel (LLM Calls, Pipeline, etc.)
    # =========================================================================
    from src.core.context import current_tracker

    conv_tracker = current_tracker.get()
    if conv_tracker is not None:
        try:
            await conv_tracker.record_node_tokens(
                node_name=f"embedding_{operation}",
                model_name=model_name,
                prompt_tokens=token_count,
                completion_tokens=0,
                cached_tokens=0,
                duration_ms=duration_ms,
                call_type="embedding",
            )
            logger.info(
                "embedding_tokens_recorded_in_conversation_tracker",
                model_name=model_name,
                token_count=token_count,
                cost_usd=round(cost_usd, 6),
                operation=operation,
                duration_ms=round(duration_ms, 1),
                run_id=conv_tracker.run_id,
            )
        except Exception as e:
            # Graceful degradation - never break embeddings for tracking failure
            logger.error(
                "embedding_tokens_conversation_tracker_failed",
                model_name=model_name,
                token_count=token_count,
                operation=operation,
                error=str(e),
                exc_info=True,
            )
        # Always return after Strategy 1 attempt (success or failure).
        # Do NOT fall through to Strategy 2: creating a new TrackingContext
        # would overwrite current_tracker ContextVar (the bug we're fixing).
        return

    # =========================================================================
    # Strategy 2: Standalone persistence (background ops without conversation)
    # e.g., RAG indexing, system space embedding, scheduled tasks
    # =========================================================================
    context = get_embedding_context()

    if not context:
        # No context set - skip DB persistence (Prometheus still tracked)
        logger.debug(
            "embedding_tokens_no_context",
            model_name=model_name,
            token_count=token_count,
            operation=operation,
        )
        return

    try:
        # Import here to avoid circular dependencies
        from src.domains.chat.service import TrackingContext

        # Convert cost to EUR via pricing cache (dynamic ECB rate)
        from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate

        cost_eur = cost_usd * get_cached_usd_eur_rate()

        # Use run_id from context if provided (merges into existing
        # conversation MessageTokenSummary), otherwise generate unique one
        import uuid

        run_id = context.run_id or f"embed_{uuid.uuid4().hex[:12]}"

        # Parse conversation_id if provided
        conv_uuid: UUID | None = None
        if context.conversation_id:
            try:
                conv_uuid = UUID(context.conversation_id)
            except ValueError:
                logger.warning(
                    "embedding_tokens_invalid_conversation_id",
                    conversation_id=context.conversation_id,
                )

        # Create TrackingContext for persistence
        async with TrackingContext(
            run_id=run_id,
            user_id=UUID(context.user_id),
            session_id=context.session_id,
            conversation_id=conv_uuid,  # type: ignore[arg-type]
            auto_commit=False,
        ) as tracker:
            # Record as embedding node (input tokens only, no output)
            await tracker.record_node_tokens(
                node_name=f"embedding_{operation}",
                model_name=model_name,
                prompt_tokens=token_count,  # Embeddings use "input" tokens
                completion_tokens=0,  # No output tokens for embeddings
                cached_tokens=0,  # No caching for embeddings
            )

            await tracker.commit()

        logger.info(
            "embedding_tokens_persisted",
            user_id=context.user_id,
            session_id=context.session_id,
            conversation_id=context.conversation_id,
            model_name=model_name,
            token_count=token_count,
            cost_usd=round(cost_usd, 6),
            cost_eur=round(cost_eur, 6),
            operation=operation,
        )

    except Exception as e:
        # Graceful degradation - never break embeddings for persistence failure
        logger.error(
            "embedding_tokens_persistence_failed",
            user_id=context.user_id if context else "unknown",
            model_name=model_name,
            token_count=token_count,
            error=str(e),
            exc_info=True,
        )
