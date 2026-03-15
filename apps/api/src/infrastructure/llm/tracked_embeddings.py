"""
Tracked OpenAI Embeddings with Token and Cost Tracking.

Wraps langchain_openai.OpenAIEmbeddings to track tokens consumed
and costs via Prometheus metrics AND database persistence.

LangChain's callbacks do NOT track embedding tokens (known issue).
This wrapper uses tiktoken to count tokens BEFORE embedding and
emits Prometheus metrics for observability.

Architecture:
    - Inherits from OpenAIEmbeddings for full compatibility
    - Overrides embed_documents() and embed_query()
    - Uses tiktoken for token counting (same encoding as OpenAI)
    - Emits metrics to Prometheus for Grafana dashboards
    - Persists to DB via ContextVar (for user billing)

Metrics (Prometheus):
    - embedding_tokens_consumed_total: Counter by model, operation
    - embedding_api_calls_total: Counter by model, status
    - embedding_cost_total: Counter by model, currency

DB Persistence:
    When embedding_context is set (via set_embedding_context()),
    tokens are also persisted to:
    - TokenUsageLog (detailed breakdown)
    - MessageTokenSummary (aggregated per run)
    - UserStatistics (cumulative for billing)

References:
    - LangChain issue: https://github.com/langchain-ai/langchain/issues/945
    - tiktoken encoding: o200k_base for text-embedding-3-* models
"""

import time
from typing import Any

import tiktoken
from langchain_openai import OpenAIEmbeddings
from prometheus_client import Counter, Histogram

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# ============================================================================
# Prometheus Metrics for Embedding Tracking
# ============================================================================

embedding_tokens_consumed_total = Counter(
    "embedding_tokens_consumed_total",
    "Total tokens consumed by embedding operations",
    ["model", "operation"],
)

embedding_api_calls_total = Counter(
    "embedding_api_calls_total",
    "Total embedding API calls",
    ["model", "status"],
)

