"""
Context Variables for Embedding Token Tracking.

Provides a mechanism to propagate user context to TrackedOpenAIEmbeddings
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
    memory_extractor.py                 TrackedOpenAIEmbeddings
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
) -> None:
    """
    Set embedding tracking context for the current async context.

    Call this BEFORE any store operations (asearch, aput) that
    trigger embeddings. The TrackedOpenAIEmbeddings wrapper will
    read this context and persist tokens to the database.

    Args:
        user_id: User ID for statistics
        session_id: Session ID for logging
        conversation_id: Optional conversation UUID
    """
    context = EmbeddingTrackingContext(
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
    )
    _embedding_context.set(context)

    logger.debug(
        "embedding_context_set",
        user_id=user_id,
        session_id=session_id,
        conversation_id=conversation_id,
    )


def get_embedding_context() -> EmbeddingTrackingContext | None:
    """
    Get current embedding tracking context.

    Returns None if no context is set.
    Used by TrackedOpenAIEmbeddings to check if DB persistence is needed.

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
) -> None:
    """
    Persist embedding tokens to database.

    Called by TrackedOpenAIEmbeddings after successful embedding.
    Uses the current context to determine user attribution.

    Args:
        model_name: Embedding model used
        token_count: Number of tokens consumed
        cost_usd: Cost in USD
        operation: Operation type (embed_query, embed_documents)
    """
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

    # Skip zero-token operations
    if token_count == 0:
        return

    try:
        # Import here to avoid circular dependencies
        from src.domains.chat.service import TrackingContext

        # Convert cost to EUR
        cost_eur = cost_usd * 0.94  # Approximate rate

        # Generate unique run_id for this embedding operation
        import uuid

        run_id = f"embed_{uuid.uuid4().hex[:12]}"

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
