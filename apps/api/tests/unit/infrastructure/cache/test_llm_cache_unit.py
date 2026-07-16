"""
Unit tests for llm_cache.py internal functions.

Tests coverage for:
- _serialize_arg (dataclasses, LangChain messages, collections, fallbacks)
- _generate_cache_key (config exclusion, determinism, collision resistance)
- _record_cache_hit_metrics (token metrics, cost estimation)
- invalidate_llm_cache (batch deletion, pattern matching, error handling)

Phase 4.1 - Coverage Baseline & Tests Unitaires
Target: 80%+ coverage for infrastructure/cache/llm_cache.py
"""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import REGISTRY

from src.infrastructure.cache.llm_cache import (
    _generate_cache_key,
    _record_cache_hit_metrics,
    _serialize_arg,
    invalidate_llm_cache,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@dataclass
class SimpleDataclass:
    """Simple dataclass for testing."""

    name: str
    value: int


@dataclass
class DataclassWithNonSerializable:
    """Dataclass containing non-serializable field (simulates PGconn)."""

    id: str
    connection: object  # Non-serializable object


class MockLangChainMessage:
    """Mock LangChain BaseMessage for testing."""

    def __init__(self, content: str, msg_type: str = "human"):
        self.content = content
        self.type = msg_type
        self.additional_kwargs = {}
        self.response_metadata = {}


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset Prometheus metrics before each test to avoid pollution."""
    for collector in list(REGISTRY._collector_to_names.keys()):
        try:
            if hasattr(collector, "_metrics"):
                collector._metrics.clear()
        except Exception:
            pass
    yield


# ============================================================================
# _serialize_arg - Unit Tests
# ============================================================================


def test_serialize_arg_langchain_message():
    """
    Test serialization of LangChain BaseMessage.

    Validates:
    - Only content and type are extracted
    - additional_kwargs and response_metadata are excluded
    - Content is converted to string
    """
    message = MockLangChainMessage(content="Hello world", msg_type="human")

    result = _serialize_arg(message)

    assert result == {"type": "human", "content": "Hello world"}
    assert "additional_kwargs" not in result
    assert "response_metadata" not in result


def test_serialize_arg_dataclass_success():
    """
    Test successful dataclass serialization.

    Validates:
    - Dataclass fields are extracted correctly
    - Field values are recursively serialized
    """
    obj = SimpleDataclass(name="test", value=42)

    result = _serialize_arg(obj)

    assert result == {"name": "test", "value": 42}
    assert isinstance(result, dict)


def test_serialize_arg_dataclass_with_non_serializable_field():
    """
    Test dataclass with non-serializable field (e.g., PGconn).

    Scenario:
    - Dataclass contains an object whose str() raises (the safe conversion
      never calls __reduce__, so the failure surfaces at the str() fallback)
    - Should gracefully replace the field with a placeholder

    Validates: Graceful handling of psycopg PGconn-like errors
    """

    class NonSerializable:
        """Object that simulates PGconn - can't be serialized."""

        def __str__(self):
            raise TypeError("no default __reduce__ due to non-trivial __cinit__")

    obj = DataclassWithNonSerializable(id="test-123", connection=NonSerializable())

    result = _serialize_arg(obj)

    assert result["id"] == "test-123"
    assert "non-serializable" in result["connection"].lower()


def test_serialize_arg_dataclass_extraction_error_fallback():
    """
    Test dataclass field extraction failure fallback.

    Scenario:
    - Field extraction raises exception
    - Should fallback to str() representation

    Validates: Fallback mechanism for broken dataclasses
    """

    @dataclass
    class BrokenDataclass:
        """Dataclass that raises error during field access."""

        value: int

        def __getattribute__(self, name):
            if name == "value":
                raise AttributeError("Simulated broken field")
            return super().__getattribute__(name)

        def __repr__(self) -> str:
            # The default dataclass repr reads self.value and would raise
            # inside the str() fallback — keep it safe so the fallback path
            # itself is what gets exercised.
            return "BrokenDataclass(value=<broken>)"

    obj = BrokenDataclass(value=42)

    # Should fallback to str() without crashing
    result = _serialize_arg(obj)

    assert isinstance(result, str)
    assert result == "BrokenDataclass(value=<broken>)"


def test_serialize_arg_list_tuple_set():
    """
    Test serialization of list, tuple, set collections.

    Validates:
    - Lists are preserved
    - Tuples are converted to lists
    - Sets are converted to lists
    - Nested items are recursively serialized
    """
    test_list = [1, 2, "test", SimpleDataclass(name="item", value=1)]
    test_tuple = (1, 2, 3)
    test_set = {1, 2, 3}

    # List
    result_list = _serialize_arg(test_list)
    assert len(result_list) == 4
    assert result_list[0] == 1
    assert result_list[3] == {"name": "item", "value": 1}

    # Tuple
    result_tuple = _serialize_arg(test_tuple)
    assert result_tuple == [1, 2, 3]

    # Set
    result_set = _serialize_arg(test_set)
    assert len(result_set) == 3
    assert all(x in result_set for x in [1, 2, 3])


def test_serialize_arg_dict():
    """
    Test dict serialization with recursive value handling.

    Validates:
    - Dict keys preserved
    - Values recursively serialized
    - Nested structures handled
    """
    test_dict = {
        "simple": "value",
        "nested": {"key": SimpleDataclass(name="nested", value=99)},
        "list": [1, 2, 3],
    }

    result = _serialize_arg(test_dict)

    assert result["simple"] == "value"
    assert result["nested"]["key"] == {"name": "nested", "value": 99}
    assert result["list"] == [1, 2, 3]


def test_serialize_arg_primitives():
    """
    Test that primitives pass through unchanged.

    Validates: str, int, float, bool, None handling
    """
    assert _serialize_arg("test") == "test"
    assert _serialize_arg(42) == 42
    assert _serialize_arg(3.14) == 3.14
    assert _serialize_arg(True) is True
    assert _serialize_arg(None) is None


def test_serialize_arg_fallback_to_str():
    """
    Test fallback to str() for unknown object types.

    Validates: Custom objects converted to string representation
    """

    class CustomClass:
        """Custom class without serialization support."""

        def __str__(self):
            return "CustomClass instance"

    obj = CustomClass()
    result = _serialize_arg(obj)

    assert result == "CustomClass instance"


# ============================================================================
# _generate_cache_key - Unit Tests
# ============================================================================


def test_generate_cache_key_excludes_config():
    """
    Test that 'config' parameter is excluded from cache key.

    Scenario:
    - Same function + args + kwargs (except config)
    - Different config values
    - Should produce SAME cache key

    Validates: Phase 6 fix - config exclusion for observability
    """
    func_name = "test_func"
    args = ("arg1",)
    kwargs1 = {"param": "value", "config": {"callbacks": [1, 2, 3]}}
    kwargs2 = {"param": "value", "config": {"callbacks": [4, 5, 6]}}

    key1 = _generate_cache_key(func_name, args, kwargs1)
    key2 = _generate_cache_key(func_name, args, kwargs2)

    # Keys should be identical (config excluded)
    assert key1 == key2


def test_generate_cache_key_deterministic():
    """
    Test that same inputs produce same cache key.

    Validates: Determinism requirement
    """
    func_name = "test_func"
    args = ("query", "model")
    kwargs = {"temperature": 0.0, "max_tokens": 100}

    key1 = _generate_cache_key(func_name, args, kwargs)
    key2 = _generate_cache_key(func_name, args, kwargs)

    assert key1 == key2
    assert key1.startswith("llm_cache:test_func:")


def test_generate_cache_key_collision_resistant():
    """
    Test that different inputs produce different cache keys.

    Validates: Collision resistance via SHA256
    """
    func_name = "test_func"

    # Different args
    key1 = _generate_cache_key(func_name, ("query1",), {})
    key2 = _generate_cache_key(func_name, ("query2",), {})
    assert key1 != key2

    # Different kwargs
    key3 = _generate_cache_key(func_name, (), {"model": "gpt-4"})
    key4 = _generate_cache_key(func_name, (), {"model": "gpt-3.5"})
    assert key3 != key4

    # Different function names
    key5 = _generate_cache_key("func1", ("arg",), {})
    key6 = _generate_cache_key("func2", ("arg",), {})
    assert key5 != key6


def test_generate_cache_key_handles_complex_args():
    """
    Test cache key generation with complex argument types.

    Validates: Serialization of nested structures in cache key
    """
    func_name = "complex_func"
    args = (SimpleDataclass(name="test", value=42),)
    kwargs = {"messages": [{"role": "user", "content": "hello"}], "config": {"skip": "me"}}

    key = _generate_cache_key(func_name, args, kwargs)

    # Should generate valid key without errors
    assert key.startswith("llm_cache:complex_func:")
    assert len(key) > 50  # SHA256 hash is 64 chars


# ============================================================================
# _record_cache_hit_metrics - Unit Tests
# ============================================================================


@pytest.mark.asyncio
async def test_record_cache_hit_records_cost_saved_never_billed():
    """F002: a hit records the AVOIDED cost and NEVER the billed cost/consumption.

    A cache hit issues no provider call, so the billed ``llm_cost_total`` and
    ``llm_tokens_consumed_total`` counters must stay untouched — only the
    ``llm_cache_cost_saved_total`` counter moves.
    """
    usage_metadata = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cached_tokens": 0,
        "model_name": "gpt-4.1-mini",
    }

    with (
        patch(
            "src.infrastructure.observability.metrics_agents.estimate_cost_usd",
            new=AsyncMock(return_value=0.0025),
        ),
        patch("src.infrastructure.cache.llm_cache.llm_cache_cost_saved_total") as mock_saved,
        patch("src.infrastructure.observability.metrics_agents.llm_cost_total") as mock_billed,
        patch(
            "src.infrastructure.observability.metrics_agents.llm_tokens_consumed_total"
        ) as mock_tokens,
        patch("src.core.config.settings") as mock_settings,
    ):
        mock_settings.default_currency = "eur"

        await _record_cache_hit_metrics(usage_metadata, node_name="router")

    mock_saved.labels.assert_called_once_with(
        node_name="router", model="gpt-4.1-mini", currency="EUR"
    )
    mock_saved.labels.return_value.inc.assert_called_once_with(0.0025)
    # A hit must NEVER move the billed provider counters.
    mock_billed.labels.assert_not_called()
    mock_tokens.labels.assert_not_called()


