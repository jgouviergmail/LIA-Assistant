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
"Mon épouse s'appelle Hua Gouvier" with high scores, while unrelated
documents score low. This is equivalent to E5's "query:"/"passage:" prefixes.

Phase: v1.15.0 — Gemini embedding migration for multilingual retrieval
Created: 2026-04-02
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.infrastructure.llm.tracked_embeddings import (
    embedding_api_calls_total,
    embedding_api_latency_seconds,
    embedding_cost_total,
    embedding_tokens_consumed_total,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Approximate token counting for cost tracking.
# Gemini pricing: $0.15 per 1M input tokens.
# Heuristic: ~4 chars per token for multilingual text (approximate).
GEMINI_EMBEDDING_COST_PER_TOKEN_USD = 0.15 / 1_000_000


def _estimate_tokens(texts: list[str]) -> int:
    """Estimate token count from text lengths.

    Rough heuristic: ~4 chars per token for multilingual text.
    Actual Gemini tokenization may differ for CJK or mixed-language text.

    Args:
        texts: List of text strings to estimate.

    Returns:
        Estimated total token count.
    """
    return sum(len(t) // 4 + 1 for t in texts)


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
            self._emit_metrics(token_count, latency, operation, "success")

            # Best-effort DB persistence from sync context
            self._persist_cost_sync(token_count, operation, latency)

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
            self._emit_metrics(token_count, latency, operation, "success")

            # Persist to DB for user billing
            cost_usd = token_count * GEMINI_EMBEDDING_COST_PER_TOKEN_USD
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
        operation: str,
        latency: float,
    ) -> None:
        """Best-effort DB cost persistence from sync context.

        Attempts to schedule the async persist_embedding_tokens via the
        running event loop. Silently skips if no event loop is available
        (e.g., in CLI scripts where Prometheus metrics are sufficient).

        Args:
            token_count: Number of tokens consumed.
            operation: Operation type.
            latency: API call latency in seconds.
        """
        import asyncio

        cost_usd = token_count * GEMINI_EMBEDDING_COST_PER_TOKEN_USD
        try:
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
        except RuntimeError:
            # No event loop running (CLI context) — Prometheus metrics are sufficient
            pass

    def _emit_metrics(
        self,
        token_count: int,
        latency: float,
        operation: str,
        status: str,
    ) -> None:
        """Emit Prometheus metrics for embedding operation.

        Args:
            token_count: Estimated tokens consumed.
            latency: API call latency in seconds.
            operation: Operation type ("embed_documents" or "embed_query").
            status: Call status ("success" or "error").
        """
        embedding_tokens_consumed_total.labels(model=self.model_name, operation=operation).inc(
            token_count
        )
        embedding_api_calls_total.labels(model=self.model_name, status=status).inc()
        embedding_api_latency_seconds.labels(model=self.model_name).observe(latency)

        cost_usd = token_count * GEMINI_EMBEDDING_COST_PER_TOKEN_USD
        embedding_cost_total.labels(model=self.model_name, currency="USD").inc(cost_usd)

        logger.debug(
            "gemini_embedding_tracked",
            model=self.model_name,
            operation=operation,
            token_count=token_count,
            latency_seconds=round(latency, 3),
            cost_usd=round(cost_usd, 6),
        )
