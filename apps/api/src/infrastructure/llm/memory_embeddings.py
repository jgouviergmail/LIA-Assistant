"""
Memory embedding service using Google Gemini gemini-embedding-001.

Provides a lazy-initialized GeminiRetrievalEmbeddings instance with
automatic task_type handling (RETRIEVAL_QUERY for search, RETRIEVAL_DOCUMENT
for storage). Token tracking is automatic via Prometheus metrics.

Replaces OpenAI text-embedding-3-small which had poor discrimination
for multilingual retrieval (language bias causing high cosine similarity
between unrelated same-language texts).

Gemini embedding-001 supports 100+ languages with proper retrieval
task types, eliminating the language bias problem.

Follows the same singleton pattern as:
- apps/api/src/domains/journals/embedding.py (get_journal_embeddings)
- apps/api/src/domains/rag_spaces/embedding.py (get_rag_embeddings)

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
_memory_embeddings: GeminiRetrievalEmbeddings | None = None
_lock = threading.Lock()


def get_memory_embeddings() -> GeminiRetrievalEmbeddings:
    """Get or create the memory embeddings singleton.

    Returns a GeminiRetrievalEmbeddings instance that automatically
    applies task_type=RETRIEVAL_QUERY on embed_query and
    task_type=RETRIEVAL_DOCUMENT on embed_documents.

    Used by:
        - Memory services (storage + search)
        - SemanticToolSelector (tool routing)
        - Interest deduplication (topic similarity)

    Returns:
        GeminiRetrievalEmbeddings instance for memory operations.
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

        google_api_key = os.environ.get("GOOGLE_GEMINI_API_KEY", "") or os.environ.get(
            "GOOGLE_API_KEY", ""
        )

        _memory_embeddings = GeminiRetrievalEmbeddings(
            model=model,
            google_api_key=google_api_key,
            output_dimensionality=dimensions,
        )

        logger.info(
            "memory_embeddings_initialized",
            model=model,
            dimensions=dimensions,
            provider="gemini",
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
