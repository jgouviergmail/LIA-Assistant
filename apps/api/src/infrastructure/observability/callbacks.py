"""
LangChain callbacks for observability.

Captures LLM API calls metrics (tokens, costs, latency) using LangChain's
callback system for comprehensive observability.
"""

import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from src.domains.chat.service import TrackingContext

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import LLMResult
from prometheus_client import Counter

from src.core.config import settings
from src.core.field_names import FIELD_METADATA, FIELD_MODEL_NAME
from src.infrastructure.observability.error_taxonomy import classify_llm_error
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    estimate_cost_from_cache,
    llm_api_calls_total,
    llm_api_latency_seconds,
    llm_cost_total,
    llm_tokens_consumed_total,
)
from src.infrastructure.observability.token_extractor import TokenExtractor

logger = get_logger(__name__)

# ADR-220: a completed LLM call whose result carries NO token usage. On a paid
# provider this means the ledger, the spend ceiling and the dashboards did not
# see the spend — for months the only trace was a model="unknown" label and a
# DEBUG log (ex-F1). Lives next to its single emitter (MetricsCallbackHandler,
# below — the llm_cache counters follow the same pattern); node_name only: the
# model is precisely what a usage-less result cannot tell us reliably.
llm_calls_without_usage_total = Counter(
    "llm_calls_without_usage_total",
    "Completed LLM calls whose result carried no token usage metadata",
    ["node_name"],
)


