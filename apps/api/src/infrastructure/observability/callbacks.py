"""
LangChain callbacks for observability.

Captures LLM API calls metrics (tokens, costs, latency) using LangChain's
callback system for comprehensive observability.
"""

import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from src.domains.chat.service import TrackingContext

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.exceptions import ContextOverflowError
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import LLMResult

from src.core.config import settings
from src.core.field_names import FIELD_METADATA, FIELD_MODEL_NAME
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
            # No usage found - track API call but skip token metrics
            llm_api_calls_total.labels(model="unknown", node_name=node_name, status="success").inc()
            llm_api_latency_seconds.labels(model="unknown", node_name=node_name).observe(latency)
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
            try:
                model_name = getattr(self.llm, "model_name", "unknown")
            except Exception:
                pass

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
        """
        Classify LLM API errors into standardized categories for metrics.

        Error taxonomy based on OpenAI/Anthropic/Google API error codes:
        - rate_limit: 429 Too Many Requests, quota exceeded
        - timeout: Request timeout, connection timeout
        - invalid_request: 400 Bad Request, malformed parameters
        - context_length_exceeded: Prompt exceeds model's context window
        - authentication: 401 Unauthorized, invalid API key
        - content_filter: Content policy violation (safety filters)
        - model_not_found: 404 Model not found or deprecated
        - api_error: 500+ Server errors from provider
        - unknown: Other errors

        Args:
            error: Exception from LLM API call

        Returns:
            Error type string for metrics labeling
        """
        # Type-safe check (langchain-core 1.2.10+) — takes priority over string matching
        if isinstance(error, ContextOverflowError):
            return "context_length_exceeded"

        error_type_name = type(error).__name__
        error_msg = str(error).lower()

        # OpenAI/LangChain error types
        if "RateLimitError" in error_type_name or "rate_limit" in error_msg:
            return "rate_limit"

        if "APITimeoutError" in error_type_name or "timeout" in error_msg:
            return "timeout"

        if (
            "InvalidRequestError" in error_type_name
            or "invalid_request" in error_msg
            or "bad request" in error_msg
        ):
            return "invalid_request"

        # Context length errors (various providers)
        if any(
            keyword in error_msg
            for keyword in [
                "context_length_exceeded",
                "maximum context length",
                "context window",
                "too many tokens",
                "token limit",
            ]
        ):
            return "context_length_exceeded"

        # Authentication errors
        if (
            "AuthenticationError" in error_type_name
            or "authentication" in error_msg
            or "invalid api key" in error_msg
            or "unauthorized" in error_msg
        ):
            return "authentication"

        # Content filter violations
        if any(
            keyword in error_msg
            for keyword in [
                "content_filter",
                "content policy",
                "safety",
                "responsible ai",
                "harmful content",
            ]
        ):
            return "content_filter"

        # Model not found
        if (
            "NotFoundError" in error_type_name
            or "model not found" in error_msg
            or "model does not exist" in error_msg
        ):
            return "model_not_found"

        # API errors (5xx from provider)
        if (
            "APIError" in error_type_name
            or "APIConnectionError" in error_type_name
            or "server error" in error_msg
            or "service unavailable" in error_msg
        ):
            return "api_error"

        return "unknown"


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

    def __init__(self, tracker: "TrackingContext", run_id: str) -> None:
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

    def _store_call_context(self, run_id: UUID, metadata: dict[str, Any] | None) -> None:
        """Store per-call context for parallel-safe tracking (DRY helper)."""
        self._last_usage_metadata = None
        self._call_context[str(run_id)] = {
            "node_name": (metadata or {}).get("langgraph_node", "unknown"),
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
        )

        try:
            # Extract token usage using centralized extractor (eliminates duplication)
            usage_data = TokenExtractor.extract(response)

            if not usage_data:
                logger.debug(
                    "token_tracking_no_usage",
                    run_id=self.run_id,
                    llm_run_id=run_id_str,
                    msg="No usage metadata in LLMResult",
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
