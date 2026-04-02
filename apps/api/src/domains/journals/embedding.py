"""
Journal embedding service using Google Gemini gemini-embedding-001.

Provides a lazy-initialized GeminiRetrievalEmbeddings instance with
automatic task_type handling (RETRIEVAL_QUERY for search, RETRIEVAL_DOCUMENT
for storage). Token tracking is automatic via Prometheus metrics.

Follows the same singleton pattern as:
- apps/api/src/infrastructure/llm/memory_embeddings.py (get_memory_embeddings)

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

# Singleton with thread-safe lazy initialization
_journal_embeddings: GeminiRetrievalEmbeddings | None = None
_lock = threading.Lock()


def get_journal_embeddings() -> GeminiRetrievalEmbeddings:
    """Get or create the journal embeddings singleton.

    Returns a GeminiRetrievalEmbeddings instance that automatically
    applies task_type=RETRIEVAL_QUERY on embed_query and
    task_type=RETRIEVAL_DOCUMENT on embed_documents.

    Returns:
        GeminiRetrievalEmbeddings instance for journal operations.
    """
    global _journal_embeddings

    if _journal_embeddings is not None:
        return _journal_embeddings

    with _lock:
        if _journal_embeddings is not None:
            return _journal_embeddings

        model = settings.journal_embedding_model
        dimensions = settings.journal_embedding_dimensions

        google_api_key = os.environ.get("GOOGLE_GEMINI_API_KEY", "") or os.environ.get(
            "GOOGLE_API_KEY", ""
        )

        _journal_embeddings = GeminiRetrievalEmbeddings(
            model=model,
            google_api_key=google_api_key,
            output_dimensionality=dimensions,
        )

        logger.info(
            "journal_embeddings_initialized",
            model=model,
            dimensions=dimensions,
            provider="gemini",
        )

    return _journal_embeddings


def reset_journal_embeddings() -> None:
    """Reset the journal embeddings singleton."""
    global _journal_embeddings

    with _lock:
        _journal_embeddings = None

    logger.info("journal_embeddings_reset")
