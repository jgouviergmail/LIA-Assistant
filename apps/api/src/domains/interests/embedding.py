"""
Interest embedding service using Google Gemini gemini-embedding-001.

Provides a lazy-initialized GeminiRetrievalEmbeddings instance for
interest topic indexing and deduplication. Follows the same singleton
pattern as memory and journal embedding services.

Phase: v1.15.0 — Gemini embedding migration
Created: 2026-04-02
"""

from __future__ import annotations

import os
import threading

from src.core.config import settings
from src.infrastructure.llm.gemini_embeddings import GeminiRetrievalEmbeddings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_interest_embeddings: GeminiRetrievalEmbeddings | None = None
_lock = threading.Lock()


def get_interest_embeddings() -> GeminiRetrievalEmbeddings:
    """Get or create the interest embeddings singleton.

    Returns:
        GeminiRetrievalEmbeddings instance for interest operations.
    """
    global _interest_embeddings

    if _interest_embeddings is not None:
        return _interest_embeddings

    with _lock:
        if _interest_embeddings is not None:
            return _interest_embeddings

        model = settings.interest_embedding_model
        dimensions = settings.interest_embedding_dimensions

        google_api_key = os.environ.get("GOOGLE_GEMINI_API_KEY", "") or os.environ.get(
            "GOOGLE_API_KEY", ""
        )

        _interest_embeddings = GeminiRetrievalEmbeddings(
            model=model,
            google_api_key=google_api_key,
            output_dimensionality=dimensions,
        )

        logger.info(
            "interest_embeddings_initialized",
            model=model,
            dimensions=dimensions,
            provider="gemini",
        )

    return _interest_embeddings


def reset_interest_embeddings() -> None:
    """Reset the interest embeddings singleton."""
    global _interest_embeddings

    with _lock:
        _interest_embeddings = None

    logger.info("interest_embeddings_reset")
