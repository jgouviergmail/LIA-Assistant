"""
LLM Response Caching for Router and Planner.

Phase 3.2.8.2: Implements deterministic LLM response caching to reduce:
- Latency: 90%+ reduction for cached queries
- Cost: Cached queries are free
- API load: Fewer calls to OpenAI/Anthropic

Architecture:
- Uses Redis for distributed caching
- Hash-based cache keys (query + context + model)
- Configurable TTL (default: 5 minutes)
- Only caches deterministic calls (temperature=0.0)

Usage:
    from src.infrastructure.cache.llm_cache import cache_llm_response

    @cache_llm_response(ttl_seconds=300)
    async def call_router_llm(query: str, history: list) -> dict:
        # ... LLM call ...
        return response

Compliance: LangGraph v1.0, async/await, type hints
"""

import asyncio
import functools
import hashlib
import json
from collections.abc import Callable
from decimal import Decimal
from functools import wraps
from typing import Any, TypeVar

import structlog
from prometheus_client import Counter
from pydantic import BaseModel

from src.core.field_names import FIELD_CONTENT, FIELD_METADATA, FIELD_MODEL_NAME, FIELD_RESULT
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

# Type variable for generic decorator
F = TypeVar("F", bound=Callable[..., Any])

# ============================================================================
# Phase 2.1 (RC4 Fix): Cache Observability Metrics
# ============================================================================

llm_cache_hits_total = Counter(
    "llm_cache_hits_total",
    "LLM cache hits by format version and usage availability",
    ["func_name", "format_version", "has_usage"],
)

llm_cache_misses_total = Counter("llm_cache_misses_total", "LLM cache misses", ["func_name"])

llm_cache_format_migration = Counter(
    "llm_cache_format_migration_total",
    "Legacy cache format hits (v1) - should decrease to 0 after migration",
    ["func_name"],
)

llm_cache_errors_total = Counter(
    "llm_cache_errors_total", "Cache operation errors", ["func_name", "error_type"]
)

# ADR-220 (ex-F4): degenerate producer results refused at the write boundary.
llm_cache_write_skipped_total = Counter(
    "llm_cache_write_skipped_total",
    "Cache writes refused because the producer result was degenerate",
    ["func_name", "reason"],
)

# Provider cost AVOIDED by a cache hit (F002). A hit performs no provider call,
# so it must NEVER increment the billed ``llm_cost_total`` / ``llm_tokens_consumed_total``
# — the avoided spend is tracked separately here.
llm_cache_cost_saved_total = Counter(
    "llm_cache_cost_saved_total",
    "Estimated provider cost avoided by LLM cache hits",
    ["node_name", "model", "currency"],
)

# Local per-key single-flight for concurrent identical calls (F002): the first
# caller runs the producer, others await the SAME task via ``asyncio.shield`` so
# the producer is invoked at most once per key and a local cancellation never
# cancels it for the others. Each task deregisters itself, so the map is bounded
# by the live key set. Not a multi-worker lock — no consumer needs cross-process
# coalescing today (the sole consumer is semantic_pivot_service).
_producer_inflight: dict[str, "asyncio.Task[Any]"] = {}