class MetricsCallbackHandler(AsyncCallbackHandler):
    """
    LangChain async callback handler for metrics collection.

    Captures:
    - Token consumption (prompt + completion)
    - API call latency
    - API call success/failure
    - Estimated costs
    """

    def __init__(self, node_name: str = "unknown", llm: BaseChatModel | None = None) -> None:
        """
        Initialize metrics callback handler.

        Args:
            node_name: Name of the node (router, response) for metrics labels
            llm: LLM instance to extract model name from (optional)
        """
        super().__init__()
        self.node_name = node_name
        self.llm = llm
        self.start_times: dict[UUID, float] = {}
        # Phase 2.1 (RC4 Fix): Store last usage for cache decorator
        # CRITICAL: Cleared on each on_llm_start to prevent memory leaks
        self._last_usage_metadata: dict[str, Any] | None = None
        # Idempotency guard (symmetric with TokenTrackingCallback): a single LLM
        # run_id must emit Prometheus metrics exactly once. ``on_llm_end`` can fire
        # twice for the same run when this handler is double-attached on the
        # ``astream_events`` reasoning path (see TokenTrackingCallback.__init__).
        # enrich_config_preserving_callbacks already removes that double-fire at the
        # source on the reasoning path; this guard is the matching defense-in-depth so
        # the metrics path (llm_tokens_consumed_total / llm_api_calls_total /
        # llm_cost_total) cannot double-count if a duplicate ``on_llm_end`` ever
        # reaches the same instance from another source.
        self._recorded_llm_run_ids: set[UUID] = set()

    def _store_start_time(self, run_id: UUID) -> None:
        """Store start time for latency calculation (DRY helper)."""
        self.start_times[run_id] = time.time()
        self._last_usage_metadata = None

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts (legacy text completion models)."""
        self._store_start_time(run_id)

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when ChatModel starts (modern chat models like GPT-4)."""
        self._store_start_time(run_id)

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM ends running successfully."""
        # Idempotency guard (parallel-safe): emit metrics once per LLM run_id. The
        # check-and-mark is atomic under asyncio (no ``await`` between), so concurrent
        # duplicate ends cannot both pass. Mirrors TokenTrackingCallback.on_llm_end.
        if run_id in self._recorded_llm_run_ids:
            return
        self._recorded_llm_run_ids.add(run_id)

        # Calculate latency
        latency = time.time() - self.start_times.pop(run_id, time.time())

        # **Phase 2.1 - Token Tracking Alignment Fix (CRITICAL)**
        # Extract node_name from kwargs metadata (set by enrich_config_with_node_metadata)
        # This overrides self.node_name from __init__ to support dynamic node context
        metadata = kwargs.get(FIELD_METADATA, {})
        node_name = metadata.get("langgraph_node", self.node_name)

        # Extract token usage using centralized extractor (eliminates duplication)
        usage = TokenExtractor.extract(response, self.llm)

        if not usage:
            # No usage found - track API call but skip token metrics.
            # ADR-220: this is an accounting hole, not a curiosity — on a paid
            # provider the ledger and the spend ceiling just missed the spend.
            # Count it and say it at WARNING (node_name only, never content).
            llm_api_calls_total.labels(model="unknown", node_name=node_name, status="success").inc()
            llm_api_latency_seconds.labels(model="unknown", node_name=node_name).observe(latency)
            llm_calls_without_usage_total.labels(node_name=node_name).inc()
            logger.warning(
                "llm_call_without_usage",
                node_name=node_name,
                latency_seconds=round(latency, 3),
                msg="LLM call completed without token usage metadata — spend not accounted",
            )
            return

        model_name = usage.model_name
        prompt_tokens = usage.input_tokens
        completion_tokens = usage.output_tokens
        cached_tokens = usage.cached_tokens

        # Phase 2.1 (RC4 Fix): Store usage for cache decorator
        # Will be extracted by cache decorator after function completes
        # Cleared on next on_llm_start to prevent memory leaks
        self._last_usage_metadata = {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "cached_tokens": cached_tokens,
            FIELD_MODEL_NAME: model_name,
        }

        # Track tokens consumed
        if prompt_tokens > 0:
            llm_tokens_consumed_total.labels(
                model=model_name, node_name=node_name, token_type="prompt_tokens"
            ).inc(prompt_tokens)
            # Dashboard 07 "Context Tokens by Node" — current context size
            with suppress(Exception):
                from src.infrastructure.observability.metrics_agents import (
                    agent_context_tokens_gauge,
                )

                agent_context_tokens_gauge.labels(node_name=node_name).set(prompt_tokens)

        if completion_tokens > 0:
            llm_tokens_consumed_total.labels(
                model=model_name,
                node_name=node_name,
                token_type="completion_tokens",
            ).inc(completion_tokens)

        if cached_tokens > 0:
            llm_tokens_consumed_total.labels(
                model=model_name, node_name=node_name, token_type="cached_tokens"
            ).inc(cached_tokens)

        # Track API call success
        llm_api_calls_total.labels(model=model_name, node_name=node_name, status="success").inc()

        # Track latency
        llm_api_latency_seconds.labels(model=model_name, node_name=node_name).observe(latency)

        # Estimate cost using cached prices (sync, no DB access - safe for callbacks)
        cost = estimate_cost_from_cache(
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
        )
        # Get configured currency (validated Enum: USD or EUR)
        currency = settings.default_currency.upper()
        llm_cost_total.labels(model=model_name, node_name=node_name, currency=currency).inc(cost)

        # Debug log removed - hot path (every LLM call), all info already in Prometheus metrics
        # Metrics: llm_tokens_consumed_total, llm_api_latency_seconds, llm_cost_total

        # NOTE: Token tracking is now done via usage_metadata extraction
        # in AgentService after graph execution completes
        # This approach is more reliable and follows LangChain 2025 best practices

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM errors."""
        # Clean up start time
        self.start_times.pop(run_id, None)

        # **Phase 2.1 - Token Tracking Alignment Fix (CRITICAL)**
        # Extract node_name from kwargs metadata (set by enrich_config_with_node_metadata)
        # This overrides self.node_name from __init__ to support dynamic node context
        metadata = kwargs.get(FIELD_METADATA, {})
        node_name = metadata.get("langgraph_node", self.node_name)

        # Extract model name from LLM instance if available
        model_name = "unknown"
        if self.llm:
            with suppress(Exception):
                model_name = getattr(self.llm, "model_name", "unknown")

        # Track API call error
        llm_api_calls_total.labels(model=model_name, node_name=node_name, status="error").inc()

        # METRICS: Classify and track specific LLM error types
        from src.infrastructure.observability.metrics_errors import (
            llm_api_errors_total,
            llm_content_filter_violations_total,
            llm_context_length_exceeded_total,
            llm_rate_limit_hit_total,
        )

        provider = self._infer_provider(model_name)
        error_type = self._classify_llm_error(error)

        # Track general LLM API error
        llm_api_errors_total.labels(provider=provider, error_type=error_type).inc()

        # Track specific error categories with additional context
        error_str = str(error).lower()

        # Rate limit errors
        if error_type == "rate_limit":
            # Infer limit type from error message
            limit_type = "requests_per_minute"  # default
            if "tokens per min" in error_str or "tpm" in error_str:
                limit_type = "tokens_per_minute"
            elif "requests per day" in error_str or "rpd" in error_str:
                limit_type = "requests_per_day"

            llm_rate_limit_hit_total.labels(provider=provider, limit_type=limit_type).inc()

        # Context length exceeded errors
        elif error_type == "context_length_exceeded":
            llm_context_length_exceeded_total.labels(provider=provider, model=model_name).inc()

        # Content filter violations
        elif error_type == "content_filter":
            llm_content_filter_violations_total.labels(provider=provider).inc()

        logger.error(
            "llm_api_call_failed",
            run_id=str(run_id),
            node_name=node_name,
            model=model_name,
            provider=provider,
            error=str(error),
            error_type=type(error).__name__,
            classified_error=error_type,
        )

    @staticmethod
    def _infer_provider(model_name: str) -> str:
        """
        Infer LLM provider from model name.

        Args:
            model_name: Model identifier (e.g., "gpt-4.1-mini", "claude-3-5-sonnet")

        Returns:
            Provider name (openai, anthropic, google, deepseek, perplexity, ollama, unknown)
        """
        model_lower = model_name.lower()

        if any(
            model_lower.startswith(prefix)
            for prefix in [
                "gpt-",
                "o1",
                "o3",
                "o4",
                "davinci",
                "babbage",
                "chatgpt-",
                "codex",
            ]
        ):
            return "openai"
        elif "claude" in model_lower:
            return "anthropic"
        elif any(prefix in model_lower for prefix in ["gemini", "palm", "bard"]):
            return "google"
        elif model_lower.startswith("deepseek"):
            return "deepseek"
        elif "sonar" in model_lower:
            return "perplexity"
        elif model_lower.startswith("qwen"):
            return "qwen"
        elif any(
            model_lower.startswith(prefix) for prefix in ["llama", "mistral", "phi-", "codellama"]
        ):
            return "ollama"
        else:
            return "unknown"

    @staticmethod
    def _classify_llm_error(error: BaseException) -> str:
        """Delegate to the shared taxonomy (see :mod:`error_taxonomy`).

        Kept as a method because the metrics handler and its tests call it that
        way; the vocabulary and the rules live in one module so the Prometheus
        label and ``token_usage_logs.failure_kind`` cannot diverge.
        """
        return classify_llm_error(error)


