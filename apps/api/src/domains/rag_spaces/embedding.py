"""
RAG Spaces embedding service.

Provides a lazy-initialized TrackedOpenAIEmbeddings instance configured
for RAG document indexing and search. Token tracking is automatic via
TrackedOpenAIEmbeddings + EmbeddingTrackingContext.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
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
_rag_embeddings: TrackedOpenAIEmbeddings | None = None
_lock = threading.Lock()


def get_rag_embeddings() -> TrackedOpenAIEmbeddings:
    """
    Get or create the RAG embeddings singleton.

    Returns a TrackedOpenAIEmbeddings instance configured with the model
    and dimensions from settings. Token tracking is automatic.

    Returns:
        TrackedOpenAIEmbeddings instance for RAG operations
    """
    global _rag_embeddings

    if _rag_embeddings is not None:
        return _rag_embeddings

    with _lock:
        # Double-check after acquiring lock
        if _rag_embeddings is not None:
            return _rag_embeddings

        model = settings.rag_spaces_embedding_model
        dimensions = settings.rag_spaces_embedding_dimensions

        _rag_embeddings = TrackedOpenAIEmbeddings(
            model=model,
            dimensions=dimensions,
            openai_api_key=SecretStr(_require_api_key("openai")),
        )

        logger.info(
            "rag_embeddings_initialized",
            model=model,
            dimensions=dimensions,
        )

    return _rag_embeddings


def reset_rag_embeddings() -> None:
    """
    Reset the RAG embeddings singleton.

    Called after admin changes the embedding model to force re-initialization
    with the new model/dimensions on next use.
    """
    global _rag_embeddings

    with _lock:
        _rag_embeddings = None

    logger.info("rag_embeddings_reset")