def _record_cache_error(func_name: str, exc: Exception) -> None:
    """Log and count a non-fatal cache-boundary error (read/deserialize/write)."""
    logger.error(
        "llm_cache_error",
        func=func_name,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    llm_cache_errors_total.labels(func_name=func_name, error_type=type(exc).__name__).inc()


def _finalize_producer(cache_key: str, task: "asyncio.Task[Any]") -> None:
    """Producer-owned single-flight finalisation (F002).

    Runs when the producer task completes — regardless of whether the initiating
    caller survived. Ownership of the cleanup belongs to the PRODUCER, never to
    the initiating caller: if the initiator is cancelled while the producer is
    still running, the entry must stay so late callers coalesce onto the same
    task instead of starting a second producer (stampede / double LLM cost).

    Deregisters THIS task only when it is still the registered one (identity
    check, so a key already re-registered by a later producer is never
    clobbered), then retrieves the exception so an abandoned task (all waiters
    cancelled) does not warn 'exception was never retrieved'.
    """
    if _producer_inflight.get(cache_key) is task:
        del _producer_inflight[cache_key]
    if not task.cancelled():
        task.exception()


class CacheJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for cache values.

    Phase 2.1 (RC4 Fix): Handles Pydantic models, Decimal, datetime objects
    that are commonly used in LLM responses (RouterOutput, costs, etc.).

    Purpose:
        - Pydantic models (RouterOutput, PlannerOutput) → dict
        - Decimal (from cost calculations) → float
        - datetime/date → ISO format string
        - Fallback to default encoder

    Example:
        >>> cache_value = {"result": RouterOutput(...), "cost": Decimal("0.01")}
        >>> json.dumps(cache_value, cls=CacheJSONEncoder)
        '{"result": {...}, "cost": 0.01}'
    """

    def default(self, obj: Any) -> Any:
        """Override default serialization for custom types."""
        # Pydantic models - use JSON-safe mode
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")

        # Decimal (from cost calculations)
        if isinstance(obj, Decimal):
            return float(obj)

        # Datetime objects - ISO format
        if hasattr(obj, "isoformat"):
            return obj.isoformat()

        # Fallback to default encoder (raises TypeError if not serializable)
        return super().default(obj)


def _generate_cache_key(
    func_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    user_id: str | None = None,
) -> str:
    """
    Generate deterministic cache key from function name, arguments, and user context.

    Uses SHA256 hash of JSON-serialized arguments for:
    - Determinism: Same inputs → same key
    - Collision resistance: Different inputs → different keys
    - Compactness: Fixed 64-char hex string
    - User isolation: Cache is scoped per user when user_id provided

    Phase 6 - LLM Observability: Excludes 'config' parameter from cache key.
    - RunnableConfig contains non-serializable objects (callbacks, connections)
    - Config is for observability/metadata, NOT for caching logic
    - Ensures cache hit rate is unaffected by callback injection

    Phase 8 - Multi-user Cache Isolation (2025-12-29):
    - Includes user_id in cache key when available
    - Prevents cache pollution between different users
    - CRITICAL for multi-user deployments

    Args:
        func_name: Name of the cached function
        args: Positional arguments
        kwargs: Keyword arguments (config excluded automatically)
        user_id: Optional user identifier for cache isolation

    Returns:
        Cache key in format: "llm_cache:{func_name}:{user_id}:{hash}" or
                            "llm_cache:{func_name}:global:{hash}" if no user_id

    Example:
        >>> _generate_cache_key("router", ("hello",), {"model": "gpt-4"}, user_id="user123")
        "llm_cache:router:user123:a1b2c3..."
    """
    # Phase 6: Exclude 'config' from cache key (observability metadata)
    # This prevents serialization errors and preserves cache hit rate
    cache_kwargs = {k: v for k, v in kwargs.items() if k != "config"}

    # Build canonical representation
    canonical = {
        "func": func_name,
        "args": [_serialize_arg(arg) for arg in args],
        "kwargs": {k: _serialize_arg(v) for k, v in sorted(cache_kwargs.items())},
    }

    # Phase 8: Include user_id in canonical representation for isolation
    # FIX 2025-12-29: Convert to string (user_id is UUID, not JSON serializable)
    if user_id:
        canonical["user_id"] = str(user_id)

    # Hash for compactness and privacy (don't expose user data in keys)
    canonical_json = json.dumps(canonical, sort_keys=True, ensure_ascii=True)
    hash_digest = hashlib.sha256(canonical_json.encode()).hexdigest()

    # Include user_id in key prefix for easier debugging and cache management
    user_scope = user_id if user_id else "global"
    return f"llm_cache:{func_name}:{user_scope}:{hash_digest}"


def _serialize_arg(arg: Any) -> Any:
    """
    Serialize argument to JSON-compatible format.

    Handles:
    - UUID → string (FIX 2025-12-29: prevents JSON serialization errors)
    - Pydantic models → dict (recursively serialized)
    - LangChain messages → safe dict (content + type only)
    - Dataclasses → safe dict conversion (prevents psycopg PGconn errors)
    - Custom objects → repr() or str()
    - Iterables → lists
    - Primitives → as-is

    Args:
        arg: Argument to serialize

    Returns:
        JSON-serializable representation

    Note:
        Phase 6 - Uses safe dataclass conversion to prevent
        "no default __reduce__ due to non-trivial __cinit__" errors
        from psycopg connections embedded in LangChain objects.
    """
    # FIX 2025-12-29: Handle UUID explicitly (not JSON serializable by default)
    # This fixes "Object of type UUID is not JSON serializable" errors
    from uuid import UUID

    if isinstance(arg, UUID):
        return str(arg)

    # Pydantic models - recursively serialize the resulting dict
    # FIX 2025-12-29: model_dump() can return UUIDs, so we must serialize recursively
    if hasattr(arg, "model_dump"):
        return _serialize_arg(arg.model_dump())

    # LangChain BaseMessage - serialize only content and type (skip additional_kwargs, response_metadata)
    # This prevents serialization of nested State/Store references.
    # Use BaseMessage.text (LangChain Core 1.2+) when available so Gemini 3.x
    # list[dict] content blocks serialize as their concatenated text instead of
    # the Python repr — otherwise cache keys differ between provider versions
    # for semantically identical messages.
    if hasattr(arg, "content") and hasattr(arg, "type"):
        text_repr = str(arg.text) if hasattr(arg, "text") else str(arg.content)
        return {
            "type": arg.type,
            FIELD_CONTENT: text_repr,
        }

    # Dataclasses - SAFE conversion (Phase 6 fix for psycopg PGconn errors)
    if hasattr(arg, "__dataclass_fields__"):
        from dataclasses import fields

        # Instead of asdict() which does deepcopy, manually convert fields
        # This avoids triggering __reduce__ on non-serializable objects
        try:
            result = {}
            for field in fields(arg):
                value = getattr(arg, field.name)
                # Recursively serialize, but skip non-serializable objects gracefully
                try:
                    result[field.name] = _serialize_arg(value)
                except (TypeError, AttributeError, ValueError):
                    # Skip fields that can't be serialized (e.g., PGconn)
                    result[field.name] = f"<non-serializable: {type(value).__name__}>"
            return result
        except Exception as e:
            # Fallback: use str() representation if field extraction fails
            logger.warning(
                "dataclass_serialization_fallback",
                arg_type=type(arg).__name__,
                error=str(e),
            )
            return str(arg)

    # Lists, tuples, sets
    if isinstance(arg, list | tuple | set):
        return [_serialize_arg(item) for item in arg]

    # Dicts
    if isinstance(arg, dict):
        return {k: _serialize_arg(v) for k, v in arg.items()}

    # Primitives (str, int, float, bool, None)
    if isinstance(arg, str | int | float | bool | type(None)):
        return arg

    # Fallback: string representation
    return str(arg)


async def _record_cache_hit_metrics(
    usage_metadata: dict[str, Any],
    node_name: str,
) -> None:
    """
    Record the provider cost AVOIDED by a cache hit (F002).

    A hit issues no provider call, so this only increments
    ``llm_cache_cost_saved_total`` — never the billed ``llm_cost_total`` or
    ``llm_tokens_consumed_total`` (which must reflect real provider consumption,
    i.e. cache misses whose LLM callbacks record them). Callbacks are not
    replayed here (``on_llm_end`` is not guaranteed idempotent; cache hits are
    intentionally absent from Langfuse traces).

    Args:
        usage_metadata: Cached usage data (tokens, model_name)
        node_name: Node name for metrics labeling

    Example:
        >>> await _record_cache_hit_metrics(
        ...     usage_metadata={"input_tokens": 100, "output_tokens": 50, "model_name": "gpt-4"},
        ...     node_name="router"
        ... )
    """
    from src.core.config import settings
    from src.infrastructure.observability.metrics_agents import estimate_cost_usd

    model_name = usage_metadata.get(FIELD_MODEL_NAME, "unknown")
    input_tokens = usage_metadata.get("input_tokens", 0)
    output_tokens = usage_metadata.get("output_tokens", 0)
    cached_tokens = usage_metadata.get("cached_tokens", 0)

    # A cache hit performs NO provider call: it must never touch the billed
    # ``llm_cost_total`` / ``llm_tokens_consumed_total`` counters (F002 — those
    # inflated the reported spend). Record only the cost it AVOIDED.
    cost_saved = await estimate_cost_usd(
        model=model_name,
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        cached_tokens=cached_tokens,
    )

    currency = settings.default_currency.upper()
    llm_cache_cost_saved_total.labels(
        node_name=node_name,
        model=model_name,
        currency=currency,
    ).inc(cost_saved)

    logger.debug(
        "cache_hit_cost_saved_recorded",
        node_name=node_name,
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cost_saved=cost_saved,
        currency=currency,
    )


async def _return_cached_result(
    cached_value: str | bytes,
    func_name: str,
    cache_key: str,
    user_id: Any,
    kwargs: dict[str, Any],
) -> Any:
    """Deserialize a cache entry, record hit metrics, and return the result.

    Raises on a corrupt/partial entry so the caller falls through to a recompute
    (the cache-hit boundary), never to a second producer call.
    """
    cached_data = json.loads(cached_value)
    if isinstance(cached_data, dict) and FIELD_METADATA in cached_data:
        result = cached_data[FIELD_RESULT]
        usage_metadata = cached_data[FIELD_METADATA].get("usage")
        format_version = cached_data[FIELD_METADATA].get("version", 2)
        logger.info(
            "llm_cache_hit",
            func=func_name,
            cache_key=cache_key[:50],
            format_version=format_version,
            has_usage=usage_metadata is not None,
            user_scope=user_id if user_id else "global",
        )
        llm_cache_hits_total.labels(
            func_name=func_name,
            format_version=str(format_version),
            has_usage=str(usage_metadata is not None),
        ).inc()
        if usage_metadata:
            config = kwargs.get("config")
            node_name = (
                config.get(FIELD_METADATA, {}).get("langgraph_node")
                if config
                else func_name.replace("_call_", "").replace("_llm", "")
            )
            await _record_cache_hit_metrics(usage_metadata=usage_metadata, node_name=node_name)
    else:
        result = cached_data
        logger.info(
            "llm_cache_hit",
            func=func_name,
            cache_key=cache_key[:50],
            format_version=1,
            has_usage=False,
            user_scope=user_id if user_id else "global",
        )
        llm_cache_hits_total.labels(
            func_name=func_name, format_version="1", has_usage="False"
        ).inc()
        llm_cache_format_migration.labels(func_name=func_name).inc()
    return result


async def _store_cached_result(
    redis: Any,
    cache_key: str,
    result: Any,
    ttl_seconds: int,
    func_name: str,
    user_id: Any,
    kwargs: dict[str, Any],
) -> None:
    """Serialize + store a producer result as a v2 cache entry.

    A non-serializable result is logged and skipped (never a corrupt entry).
    A Redis write error propagates to the caller's write boundary — which
    returns the already-computed result rather than re-running the producer.
    """
    import time

    # ADR-220 (ex-F4): never memorize a degenerate result. An empty LLM
    # completion (content filter, output budget consumed by reasoning) used to
    # be cached verbatim and replayed for the full TTL — the semantic pivot
    # then served "" as "the intent in English" for 5 minutes. The boundary is
    # deliberate: None and blank STRINGS are a completion that produced
    # nothing; empty containers ([], {}) are legitimate negatives ("no
    # entities found") and stay cacheable.
    if result is None or (isinstance(result, str) and not result.strip()):
        llm_cache_write_skipped_total.labels(func_name=func_name, reason="empty_result").inc()
        logger.warning(
            "llm_cache_write_skipped",
            func=func_name,
            reason="empty_result",
            result_type=type(result).__name__,
        )
        return

    usage_metadata = None
    config = kwargs.get("config")
    if config and "callbacks" in config:
        for callback in config.get("callbacks", []):
            if hasattr(callback, "_last_usage_metadata"):
                usage_metadata = callback._last_usage_metadata
                callback._last_usage_metadata = None  # clear to prevent reuse
                break

    cache_value = {
        FIELD_RESULT: result,
        FIELD_METADATA: {"version": 2, "cached_at": time.time(), "usage": usage_metadata},
    }
    try:
        serialized = json.dumps(cache_value, cls=CacheJSONEncoder, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        logger.error(
            "llm_cache_serialization_failed",
            func=func_name,
            error=str(exc),
            result_type=type(result).__name__,
            exc_info=True,
        )
        llm_cache_errors_total.labels(func_name=func_name, error_type="serialization_failed").inc()
        return

    await redis.set(cache_key, serialized, ex=ttl_seconds)
    logger.info(
        "llm_cache_stored",
        func=func_name,
        cache_key=cache_key[:50],
        ttl_seconds=ttl_seconds,
        format_version=2,
        has_usage=usage_metadata is not None,
        user_scope=user_id if user_id else "global",
    )


def cache_llm_response(
    ttl_seconds: int = 300,
    enabled: bool = True,
) -> Callable[[F], F]:
    """
    Decorator to cache LLM responses in Redis.

    IMPORTANT: Only use on deterministic LLM calls (temperature=0.0).
    Non-deterministic calls should NOT be cached as it breaks randomness.

    Args:
        ttl_seconds: Time-to-live in seconds (default: 300 = 5 minutes)
        enabled: Enable/disable caching (default: True, can use env var)

    Returns:
        Decorator function

    Example:
        >>> @cache_llm_response(ttl_seconds=600)
        >>> async def classify_intent(query: str, model: str = "gpt-4") -> dict:
        >>>     # ... LLM call with temperature=0.0 ...
        >>>     return {"intent": "search", "confidence": 0.95}

        First call: Cache MISS → calls LLM → caches result → returns
        Second call (same args): Cache HIT → returns cached → saves 2s + $0.02

    Cache Hit Performance:
        - Latency: ~5ms (Redis) vs ~2000ms (LLM API)
        - Cost: $0 vs ~$0.01-$0.05 per call
        - ROI: Massive for repeated queries

    Thread Safety:
        - Safe for concurrent access (Redis atomic operations)
        - No cache stampede: a local per-key single-flight coalesces concurrent
          identical calls onto ONE producer invocation; the others await it via
          ``asyncio.shield``, so a caller's cancellation never cancels the shared
          producer (F002). This is in-process only (no cross-worker lock).
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Skip caching if disabled
            if not enabled:
                logger.debug("llm_cache_disabled", func=func.__name__)
                return await func(*args, **kwargs)

            # Extract user_id from config for cache isolation (LangGraph pattern:
            # config["configurable"]["user_id"]).
            config = kwargs.get("config")
            user_id = None
            if config and isinstance(config, dict):
                configurable = config.get("configurable", {})
                if isinstance(configurable, dict):
                    user_id = configurable.get("user_id")
            cache_key = _generate_cache_key(func.__name__, args, kwargs, user_id=user_id)

            # === READ boundary: a Redis read error degrades to a miss (never a
            # second producer call) and disables the later write. ===
            redis = None
            cached_value = None
            try:
                redis = await get_redis_cache()
                cached_value = await redis.get(cache_key)
            except Exception as read_err:  # noqa: BLE001 — a cache read must not break the call
                _record_cache_error(func.__name__, read_err)
                redis = None

            # === HIT boundary: a corrupt/partial entry falls through to a miss. ===
            if cached_value:
                try:
                    return await _return_cached_result(
                        cached_value, func.__name__, cache_key, user_id, kwargs
                    )
                except Exception as hit_err:  # noqa: BLE001 — bad entry → recompute, don't crash
                    _record_cache_error(func.__name__, hit_err)

            # === MISS ===
            logger.info(
                "llm_cache_miss",
                func=func.__name__,
                cache_key=cache_key[:50],
                user_scope=user_id if user_id else "global",
            )
            llm_cache_misses_total.labels(func_name=func.__name__).inc()

            # === PRODUCER boundary: single-flight — the producer runs AT MOST
            # ONCE per key; its exception propagates UNCHANGED (no silent retry).
            # Concurrent identical callers coalesce onto the same task; a local
            # cancellation cannot cancel it for the others (asyncio.shield). ===
            inflight = _producer_inflight.get(cache_key)
            is_initiator = inflight is None
            if inflight is None:
                inflight = asyncio.create_task(func(*args, **kwargs))
                _producer_inflight[cache_key] = inflight
                # Cleanup is owned by the PRODUCER task, not the initiating
                # caller (F002): the entry lives until the producer finishes, so
                # an initiator cancelled mid-flight never orphans it.
                inflight.add_done_callback(functools.partial(_finalize_producer, cache_key))
            result = await asyncio.shield(inflight)

            # === WRITE boundary: only the initiator writes (one producer → one
            # write); a write error returns the already-computed result. ===
            if is_initiator and redis is not None:
                try:
                    await _store_cached_result(
                        redis, cache_key, result, ttl_seconds, func.__name__, user_id, kwargs
                    )
                except (
                    Exception
                ) as write_err:  # noqa: BLE001 — a write error must not lose the result
                    _record_cache_error(func.__name__, write_err)

            return result

        return wrapper  # type: ignore

    return decorator


async def invalidate_llm_cache(pattern: str = "llm_cache:*") -> int:
    """
    Invalidate LLM cache entries matching pattern.

    Useful for:
    - Clearing cache after model updates
    - Removing stale entries manually
    - Testing/debugging

    Args:
        pattern: Redis key pattern (default: all LLM cache)

    Returns:
        Number of keys deleted

    Example:
        >>> # Clear all router cache
        >>> await invalidate_llm_cache("llm_cache:router:*")

        >>> # Clear all LLM cache
        >>> await invalidate_llm_cache("llm_cache:*")

    Warning:
        Use with caution - invalidating cache increases costs and latency.
    """
    try:
        redis = await get_redis_cache()

        # Find all matching keys
        keys = []
        async for key in redis.scan_iter(match=pattern):
            keys.append(key)

        if not keys:
            logger.info("llm_cache_invalidate_no_keys", pattern=pattern)
            return 0

        # Delete in batches (avoid blocking Redis)
        deleted_count = 0
        batch_size = 100

        for i in range(0, len(keys), batch_size):
            batch = keys[i : i + batch_size]
            deleted = await redis.delete(*batch)
            deleted_count += deleted

        logger.info(
            "llm_cache_invalidated",
            pattern=pattern,
            deleted_count=deleted_count,
        )

        return deleted_count

    except Exception as e:
        logger.error(
            "llm_cache_invalidate_error",
            pattern=pattern,
            error=str(e),
            exc_info=True,
        )
        return 0


__all__ = [
    "cache_llm_response",
    "invalidate_llm_cache",
]
