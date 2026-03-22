"""
Journal embedding service.

Provides a lazy-initialized TrackedOpenAIEmbeddings instance configured
for journal entry indexing and semantic search. Token tracking is automatic
via TrackedOpenAIEmbeddings + EmbeddingTrackingContext.

Follows the same singleton pattern as RAG Spaces embedding service
(apps/api/src/domains/rag_spaces/embedding.py).

Phase: v1.9.2 — Journal Relevance & Retrieval Overhaul
Created: 2026-03-22
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
_journal_embeddings: TrackedOpenAIEmbeddings | None = None
_lock = threading.Lock()


def get_journal_embeddings() -> TrackedOpenAIEmbeddings:
    """
    Get or create the journal embeddings singleton.

    Returns a TrackedOpenAIEmbeddings instance configured with the model
    and dimensions from settings. Token tracking is automatic via
    Prometheus metrics and optional DB persistence (when EmbeddingTrackingContext
    is set by the caller).

    Returns:
        TrackedOpenAIEmbeddings instance for journal operations
    """
    global _journal_embeddings

    if _journal_embeddings is not None:
        return _journal_embeddings

    with _lock:
        # Double-check after acquiring lock
        if _journal_embeddings is not None:
            return _journal_embeddings

        model = settings.journal_embedding_model
        dimensions = settings.journal_embedding_dimensions

        _journal_embeddings = TrackedOpenAIEmbeddings(
            model=model,
            dimensions=dimensions,
            openai_api_key=SecretStr(_require_api_key("openai")),
        )

        logger.info(
            "journal_embeddings_initialized",
            model=model,
            dimensions=dimensions,
        )

    return _journal_embeddings


def reset_journal_embeddings() -> None:
    """
    Reset the journal embeddings singleton.

    Forces re-initialization with current settings on next use.
    """
    global _journal_embeddings

    with _lock:
        _journal_embeddings = None

    logger.info("journal_embeddings_reset")