@pytest.mark.asyncio
async def test_record_cache_hit_estimates_saved_cost_with_token_counts():
    """The avoided cost is estimated from the cached token counts."""
    usage_metadata = {
        "input_tokens": 200,
        "output_tokens": 100,
        "cached_tokens": 50,
        "model_name": "gpt-4.1-mini",
    }

    mock_estimate = AsyncMock(return_value=0.01)
    with (
        patch(
            "src.infrastructure.observability.metrics_agents.estimate_cost_usd",
            new=mock_estimate,
        ),
        patch("src.infrastructure.cache.llm_cache.llm_cache_cost_saved_total"),
    ):
        await _record_cache_hit_metrics(usage_metadata, node_name="test_node")

    mock_estimate.assert_awaited_once_with(
        model="gpt-4.1-mini",
        prompt_tokens=200,
        completion_tokens=100,
        cached_tokens=50,
    )


@pytest.mark.asyncio
async def test_record_cache_hit_zero_tokens_records_zero_saved():
    """A zero-token cached entry still records a 0.0 saved-cost sample."""
    usage_metadata = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "model_name": "gpt-4.1-mini",
    }

    with (
        patch(
            "src.infrastructure.observability.metrics_agents.estimate_cost_usd",
            new=AsyncMock(return_value=0.0),
        ),
        patch("src.infrastructure.cache.llm_cache.llm_cache_cost_saved_total") as mock_saved,
    ):
        await _record_cache_hit_metrics(usage_metadata, node_name="test_node")

    mock_saved.labels.return_value.inc.assert_called_once_with(0.0)


