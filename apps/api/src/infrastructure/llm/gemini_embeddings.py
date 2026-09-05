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

from src.core.config import settings
from src.core.constants import CJK_SCRIPT_RANGES
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.llm.embedding_errors import (
    embedding_retry_reason,
    is_transient_embedding_error,
)
from src.infrastructure.llm.tracked_embeddings import (
    embedding_api_calls_total,
    embedding_api_latency_seconds,
    embedding_call_outcomes_total,
    embedding_cost_total,
    embedding_provider_errors_total,
    embedding_shaper_outcomes_total,
    embedding_tokens_consumed_total,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.rate_limiting.slot_waiter import wait_for_slot
from src.infrastructure.utils.retry import retry_async

logger = get_logger(__name__)


class _TransientEmbeddingError(Exception):
    """Marker used to tell :func:`retry_async` which failures to retry.

    The retry helper selects on exception TYPE, while the provider expresses
    itself as a status code buried in a wrapped exception, so the verdict of
    :func:`is_transient_embedding_error` needs a type to travel in.

    It is a marker, never a replacement: the original exception is chained with
    ``from``, so a caller with its own retry policy still reaches the provider's
    status code by walking ``__cause__``.
    """


def _shaper_key(model_name: str) -> str:
    """Shaper key for a model.

    The provider quota is enforced per BASE MODEL across the whole project, so
    the budget is global. Keyed per user, every user would get their own and
    the shaper would shape nothing.
    """
    return f"ratelimit:embeddings:{model_name}"


T = TypeVar("T")


def _exact_str(text: str) -> str:
    """Return ``text`` as an EXACT ``str`` — a subclass instance is copied down.

    The SDK loses the text of a ``str`` SUBCLASS: google-genai validates
    ``contents`` through a pydantic union in which ``Content``
    (``from_attributes=True``) precedes ``str``, and a subclass instance is
    accepted as an attribute-less object — an EMPTY ``Content``. Measured in
    production on 2026-09-05: ``"content": {}`` on the wire and ``500 INTERNAL``
    back, on every RAG query of every turn, identical on google-genai 1.67.0 and
    2.10.0 under pydantic 2.13.4. ``HumanMessage.text`` IS such a subclass
    (langchain-core's ``TextAccessor``), and the memory path only survived
    because slicing (``message[:N]``) happens to yield a plain ``str``.

    Normalising here, at the single funnel every Gemini embedding goes through,
    means no caller can reintroduce the defect by forgetting to slice. An exact
    ``str`` is returned as the same object: the nominal path costs nothing.

    Args:
        text: Any ``str`` instance, subclass or not.

    Returns:
        The same object when it is exactly a ``str``, else a plain ``str`` copy.
    """
    return text if type(text) is str else str(text)


def _exact_strs(texts: list[str]) -> list[str]:
    """Apply :func:`_exact_str` to a batch (see there for why it exists)."""
    return [_exact_str(text) for text in texts]


#: Reason label when the classifier finds nothing transient: the provider said
#: the failure is final (a malformed input, an invalid key).
_PERMANENT_REASON = "permanent"


def _count_provider_error(model_name: str, exc: BaseException) -> None:
    """Count one refused attempt under the reason the retry classified it with.

    One classification, two readers: what decides whether to retry is exactly
    what the metric publishes, so a dashboard and a diagnosis can never disagree
    with the retry about what the provider said.
    """
    embedding_api_calls_total.labels(model=model_name, status="error").inc()
    embedding_provider_errors_total.labels(
        model=model_name, reason=embedding_retry_reason(exc) or _PERMANENT_REASON
    ).inc()


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
    # Deliberately NOT shaped and NOT retried, unlike its async twin. No caller
    # in this repository uses it — the house rule is `aembed_*`, never `embed_*`
    # — and the shaper is an `await`. It exists to satisfy the LangChain
    # `Embeddings` contract. Wiring resilience into a path nobody calls would be
    # code with no way to fail visibly.

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents with task_type=RETRIEVAL_DOCUMENT.

        Args:
            texts: List of document texts to embed.

        Returns:
            List of embedding vectors.
        """
        texts = _exact_strs(texts)
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
        text = _exact_str(text)
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
        texts = _exact_strs(texts)
        return await self._async_tracked_call(
            lambda: self._client.aembed_documents(
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
        text = _exact_str(text)
        return await self._async_tracked_call(
            lambda: self._client.aembed_query(
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
            _count_provider_error(self.model_name, e)
            logger.error("gemini_embedding_failed", model=self.model_name, error=str(e))
            raise

    async def _attempt(
        self,
        factory: Callable[[], Awaitable[T]],
        token_count: int,
        operation: str,
    ) -> T:
        """One provider call, tracked and billed. Raises so the retry can act.

        A transient failure is re-raised as :class:`_TransientEmbeddingError`
        chaining the original, because the retry helper selects on exception
        TYPE while the provider's verdict is a status code inside a wrapper.
        """
        # Each ATTEMPT asks, not each operation: a retry is another call on a
        # provider that just refused one, and letting retries bypass the shaper
        # would add load exactly where it is already saturated.
        outcome = await wait_for_slot(
            _shaper_key(self.model_name),
            settings.embedding_rate_limit_max_calls,
            settings.embedding_rate_limit_window_seconds,
            timeout_seconds=settings.embedding_rate_limit_wait_seconds,
        )
        # Counted, never acted on: whatever the shaper answered, the call goes
        # through. The counter is what tells an operator the budget has become
        # too small for the number of users — the one question this setting
        # cannot answer on its own.
        embedding_shaper_outcomes_total.labels(model=self.model_name, outcome=outcome.value).inc()

        # Timed AFTER the wait: `embedding_api_latency_seconds` answers "how slow
        # is the provider", and folding our own queueing into it would make the
        # shaper look like provider latency the day it starts working.
        start = time.time()
        try:
            result = await factory()
        except Exception as e:
            _count_provider_error(self.model_name, e)
            logger.error("gemini_embedding_failed", model=self.model_name, error=str(e))
            if is_transient_embedding_error(e):
                raise _TransientEmbeddingError(str(e)) from e
            raise

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

    async def _async_tracked_call(
        self,
        factory: Callable[[], Awaitable[T]],
        texts: list[str],
        operation: str,
    ) -> T:
        """Shape, call, retry — the single funnel every async embedding takes.

        Takes a FACTORY rather than an awaitable, and that is the change that
        made the rest possible: a coroutine can be awaited exactly once, so a
        seam holding ``client.aembed_query(...)`` cannot retry it — the second
        await raises instead of calling again.

        Order matters. Every attempt asks the shaper first — a retry is another
        call on a provider that just refused one — and the retry wraps the whole
        thing so what the shaper did not prevent is still recovered. Neither may
        block the caller forever: the wait is bounded and expires OPEN, and only
        transient failures are retried.

        Args:
            factory: Builds a fresh awaitable for the provider call.
            texts: Input texts (for token estimation).
            operation: "embed_documents" or "embed_query".

        Returns:
            The embedding result.

        Raises:
            MaxRetriesExceededError: Every attempt hit a transient failure.
            Exception: A non-transient provider error, unchanged.
        """
        token_count = _estimate_tokens(texts)

        try:
            result = await retry_async(
                lambda: self._attempt(factory, token_count, operation),
                max_retries=settings.embedding_retry_max_attempts,
                backoff_factor=settings.embedding_retry_backoff_factor,
                retryable_exceptions=(_TransientEmbeddingError,),
                operation_name=f"embedding_{operation}",
            )
        except Exception:
            embedding_call_outcomes_total.labels(model=self.model_name, outcome="failed").inc()
            raise

        embedding_call_outcomes_total.labels(model=self.model_name, outcome="succeeded").inc()
        return result

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
