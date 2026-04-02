"""
RAG Spaces embedding service using Google Gemini gemini-embedding-001.

Provides a lazy-initialized GeminiRetrievalEmbeddings instance with
automatic task_type handling (RETRIEVAL_QUERY for search, RETRIEVAL_DOCUMENT
for indexing). Token tracking is automatic via Prometheus metrics.

Phase: v1.15.0 — Gemini embedding migration for multilingual retrieval
Created: 2026-04-02
"""

from __future__ import annotations

import os
import threading

from src.core.config import settings
from src.infrastructure.llm.gemini_embeddings import GeminiRetrievalEmbeddings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_rag_embeddings: GeminiRetrievalEmbeddings | None = None
_lock = threading.Lock()


def get_rag_embeddings() -> GeminiRetrievalEmbeddings:
    """Get or create the RAG embeddings singleton.

    Returns a GeminiRetrievalEmbeddings instance that automatically
    applies task_type=RETRIEVAL_QUERY on embed_query and
    task_type=RETRIEVAL_DOCUMENT on embed_documents.

    Returns:
        GeminiRetrievalEmbeddings instance for RAG operations.
    """
    global _rag_embeddings

    if _rag_embeddings is not None:
        return _rag_embeddings

    with _lock:
        if _rag_embeddings is not None:
            return _rag_embeddings

        model = settings.rag_spaces_embedding_model
        dimensions = settings.rag_spaces_embedding_dimensions

        google_api_key = os.environ.get("GOOGLE_GEMINI_API_KEY", "") or os.environ.get(
            "GOOGLE_API_KEY", ""
        )

        _rag_embeddings = GeminiRetrievalEmbeddings(
            model=model,
            google_api_key=google_api_key,
            output_dimensionality=dimensions,
        )

        logger.info(
            "rag_embeddings_initialized",
            model=model,
            dimensions=dimensions,
            provider="gemini",
        )

    return _rag_embeddings


def reset_rag_embeddings() -> None:
    """Reset the RAG embeddings singleton.

    Called after admin changes the embedding model to force re-initialization.
    """
    global _rag_embeddings

    with _lock:
        _rag_embeddings = None

    logger.info("rag_embeddings_reset")