# ============================================================================
# invalidate_llm_cache - Unit Tests
# ============================================================================


@pytest.mark.asyncio
async def test_invalidate_llm_cache_single_key():
    """
    Test deleting single cache key.

    Validates:
    - scan_iter finds matching key
    - delete called with correct key
    - Returns correct count
    """
    mock_redis = MagicMock()

    async def mock_scan_iter(match):
        """Mock scan_iter that yields one key."""
        yield "llm_cache:test_func:abc123"

    mock_redis.scan_iter = mock_scan_iter
    mock_redis.delete = AsyncMock(return_value=1)

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        count = await invalidate_llm_cache("llm_cache:test_func:*")

        assert count == 1
        mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_llm_cache_batch_deletion():
    """
    Test batch deletion of many keys (>100 keys).

    Validates:
    - Keys deleted in batches of 100
    - Multiple delete calls for large sets
    - Correct total count returned
    """
    mock_redis = MagicMock()

    # Generate 150 keys
    async def mock_scan_iter(match):
        """Mock scan_iter that yields 150 keys."""
        for i in range(150):
            yield f"llm_cache:test:{i}"

    mock_redis.scan_iter = mock_scan_iter
    mock_redis.delete = AsyncMock(return_value=100)  # Returns count per batch

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        count = await invalidate_llm_cache("llm_cache:test:*")

        # Should be called twice (batch_size=100)
        assert mock_redis.delete.call_count == 2
        # Total count = 200 (100 per batch, 2 batches)
        assert count == 200