embedding_api_latency_seconds = Histogram(
    "embedding_api_latency_seconds",
    "Embedding API call latency in seconds",
    ["model"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

embedding_cost_total = Counter(
    "embedding_cost_total",
    "Total cost of embedding operations",
    ["model", "currency"],
)


# Tiktoken encoding for text-embedding-3-* models
# These models use cl100k_base encoding (same as gpt-4)
EMBEDDING_ENCODING = "cl100k_base"


def _count_tokens(texts: list[str], encoding_name: str = EMBEDDING_ENCODING) -> int:
    """
    Count tokens in a list of texts using tiktoken.

    Args:
        texts: List of text strings to count
        encoding_name: tiktoken encoding name

    Returns:
        Total token count across all texts
    """
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        total = 0
        for text in texts:
            if text:
                total += len(encoding.encode(text))
        return total
    except Exception as e:
        logger.warning(
            "token_counting_failed_fallback",
            error=str(e),
            encoding=encoding_name,
        )
        # Fallback: rough estimate of 4 chars per token
        return sum(len(t) // 4 for t in texts if t)


def estimate_embedding_cost_sync(model: str, token_count: int) -> float:
    """
    Estimate cost for embedding tokens (synchronous fallback-only version).

    Uses hardcoded pricing for simplicity and reliability.
    Embedding costs are small and database lookup is not critical here.

    Args:
        model: Embedding model name
        token_count: Number of tokens

    Returns:
        Estimated cost in USD
    """
    # Fallback pricing (USD per 1M tokens) - OpenAI published rates
    fallback_prices = {
        "text-embedding-3-small": 0.02,
        "text-embedding-3-large": 0.13,
        "text-embedding-ada-002": 0.10,
    }
    price_per_1m = fallback_prices.get(model, 0.02)
    return (token_count / 1_000_000) * price_per_1m


async def _estimate_embedding_cost(model: str, token_count: int) -> float:
    """
    Estimate cost for embedding tokens.

    Uses synchronous fallback pricing for reliability.
    Embedding costs are small, so database lookup is not critical.

    Args:
        model: Embedding model name
        token_count: Number of tokens

    Returns:
        Estimated cost in USD
    """
    # Use synchronous fallback for reliability
    # The async version with database lookup was causing import errors
    # that broke memory storage operations
    return estimate_embedding_cost_sync(model, token_count)


class TrackedOpenAIEmbeddings(OpenAIEmbeddings):
    """
    OpenAI Embeddings with automatic token and cost tracking.

    Extends langchain_openai.OpenAIEmbeddings to add:
    - Token counting via tiktoken
    - Prometheus metrics emission
    - Cost estimation via pricing service

    All other functionality is inherited from OpenAIEmbeddings.

    Usage:
        >>> embeddings = TrackedOpenAIEmbeddings(
        ...     model="text-embedding-3-small",
        ...     dimensions=1536,
        ... )
        >>> vectors = await embeddings.aembed_documents(["Hello", "World"])
        # Metrics automatically emitted

    Metrics Emitted:
        - embedding_tokens_consumed_total[model, operation]
        - embedding_api_calls_total[model, status]
        - embedding_api_latency_seconds[model]
        - embedding_cost_total[model, currency]
    """

    async def aembed_documents(
        self,
        texts: list[str],
        **kwargs: Any,
    ) -> list[list[float]]:
        """
        Embed documents with token tracking.

        Counts tokens BEFORE embedding, then emits metrics AFTER.
        """
        model_name = self.model
        start_time = time.time()

        # Count tokens before embedding
        token_count = _count_tokens(texts)

        try:
            # Call parent implementation
            result = await super().aembed_documents(texts, **kwargs)

            # Calculate latency
            latency = time.time() - start_time

            # Track metrics
            embedding_tokens_consumed_total.labels(
                model=model_name,
                operation="embed_documents",
            ).inc(token_count)

            embedding_api_calls_total.labels(
                model=model_name,
                status="success",
            ).inc()

            embedding_api_latency_seconds.labels(model=model_name).observe(latency)

            # Calculate and track cost
            cost_usd = await _estimate_embedding_cost(model_name, token_count)
            embedding_cost_total.labels(
                model=model_name,
                currency="USD",
            ).inc(cost_usd)

            # Convert to EUR if configured
            if settings.default_currency.upper() == "EUR":
                from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate

                cost_eur = cost_usd * get_cached_usd_eur_rate()
                embedding_cost_total.labels(
                    model=model_name,
                    currency="EUR",
                ).inc(cost_eur)

            logger.debug(
                "embedding_documents_tracked",
                model=model_name,
                document_count=len(texts),
                token_count=token_count,
                latency_seconds=round(latency, 3),
                cost_usd=round(cost_usd, 6),
            )

            # Persist to DB if context is set (for user billing)
            from src.infrastructure.llm.embedding_context import persist_embedding_tokens

            await persist_embedding_tokens(
                model_name=model_name,
                token_count=token_count,
                cost_usd=cost_usd,
                operation="embed_documents",
            )

            return result

        except Exception as e:
            # Track error
            embedding_api_calls_total.labels(
                model=model_name,
                status="error",
            ).inc()

            logger.error(
                "embedding_documents_failed",
                model=model_name,
                error=str(e),
            )
            raise

    async def aembed_query(
        self,
        text: str,
        **kwargs: Any,
    ) -> list[float]:
        """
        Embed a single query with token tracking.

        Counts tokens BEFORE embedding, then emits metrics AFTER.
        """
        model_name = self.model
        start_time = time.time()

        # Count tokens before embedding
        token_count = _count_tokens([text])

        try:
            # Call parent implementation
            result = await super().aembed_query(text, **kwargs)

            # Calculate latency
            latency = time.time() - start_time

            # Track metrics
            embedding_tokens_consumed_total.labels(
                model=model_name,
                operation="embed_query",
            ).inc(token_count)

            embedding_api_calls_total.labels(
                model=model_name,
                status="success",
            ).inc()

            embedding_api_latency_seconds.labels(model=model_name).observe(latency)

            # Calculate and track cost
            cost_usd = await _estimate_embedding_cost(model_name, token_count)
            embedding_cost_total.labels(
                model=model_name,
                currency="USD",
            ).inc(cost_usd)

            if settings.default_currency.upper() == "EUR":
                from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate

                cost_eur = cost_usd * get_cached_usd_eur_rate()
                embedding_cost_total.labels(
                    model=model_name,
                    currency="EUR",
                ).inc(cost_eur)

            logger.debug(
                "embedding_query_tracked",
                model=model_name,
                token_count=token_count,
                latency_seconds=round(latency, 3),
                cost_usd=round(cost_usd, 6),
            )

            # Persist to DB if context is set (for user billing)
            from src.infrastructure.llm.embedding_context import persist_embedding_tokens

            await persist_embedding_tokens(
                model_name=model_name,
                token_count=token_count,
                cost_usd=cost_usd,
                operation="embed_query",
            )

            return result

        except Exception as e:
            embedding_api_calls_total.labels(
                model=model_name,
                status="error",
            ).inc()

            logger.error(
                "embedding_query_failed",
                model=model_name,
                error=str(e),
            )
            raise

    def embed_documents(
        self,
        texts: list[str],
        **kwargs: Any,
    ) -> list[list[float]]:
        """
        Sync version of embed_documents with token tracking.
        """
        model_name = self.model
        start_time = time.time()

        # Count tokens before embedding
        token_count = _count_tokens(texts)

        try:
            # Call parent implementation
            result = super().embed_documents(texts, **kwargs)

            # Calculate latency
            latency = time.time() - start_time

            # Track metrics (sync - can't await cost calculation)
            embedding_tokens_consumed_total.labels(
                model=model_name,
                operation="embed_documents",
            ).inc(token_count)

            embedding_api_calls_total.labels(
                model=model_name,
                status="success",
            ).inc()

            embedding_api_latency_seconds.labels(model=model_name).observe(latency)

            # Estimate cost with fallback pricing
            cost_usd = estimate_embedding_cost_sync(model_name, token_count)

            embedding_cost_total.labels(
                model=model_name,
                currency="USD",
            ).inc(cost_usd)

            logger.debug(
                "embedding_documents_tracked_sync",
                model=model_name,
                document_count=len(texts),
                token_count=token_count,
                latency_seconds=round(latency, 3),
                cost_usd=round(cost_usd, 6),
            )

            return result

        except Exception:
            embedding_api_calls_total.labels(
                model=model_name,
                status="error",
            ).inc()
            raise

    def embed_query(
        self,
        text: str,
        **kwargs: Any,
    ) -> list[float]:
        """
        Sync version of embed_query with token tracking.
        """
        model_name = self.model
        start_time = time.time()

        # Count tokens before embedding
        token_count = _count_tokens([text])

        try:
            # Call parent implementation
            result = super().embed_query(text, **kwargs)

            # Calculate latency
            latency = time.time() - start_time

            # Track metrics
            embedding_tokens_consumed_total.labels(
                model=model_name,
                operation="embed_query",
            ).inc(token_count)

            embedding_api_calls_total.labels(
                model=model_name,
                status="success",
            ).inc()

            embedding_api_latency_seconds.labels(model=model_name).observe(latency)

            # Estimate cost with fallback pricing
            cost_usd = estimate_embedding_cost_sync(model_name, token_count)

            embedding_cost_total.labels(
                model=model_name,
                currency="USD",
            ).inc(cost_usd)

            logger.debug(
                "embedding_query_tracked_sync",
                model=model_name,
                token_count=token_count,
                latency_seconds=round(latency, 3),
                cost_usd=round(cost_usd, 6),
            )

            return result

        except Exception:
            embedding_api_calls_total.labels(
                model=model_name,
                status="error",
            ).inc()
            raise
