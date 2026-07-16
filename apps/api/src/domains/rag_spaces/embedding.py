"""
RAG Spaces embedding service using Google Gemini gemini-embedding-001.

Provides a lazy-initialized GeminiRetrievalEmbeddings instance with
automatic task_type handling (RETRIEVAL_QUERY for search, RETRIEVAL_DOCUMENT
for indexing). Token tracking is automatic via Prometheus metrics.

Phase: v1.15.0 — Gemini embedding migration for multilingual retrieval
Created: 2026-04-02
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time

from src.core.config import settings
from src.core.constants import (
    RAG_QUERY_EMBEDDING_CACHE_MAX_SIZE,
    RAG_QUERY_EMBEDDING_CACHE_TTL_SECONDS,
)
from src.infrastructure.llm.gemini_embeddings import GeminiRetrievalEmbeddings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_rag_embeddings: GeminiRetrievalEmbeddings | None = None
_lock = threading.Lock()

# Query embedding cache (in-process, text-hash keyed) with single-flight dedup.
# Within a turn, the user-RAG and system-RAG retrievals embed the SAME user
# message — without dedup that is two identical Gemini API calls (and once
# retrievals run concurrently, a plain cache cannot prevent the race).
# dict[cache_key] -> (monotonic_timestamp, embedding_vector)
_query_cache: dict[str, tuple[float, list[float]]] = {}
# dict[cache_key] -> in-flight embedding task (single-flight)
_query_inflight: dict[str, asyncio.Task[list[float]]] = {}


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
    Also clears the query embedding cache (keys include the model name, so
    stale entries would expire anyway — this just frees them immediately).
    """
    global _rag_embeddings

    with _lock:
        _rag_embeddings = None
    _query_cache.clear()

    logger.info("rag_embeddings_reset")


def _query_cache_key(text: str) -> str:
    """Cache key for a query embedding: model-scoped hash of the text.

    Includes the model name so an admin model change never serves vectors
    computed by the previous model. MD5 for speed (not security).
    """
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"{settings.rag_spaces_embedding_model}:{digest}"


def _cleanup_query_cache() -> None:
    """Evict expired entries and enforce max cache size (lazy, non-blocking)."""
    now = time.monotonic()
    stale_keys = [
        k for k, (ts, _) in _query_cache.items() if now - ts > RAG_QUERY_EMBEDDING_CACHE_TTL_SECONDS
    ]
    for k in stale_keys:
        del _query_cache[k]

    while len(_query_cache) > RAG_QUERY_EMBEDDING_CACHE_MAX_SIZE:
        oldest_key = next(iter(_query_cache))
        del _query_cache[oldest_key]


async def _compute_query_embedding(key: str, query: str) -> list[float]:
    """Shared single-flight body: embed, cache on success, always deregister.

    Owning the cache-write and the in-flight cleanup here (not in the callers)
    lets the embed survive a caller's cancellation: callers await it through
    ``asyncio.shield`` (F016), so a local cancellation never destroys the shared
    computation for the other waiters. Policy when every waiter is cancelled: the
    task still runs to completion and populates the cache — the work is not
    wasted and a later identical query reuses it within the TTL. On failure the
    cache is left untouched (the ``finally`` only pops the in-flight entry), so
    the next caller retries with a fresh task.
    """
    try:
        vector = await get_rag_embeddings().aembed_query(query)
        _query_cache[key] = (time.monotonic(), vector)
        return vector
    finally:
        _query_inflight.pop(key, None)


def _drain_task_exception(task: asyncio.Task[list[float]]) -> None:
    """Retrieve a finished task's exception so a fully-abandoned embed (all
    waiters cancelled) does not emit 'Task exception was never retrieved'."""
    if not task.cancelled():
        task.exception()


async def embed_rag_query_cached(query: str) -> list[float]:
    """Embed a RAG query with an in-process TTL cache and single-flight dedup.

    - Cache hit: returns the cached vector, no API call.
    - Concurrent identical queries (e.g. user-RAG + system-RAG retrievals of
      the same turn running in parallel): the second caller awaits the first
      caller's in-flight task instead of issuing a duplicate Gemini call.
    - Embedding cost tracking: attribution follows the caller that actually
      triggered the API call (only one call happens), via the
      EmbeddingTrackingContext set by that caller.

    Args:
        query: Query text to embed (task_type=RETRIEVAL_QUERY).

    Returns:
        Embedding vector for the query.
    """
    key = _query_cache_key(query)
    _cleanup_query_cache()

    cached = _query_cache.get(key)
    if cached is not None:
        logger.debug("rag_query_embedding_cache_hit", key=key[-12:])
        return cached[1]

    inflight = _query_inflight.get(key)
    if inflight is None:
        # The shared task owns the embed, the cache-write and its own in-flight
        # cleanup (see _compute_query_embedding).
        inflight = asyncio.create_task(_compute_query_embedding(key, query))
        inflight.add_done_callback(_drain_task_exception)
        _query_inflight[key] = inflight
    else:
        logger.debug("rag_query_embedding_inflight_join", key=key[-12:])

    # shield: a local cancellation (initiator OR joiner) must NOT cancel the
    # shared embed for the other waiters (F016).
    return await asyncio.shield(inflight)