@pytest.mark.asyncio
async def test_invalidate_llm_cache_no_keys_found():
    """
    Test invalidation when no keys match pattern.

    Validates:
    - Returns 0 when no keys found
    - delete not called
    - Logs info message
    """
    mock_redis = MagicMock()

    async def mock_scan_iter(match):
        """Mock scan_iter that yields no keys."""
        return
        yield  # Make this an async generator

    mock_redis.scan_iter = mock_scan_iter
    mock_redis.delete = AsyncMock()

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        count = await invalidate_llm_cache("llm_cache:nonexistent:*")

        assert count == 0
        mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_invalidate_llm_cache_with_pattern():
    """
    Test invalidation with specific pattern.

    Validates:
    - Pattern passed to scan_iter correctly
    - Only matching keys deleted
    """
    mock_redis = MagicMock()

    async def mock_scan_iter(match):
        """Mock scan_iter that respects pattern."""
        if "router" in match:
            yield "llm_cache:router:key1"
            yield "llm_cache:router:key2"

    mock_redis.scan_iter = mock_scan_iter
    mock_redis.delete = AsyncMock(return_value=2)

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        count = await invalidate_llm_cache("llm_cache:router:*")

        assert count == 2


@pytest.mark.asyncio
async def test_invalidate_llm_cache_redis_error():
    """
    Test error handling when Redis operation fails.

    Validates:
    - Exception caught gracefully
    - Returns 0 on error
    - Error logged
    """
    mock_redis = MagicMock()
    mock_redis.scan_iter = MagicMock(side_effect=Exception("Redis connection error"))

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        count = await invalidate_llm_cache("llm_cache:*")

        # Should return 0 on error (graceful degradation)
        assert count == 0


@pytest.mark.asyncio
async def test_invalidate_llm_cache_default_pattern():
    """
    Test default pattern matches all LLM cache keys.

    Validates: Default pattern is "llm_cache:*"
    """
    mock_redis = MagicMock()

    async def mock_scan_iter(match):
        """Verify default pattern."""
        assert match == "llm_cache:*"
        yield "llm_cache:func1:key1"
        yield "llm_cache:func2:key2"

    mock_redis.scan_iter = mock_scan_iter
    mock_redis.delete = AsyncMock(return_value=2)

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        count = await invalidate_llm_cache()  # No pattern specified

        assert count == 2


# ============================================================================
# cache_llm_response wrapper - error boundaries & single-flight (F002)
# ============================================================================


def _mock_redis(get_return=None):
    r = AsyncMock()
    r.get.return_value = get_return
    return r


@pytest.mark.asyncio
async def test_producer_called_once_and_propagates_when_it_raises():
    """F002: a failing producer runs AT MOST ONCE and its exception propagates."""
    from src.infrastructure.cache.llm_cache import cache_llm_response

    calls = {"n": 0}

    @cache_llm_response(ttl_seconds=60)
    async def producer(x: str) -> dict:
        calls["n"] += 1
        raise RuntimeError("LLM down")

    redis = _mock_redis(get_return=None)  # miss
    with patch(
        "src.infrastructure.cache.llm_cache.get_redis_cache",
        new=AsyncMock(return_value=redis),
    ):
        with pytest.raises(RuntimeError, match="LLM down"):
            await producer("q")

    assert calls["n"] == 1  # never a silent second call (the old except → re-call bug)


@pytest.mark.asyncio
async def test_write_error_returns_result_without_recompute():
    """F002: a Redis write error returns the computed result, never re-runs producer."""
    from src.infrastructure.cache.llm_cache import cache_llm_response

    calls = {"n": 0}

    @cache_llm_response(ttl_seconds=60)
    async def producer(x: str) -> dict:
        calls["n"] += 1
        return {"ok": True}

    redis = _mock_redis(get_return=None)
    redis.set.side_effect = RuntimeError("redis write down")
    with patch(
        "src.infrastructure.cache.llm_cache.get_redis_cache",
        new=AsyncMock(return_value=redis),
    ):
        result = await producer("q")

    assert result == {"ok": True}
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_read_error_degrades_to_single_producer_call():
    """F002: a Redis read error is treated as a miss — producer runs exactly once."""
    from src.infrastructure.cache.llm_cache import cache_llm_response

    calls = {"n": 0}

    @cache_llm_response(ttl_seconds=60)
    async def producer(x: str) -> dict:
        calls["n"] += 1
        return {"ok": 1}

    redis = AsyncMock()
    redis.get.side_effect = RuntimeError("redis read down")
    with patch(
        "src.infrastructure.cache.llm_cache.get_redis_cache",
        new=AsyncMock(return_value=redis),
    ):
        result = await producer("q")

    assert result == {"ok": 1}
    assert calls["n"] == 1
    redis.set.assert_not_awaited()  # read failed → redis disabled → no write attempt


