"""
Memory embedding service using OpenAI text-embedding-3-small.

Provides a lazy-initialized TrackedOpenAIEmbeddings instance configured
for LangGraph store semantic search, tool routing, and interest deduplication.
Token tracking is automatic via TrackedOpenAIEmbeddings + Prometheus metrics.

Replaces the former local E5 model (intfloat/multilingual-e5-small, 384 dims)
with OpenAI text-embedding-3-small (1536 dims) to eliminate ~1 GB RAM per worker
(sentence-transformers + PyTorch CPU no longer loaded).

Follows the same singleton pattern as:
- apps/api/src/domains/journals/embedding.py (get_journal_embeddings)
- apps/api/src/domains/rag_spaces/embedding.py (get_rag_embeddings)

Phase: v1.14.0 — Memory optimization (E5 → OpenAI embeddings)
Created: 2026-03-29
"""

from __future__ import annotations

import threading

from pydantic import SecretStr

from src.core.config import settings
from src.infrastructure.llm.providers.adapter import _require_api_key
from src.infrastructure.llm.tracked_embeddings import TrackedOpenAIEmbeddings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Singleton with thread-safe lazy initialization
_memory_embeddings: TrackedOpenAIEmbeddings | None = None
_lock = threading.Lock()


def get_memory_embeddings() -> TrackedOpenAIEmbeddings:
    """Get or create the memory embeddings singleton.

    Returns a TrackedOpenAIEmbeddings instance configured with the model
    and dimensions from settings. Token tracking is automatic via
    Prometheus metrics and optional DB persistence (when EmbeddingTrackingContext
    is set by the caller).

    Used by:
        - LangGraph AsyncPostgresStore (semantic memory search)
        - SemanticToolSelector (tool routing)
        - Interest deduplication (topic similarity)

    Returns:
        TrackedOpenAIEmbeddings instance for memory operations.
    """
    global _memory_embeddings

    if _memory_embeddings is not None:
        return _memory_embeddings

    with _lock:
        # Double-check after acquiring lock
        if _memory_embeddings is not None:
            return _memory_embeddings

        model = settings.memory_embedding_model
        dimensions = settings.memory_embedding_dimensions

        _memory_embeddings = TrackedOpenAIEmbeddings(
            model=model,
            dimensions=dimensions,
            openai_api_key=SecretStr(_require_api_key("openai")),
        )

        logger.info(
            "memory_embeddings_initialized",
            model=model,
            dimensions=dimensions,
        )

    return _memory_embeddings


def reset_memory_embeddings() -> None:
    """Reset the memory embeddings singleton.

    Forces re-initialization with current settings on next use.

    WARNING: Only use in tests to force recreation of embeddings.
    Production code should never call this method.
    """
    global _memory_embeddings

    with _lock:
        _memory_embeddings = None

    logger.info("memory_embeddings_reset")
