"""
Gemini Retrieval Embeddings with automatic task_type and Prometheus tracking.

Wraps langchain_google_genai.GoogleGenerativeAIEmbeddings to:
- Automatically set task_type=RETRIEVAL_QUERY for embed_query
- Automatically set task_type=RETRIEVAL_DOCUMENT for embed_documents
- Track tokens consumed via Prometheus metrics
- Track costs via DB persistence (EmbeddingTrackingContext)

The task_type parameter is the key to good discrimination: it tells Gemini
to encode queries and documents in asymmetric but aligned spaces, so that
short queries like "ma femme" match relevant documents like
"Mon épouse s'appelle Léa Lemoine" with high scores, while unrelated
documents score low. This is equivalent to E5's "query:"/"passage:" prefixes.

Phase: v1.15.0 — Gemini embedding migration for multilingual retrieval
Created: 2026-04-02
"""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, TypeVar

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.core.constants import CJK_SCRIPT_RANGES
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.llm.tracked_embeddings import (
    embedding_api_calls_total,
    embedding_api_latency_seconds,
    embedding_cost_total,
    embedding_tokens_consumed_total,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Characters belonging to a space-less script, counted one token each.
_CJK_CHAR = re.compile(f"[{CJK_SCRIPT_RANGES}]")

# Characters per token for space-separated scripts. Measured against the real
# Gemini tokenizer over fr/en/de/es/it corpora (2026-08-22): 4 lands within a few
# percent, so this half of the estimate is unchanged.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(texts: list[str]) -> int:
    """Estimate the Gemini token count of a batch, script by script.

    Space-less scripts (zh, ja, ko) tokenize at roughly one token per character,
    space-separated ones at roughly one per four. Applying the 4-character rule
    to Chinese under-counted it by 41-57%, and the whole multilingual corpus by
    15%; splitting the two brings the aggregate to +1% (measured 2026-08-22 over
    36 chunks across the 6 supported languages, ADR-242).

    Args:
        texts: List of text strings to estimate.

    Returns:
        Estimated total token count.
    """
    total = 0
    for text in texts:
        cjk = len(_CJK_CHAR.findall(text))
        total += cjk + (len(text) - cjk) // _CHARS_PER_TOKEN + 1
    return total


def _embedding_cost_usd(model_name: str, token_count: int) -> float:
    """Price a batch from the administered tariff table.

    An embedding model's price is configured in ``llm_model_pricing`` like every
    other model's, and the persisted billing has always read it from there.
    Metrics and logs used a frozen 0.15/1M constant instead, which lied the
    moment the configured model or the tariff changed.

    Args:
        model_name: Model id as keyed in the pricing table (no ``models/``).
        token_count: Input tokens consumed (embeddings produce no output).

    Returns:
        Cost in USD, or 0.0 when no price is cached — observability must never
        be the reason an embedding call fails.
    """
    try:
        cost_usd, _cost_eur = get_cached_cost_usd_eur(model_name, token_count, 0)
    except Exception as e:  # pragma: no cover - defensive; the cache is in-memory
        logger.debug("embedding_pricing_unavailable", model=model_name, error=str(e))
        return 0.0
    return float(cost_usd)


class GeminiRetrievalEmbeddings(Embeddings):
    """Gemini embeddings with automatic RETRIEVAL task types and tracking.

    Delegates to GoogleGenerativeAIEmbeddings, injecting:
    - task_type="RETRIEVAL_QUERY" on embed_query / aembed_query
    - task_type="RETRIEVAL_DOCUMENT" on embed_documents / aembed_documents
    - Prometheus metrics for tokens, calls, latency, cost
    - DB cost persistence via EmbeddingTrackingContext

    Drop-in replacement for TrackedOpenAIEmbeddings — same interface.

    Attributes:
        model_name: Short model ID for metrics/pricing (e.g., "gemini-embedding-001").
        output_dimensionality: Output vector dimensions (768, 1536, or 3072).
    """

    def __init__(
        self,
        model: str = "models/gemini-embedding-001",
        google_api_key: str | None = None,
        output_dimensionality: int = 1536,
    ) -> None:
        """Initialize Gemini embedding wrapper.

        Args:
            model: Gemini model ID (e.g., "models/gemini-embedding-001").
            google_api_key: Google API key with Generative Language API enabled.
            output_dimensionality: Output dimensions (768, 1536, or 3072).
        """
        # Strip "models/" prefix for metrics and pricing DB lookup
        # (pricing table uses "gemini-embedding-001", not "models/gemini-embedding-001")
        self.model_name = model.removeprefix("models/")
        self.output_dimensionality = output_dimensionality
        self._client = GoogleGenerativeAIEmbeddings(
            model=model,
            google_api_key=google_api_key,
        )

    # =========================================================================
    # Sync interface
    # =========================================================================

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents with task_type=RETRIEVAL_DOCUMENT.

        Args:
            texts: List of document texts to embed.

        Returns:
            List of embedding vectors.
        """
        return self._tracked_call(
            lambda: self._client.embed_documents(
                texts,
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.output_dimensionality,
            ),
            texts=texts,
            operation="embed_documents",
        )

    def embed_query(self, text: str) -> list[float]:
        """Embed query with task_type=RETRIEVAL_QUERY.

        Args:
            text: Query text to embed.

        Returns:
            Embedding vector.
        """
        return self._tracked_call(
            lambda: self._client.embed_query(
                text,
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=self.output_dimensionality,
            ),
            texts=[text],
            operation="embed_query",
        )

    # =========================================================================
    # Async interface
    # =========================================================================

    async def aembed_documents(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """Async embed documents with task_type=RETRIEVAL_DOCUMENT.

        Args:
            texts: List of document texts to embed.
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            List of embedding vectors.
        """
        return await self._async_tracked_call(
            self._client.aembed_documents(
                texts,
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.output_dimensionality,
            ),
            texts=texts,
            operation="embed_documents",
        )

    async def aembed_query(self, text: str, **kwargs: Any) -> list[float]:
        """Async embed query with task_type=RETRIEVAL_QUERY.

        Args:
            text: Query text to embed.
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            Embedding vector.
        """
        return await self._async_tracked_call(
            self._client.aembed_query(
                text,
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=self.output_dimensionality,
            ),
            texts=[text],
            operation="embed_query",
        )

    # =========================================================================
    # Tracking helpers
    # =========================================================================

    def _tracked_call(
        self,
        fn: Callable[[], T],
        texts: list[str],
        operation: str,
    ) -> T:
        """Execute sync embedding call with Prometheus tracking and DB persistence.

        Note: DB persistence uses fire-and-forget since we're in a sync context.
        If no event loop is running, DB persistence is skipped gracefully.

        Args:
            fn: Callable that performs the embedding API call.
            texts: Input texts (for token estimation).
            operation: Operation type ("embed_documents" or "embed_query").

        Returns:
            Embedding result from fn().
        """
        token_count = _estimate_tokens(texts)
        start = time.time()
        try:
            result = fn()
            latency = time.time() - start
            cost_usd = self._emit_metrics(token_count, latency, operation, "success")

            # Best-effort DB persistence from sync context
            self._persist_cost_sync(token_count, cost_usd, operation, latency)

            return result
        except Exception as e:
            embedding_api_calls_total.labels(model=self.model_name, status="error").inc()
            logger.error("gemini_embedding_failed", model=self.model_name, error=str(e))
            raise

    async def _async_tracked_call(
        self,
        coro: Awaitable[T],
        texts: list[str],
        operation: str,
    ) -> T:
        """Execute async embedding call with Prometheus tracking and DB persistence.

        Args:
            coro: Awaitable that performs the embedding API call.
            texts: Input texts (for token estimation).
            operation: Operation type ("embed_documents" or "embed_query").

        Returns:
            Embedding result from coro.
        """
        token_count = _estimate_tokens(texts)
        start = time.time()
        try:
            result = await coro
            latency = time.time() - start
            cost_usd = self._emit_metrics(token_count, latency, operation, "success")

            # Persist to DB for user billing
            from src.infrastructure.llm.embedding_context import persist_embedding_tokens

            await persist_embedding_tokens(
                model_name=self.model_name,
                token_count=token_count,
                cost_usd=cost_usd,
                operation=operation,
                duration_ms=latency * 1000,
            )

            return result
        except Exception as e:
            embedding_api_calls_total.labels(model=self.model_name, status="error").inc()
            logger.error("gemini_embedding_failed", model=self.model_name, error=str(e))
            raise

    def _persist_cost_sync(
        self,
        token_count: int,
        cost_usd: float,
        operation: str,
        latency: float,
    ) -> None:
        """Best-effort DB cost persistence from sync context.

        Attempts to schedule the async persist_embedding_tokens via the
        running event loop. Silently skips if no event loop is available
        (e.g., in CLI scripts where Prometheus metrics are sufficient).

        Args:
            token_count: Number of tokens consumed.
            cost_usd: Cost already priced by :meth:`_emit_metrics` for this batch.
            operation: Operation type.
            latency: API call latency in seconds.
        """
        import asyncio

        # No event loop running (CLI context) — Prometheus metrics are sufficient
        with suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            from src.infrastructure.llm.embedding_context import persist_embedding_tokens

            loop.create_task(
                persist_embedding_tokens(
                    model_name=self.model_name,
                    token_count=token_count,
                    cost_usd=cost_usd,
                    operation=operation,
                    duration_ms=latency * 1000,
                )
            )

    def _emit_metrics(
        self,
        token_count: int,
        latency: float,
        operation: str,
        status: str,
    ) -> float:
        """Emit Prometheus metrics for one embedding operation.

        Args:
            token_count: Estimated tokens consumed.
            latency: API call latency in seconds.
            operation: Operation type ("embed_documents" or "embed_query").
            status: Call status ("success" or "error").

        Returns:
            The cost in USD this batch was priced at, so the caller can reuse it
            for persistence instead of pricing the same batch a second time.
        """
        embedding_tokens_consumed_total.labels(model=self.model_name, operation=operation).inc(
            token_count
        )
        embedding_api_calls_total.labels(model=self.model_name, status=status).inc()
        embedding_api_latency_seconds.labels(model=self.model_name).observe(latency)

        cost_usd = _embedding_cost_usd(self.model_name, token_count)
        embedding_cost_total.labels(model=self.model_name, currency="USD").inc(cost_usd)

        logger.debug(
            "gemini_embedding_tracked",
            model=self.model_name,
            operation=operation,
            token_count=token_count,
            latency_seconds=round(latency, 3),
            cost_usd=round(cost_usd, 6),
        )
        return cost_usd