@pytest.mark.asyncio
async def test_concurrent_identical_calls_are_single_flight():
    """F002: 20 concurrent identical calls coalesce onto ONE producer invocation."""
    from src.infrastructure.cache.llm_cache import cache_llm_response

    calls = {"n": 0}
    release = asyncio.Event()

    @cache_llm_response(ttl_seconds=60)
    async def producer(x: str) -> dict:
        calls["n"] += 1
        await release.wait()
        return {"v": 1}

    redis = _mock_redis(get_return=None)
    with patch(
        "src.infrastructure.cache.llm_cache.get_redis_cache",
        new=AsyncMock(return_value=redis),
    ):
        tasks = [asyncio.create_task(producer("q")) for _ in range(20)]
        for _ in range(4):
            await asyncio.sleep(0)  # let all callers reach the single-flight join
        release.set()
        results = await asyncio.gather(*tasks)

    assert all(r == {"v": 1} for r in results)
    assert calls["n"] == 1  # single-flight: one producer for 20 callers (no stampede)


@pytest.mark.asyncio
async def test_waiter_cancellation_does_not_kill_shared_producer():
    """F002: cancelling one caller must not cancel the shared producer for others."""
    from src.infrastructure.cache.llm_cache import cache_llm_response

    calls = {"n": 0}
    release = asyncio.Event()

    @cache_llm_response(ttl_seconds=60)
    async def producer(x: str) -> dict:
        calls["n"] += 1
        await release.wait()
        return {"v": 2}

    redis = _mock_redis(get_return=None)
    with patch(
        "src.infrastructure.cache.llm_cache.get_redis_cache",
        new=AsyncMock(return_value=redis),
    ):
        initiator = asyncio.create_task(producer("q"))
        await asyncio.sleep(0)
        joiner = asyncio.create_task(producer("q"))
        await asyncio.sleep(0)
        initiator.cancel()
        await asyncio.sleep(0)
        release.set()
        result = await joiner

    assert result == {"v": 2}
    with pytest.raises(asyncio.CancelledError):
        await initiator
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_initiator_cancellation_keeps_producer_registered_for_late_callers():
    """F002 (the real bug): cancelling the INITIATOR while its producer is still
    running must NOT deregister the single-flight entry. A caller that arrives
    AFTER the cancellation must coalesce onto the SAME producer, never start a
    second one (no stampede / double LLM cost)."""
    from src.infrastructure.cache.llm_cache import cache_llm_response

    calls = {"n": 0}
    release = asyncio.Event()

    @cache_llm_response(ttl_seconds=60)
    async def producer(x: str) -> dict:
        calls["n"] += 1
        await release.wait()
        return {"v": 3}

    redis = _mock_redis(get_return=None)
    with patch(
        "src.infrastructure.cache.llm_cache.get_redis_cache",
        new=AsyncMock(return_value=redis),
    ):
        initiator = asyncio.create_task(producer("q"))
        await asyncio.sleep(0)  # initiator registers the producer + awaits it
        initiator.cancel()
        for _ in range(4):
            await asyncio.sleep(0)  # let the cancellation fully unwind
        # Late caller AFTER the initiator was cancelled, producer still running.
        late = asyncio.create_task(producer("q"))
        for _ in range(4):
            await asyncio.sleep(0)
        release.set()
        result = await late

    assert result == {"v": 3}
    with pytest.raises(asyncio.CancelledError):
        await initiator
    assert calls["n"] == 1  # single producer despite initiator cancellation


@pytest.mark.asyncio
async def test_producer_deregisters_itself_after_completion():
    """The producer task owns cleanup: once it finishes, the key is removed so a
    fresh call recomputes (bounded map), not stuck on a stale finished task."""
    from src.infrastructure.cache.llm_cache import _producer_inflight, cache_llm_response

    calls = {"n": 0}

    @cache_llm_response(ttl_seconds=60)
    async def producer(x: str) -> dict:
        calls["n"] += 1
        return {"v": 4}

    redis = _mock_redis(get_return=None)
    with patch(
        "src.infrastructure.cache.llm_cache.get_redis_cache",
        new=AsyncMock(return_value=redis),
    ):
        await producer("q")
        for _ in range(4):
            await asyncio.sleep(0)  # let the done-callback deregister
        assert not any(k for k in _producer_inflight), "producer must deregister after completion"