class TokenTrackingCallback(AsyncCallbackHandler):
    """
    Callback handler for tracking LLM token usage in TrackingContext.

    Modern approach (2025): Intercepts ALL LLM calls via callbacks,
    regardless of invocation pattern (regular, with_structured_output, agents).

    This solves the problem where router_node uses with_structured_output()
    which doesn't add AIMessage to state, making tokens invisible to
    post-execution message scanning.

    Attributes:
        tracker: TrackingContext instance to record tokens
        run_id: LangGraph run ID for logging
    """

    def __init__(self, tracker: TrackingContext, run_id: str) -> None:
        """
        Initialize token tracking callback.

        Args:
            tracker: TrackingContext instance from src.domains.chat.service
            run_id: LangGraph run ID for logging correlation
        """
        super().__init__()
        self.tracker = tracker
        self.run_id = run_id
        # Phase 2.1 (RC4 Fix): Store last usage for cache decorator
        # CRITICAL: Cleared on each on_llm_start to prevent memory leaks
        self._last_usage_metadata: dict[str, Any] | None = None
        # v3.2: Per-call tracking to support parallel execution
        # Keyed by LLM call run_id (UUID) to avoid race conditions
        # when multiple LLM calls run concurrently (e.g., parallel_executor)
        self._call_context: dict[str, dict[str, Any]] = {}
        # Idempotency guard: LLM run_ids already recorded. A single physical LLM
        # call must be recorded exactly once. On the reasoning-streaming path
        # (``astream_events``) this handler can be attached twice — once inherited
        # from the graph-level config and once as a per-node local handler after
        # ``enrich_config_with_node_metadata`` — and LangChain does not dedupe the
        # two attachments there, so ``on_llm_end`` fires twice for the same run_id.
        # Without this guard the second invocation records a phantom
        # ``node_name="unknown"`` row with identical tokens, double-counting the
        # call in the debug panel, the persisted summary and user statistics.
        self._recorded_llm_run_ids: set[str] = set()

    def _store_call_context(self, run_id: UUID, metadata: dict[str, Any] | None) -> None:
        """Store per-call context for parallel-safe tracking (DRY helper)."""
        self._last_usage_metadata = None
        md = metadata or {}
        # node_name_override: set by ReactSubAgentRunner to display a
        # user-friendly name (e.g., "MCP Iterative: excalidraw") instead
        # of the internal graph node name ("agent").
        node_name = md.get("node_name_override") or md.get("langgraph_node", "unknown")
        self._call_context[str(run_id)] = {
            "node_name": node_name,
            # The configured slot, put here by create_instrumented_config at
            # every instrumented call site (ADR-244). node_name cannot stand in
            # for it: that is the graph node, its values are unbounded, and it
            # does not map to a slot.
            "llm_type": md.get("llm_type"),
            "start_time": time.time(),
        }

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts (legacy text completion models)."""
        self._store_call_context(run_id, kwargs.get(FIELD_METADATA))

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when ChatModel starts (modern chat models like GPT-4)."""
        logger.debug(
            "token_tracking_on_chat_model_start_provenance",
            graph_run_id=self.run_id,
            llm_run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tags=tags,
            langgraph_node=(metadata or {}).get("langgraph_node"),
        )
        self._store_call_context(run_id, metadata)

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called when LLM completes - extract and record token usage.

        Args:
            response: LLMResult with generations and usage metadata
            run_id: Unique ID for this LLM call
            parent_run_id: Parent run ID if nested
            tags: Tags from LangChain
            **kwargs: Additional args
        """
        run_id_str = str(run_id)

        # Provenance of this callback invocation (run-tree scope). Used to diagnose
        # duplicate on_llm_end firings: two fires of the same LLM run_id with
        # different parent_run_id/tags reveal two distinct callback-manager scopes.
        parent_run_id_str = str(parent_run_id) if parent_run_id else None
        meta_node = (kwargs.get(FIELD_METADATA) or {}).get("langgraph_node")

        # Idempotency guard (parallel-safe): a single LLM run_id must be recorded
        # once. ``on_llm_end`` can fire twice for the same run when this handler is
        # double-attached on the ``astream_events`` reasoning path (see __init__).
        # The check-and-mark below is atomic under asyncio (no ``await`` between),
        # so concurrent duplicate ends cannot both pass. The first end carries the
        # real node context; the second is a no-op skip.
        if run_id_str in self._recorded_llm_run_ids:
            logger.debug(
                "token_tracking_duplicate_llm_end_skipped",
                run_id=self.run_id,
                llm_run_id=run_id_str,
                parent_run_id=parent_run_id_str,
                tags=tags,
                langgraph_node=meta_node,
                msg="Duplicate on_llm_end for same LLM run_id; skipping to avoid double-count",
            )
            return
        self._recorded_llm_run_ids.add(run_id_str)

        # v3.2: Retrieve and cleanup per-call context (parallel-safe)
        call_ctx = self._call_context.pop(run_id_str, {})
        node_name = call_ctx.get("node_name", "unknown")
        start_time = call_ctx.get("start_time", 0.0)

        # DEBUG: Log callback invocation to diagnose Planner token tracking issue
        logger.info(
            "token_tracking_callback_on_llm_end_called",
            run_id=run_id_str,
            node_name=node_name,
            graph_run_id=self.run_id,
            parent_run_id=parent_run_id_str,
            tags=tags,
            langgraph_node=meta_node,
        )

        try:
            # Extract token usage using centralized extractor (eliminates duplication)
            usage_data = TokenExtractor.extract(response)

            if not usage_data:
                # ADR-220: WARNING, not debug — a paid call whose tokens never
                # reach token_usage_logs is a ledger hole. The counter lives in
                # MetricsCallbackHandler (both handlers fire for the same call;
                # incrementing here too would double-count).
                logger.warning(
                    "token_tracking_no_usage",
                    run_id=self.run_id,
                    llm_run_id=run_id_str,
                    node_name=node_name,
                    msg="No usage metadata in LLMResult — spend not persisted",
                )
                return

            # DEBUG: Log token extraction to diagnose Planner issue
            logger.info(
                "token_tracking_callback_tokens_extracted",
                run_id=self.run_id,
                node_name=node_name,
                model=usage_data.model_name,
                prompt_tokens=usage_data.input_tokens,
                completion_tokens=usage_data.output_tokens,
                cached_tokens=usage_data.cached_tokens,
            )

            # Phase 2.1 (RC4 Fix): Store usage for cache decorator
            # Will be extracted by cache decorator after function completes
            # Cleared on next on_llm_start to prevent memory leaks
            self._last_usage_metadata = {
                "input_tokens": usage_data.input_tokens,
                "output_tokens": usage_data.output_tokens,
                "cached_tokens": usage_data.cached_tokens,
                FIELD_MODEL_NAME: usage_data.model_name,
            }

            # v3.2 Debug Panel: Calculate LLM call duration (parallel-safe)
            duration_ms = (time.time() - start_time) * 1000 if start_time > 0 else 0.0

            # Record in TrackingContext (unified method with auto-cost calculation)
            await self.tracker.record_node_tokens(
                node_name=node_name,
                model_name=usage_data.model_name,
                prompt_tokens=usage_data.input_tokens,
                completion_tokens=usage_data.output_tokens,
                cached_tokens=usage_data.cached_tokens,
                duration_ms=duration_ms,
                # v3.4 waterfall: real start stamp when the per-call context
                # captured one (0.0 means the on_llm_start pairing was lost).
                started_at=start_time if start_time > 0 else None,
                llm_type=call_ctx.get("llm_type"),
                status="success",
            )

            # DEBUG: Confirm tokens recorded
            logger.info(
                "token_tracking_callback_tokens_recorded",
                run_id=self.run_id,
                node_name=node_name,
                duration_ms=round(duration_ms, 1),
            )

        except Exception as e:
            # Don't fail LLM call if token tracking fails
            logger.error(
                "token_tracking_callback_failed",
                run_id=self.run_id,
                llm_run_id=run_id_str,
                error=str(e),
                exc_info=True,
            )

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Record a failed call as a zero-token row.

        A failure produces no usage metadata, so without this the ledger has no
        trace that the call happened at all -- and a policy that only ever sees
        successes cannot tell a model that works from one that never answers
        (ADR-244). The row carries zero tokens and zero cost: it is an
        observation, not a charge.

        Shares ``_recorded_llm_run_ids`` with :meth:`on_llm_end`, so a run is
        recorded exactly once whichever way it ends and however many times the
        handler is attached.
        """
        run_id_str = str(run_id)
        if run_id_str in self._recorded_llm_run_ids:
            return
        self._recorded_llm_run_ids.add(run_id_str)

        call_ctx = self._call_context.pop(run_id_str, {})
        start_time = call_ctx.get("start_time", 0.0)
        duration_ms = (time.time() - start_time) * 1000 if start_time > 0 else 0.0
        failure_kind = classify_llm_error(error)

        logger.warning(
            "token_tracking_llm_error",
            run_id=self.run_id,
            llm_run_id=run_id_str,
            node_name=call_ctx.get("node_name", "unknown"),
            llm_type=call_ctx.get("llm_type"),
            failure_kind=failure_kind,
        )
        # Best-effort by design, same guard as on_llm_end: recording an
        # observation must never turn a provider failure into a second,
        # different failure for the caller.
        try:
            await self.tracker.record_node_tokens(
                node_name=call_ctx.get("node_name", "unknown"),
                model_name="unknown",
                prompt_tokens=0,
                completion_tokens=0,
                cached_tokens=0,
                duration_ms=duration_ms,
                started_at=start_time if start_time > 0 else None,
                llm_type=call_ctx.get("llm_type"),
                status="error",
                failure_kind=failure_kind,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "token_tracking_error_record_failed",
                run_id=self.run_id,
                llm_run_id=run_id_str,
                error=str(exc),
                exc_info=True,
            )
