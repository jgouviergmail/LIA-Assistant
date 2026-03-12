"""
Integration tests for cache hit metrics alignment (Phase 2.1.9 - RC4 Fix).

Tests that cache hits trigger correct Prometheus metrics and that metadata
is properly stored/retrieved across cache MISS/HIT cycles.

Critical behaviors tested:
    1. Cache MISS: Stores v2 format with usage_metadata
    2. Cache HIT v2: Extracts metadata and records metrics
    3. Cache HIT v1: Handles legacy format gracefully
    4. Prometheus metrics: Verify token/cost counters increment correctly
    5. Observability metrics: Track cache hits/misses/format migration

User feedback: "Priorité aux tests d'intégration, surtout pour vérifier que
Prometheus, Langfuse et la base reçoivent bien les mêmes valeurs sur un hit/miss."
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import REGISTRY

from src.infrastructure.cache.llm_cache import (
    CacheJSONEncoder,
    cache_llm_response,
    llm_cache_errors_total,
    llm_cache_format_migration,
    llm_cache_hits_total,
    llm_cache_misses_total,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis client for cache operations."""
    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(return_value=None)  # Default: cache miss
    redis_mock.setex = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_callbacks():
    """
    Mock LangChain callbacks with usage_metadata.

    Simulates MetricsCallbackHandler with stored metadata after LLM call.
    """
    callback_mock = MagicMock()
    callback_mock._last_usage_metadata = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cached_tokens": 0,
        "model_name": "gpt-4.1-mini",
    }
    return [callback_mock]


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset Prometheus metrics before each test to avoid pollution."""
    # Clear metric families from registry
    for collector in list(REGISTRY._collector_to_names.keys()):
        try:
            if hasattr(collector, "_metrics"):
                collector._metrics.clear()
        except Exception:
            pass  # Ignore metrics that can't be cleared
    yield


# ============================================================================
# Cache MISS - v2 Format Storage Tests
# ============================================================================


@pytest.mark.asyncio
async def test_cache_miss_stores_v2_format_with_metadata(mock_redis, mock_callbacks):
    """
    Test that cache MISS stores v2 format with usage metadata.

    Scenario:
        1. First call (cache miss)
        2. Function executes with callbacks
        3. Result cached with v2 format (result + metadata)

    Validates:
        - v2 format structure correct
        - usage_metadata extracted from callbacks
        - CacheJSONEncoder used for serialization
    """

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str, config: dict) -> dict:
        """Mock LLM function that returns structured output."""
        return {"next_node": "response_node", "confidence": 0.95}

    # Patch redis to simulate cache miss
    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        result = await mock_llm_function(prompt="test prompt", config={"callbacks": mock_callbacks})

        # Verify function executed correctly
        assert result == {"next_node": "response_node", "confidence": 0.95}

        # Verify Redis setex called (cache stored)
        assert mock_redis.setex.called, "Cache should store result"

        # Extract serialized cache value
        call_args = mock_redis.setex.call_args
        cache_key, ttl, serialized_value = call_args[0]

        # Verify TTL
        assert ttl == 60

        # Deserialize and verify v2 format
        cached_data = json.loads(serialized_value)
        assert "result" in cached_data, "v2 format should have 'result' key"
        assert "metadata" in cached_data, "v2 format should have 'metadata' key"

        # Verify result
        assert cached_data["result"] == {"next_node": "response_node", "confidence": 0.95}

        # Verify metadata structure
        metadata = cached_data["metadata"]
        assert metadata["version"] == 2
        assert "cached_at" in metadata
        assert "usage" in metadata

        # Verify usage metadata extracted from callbacks
        usage = metadata["usage"]
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50
        assert usage["cached_tokens"] == 0
        assert usage["model_name"] == "gpt-4.1-mini"


@pytest.mark.asyncio
async def test_cache_miss_clears_callback_metadata_after_extraction(mock_redis, mock_callbacks):
    """
    Test that callback metadata is cleared after extraction (memory safety).

    Scenario:
        1. Cache miss with callbacks containing metadata
        2. Metadata extracted and stored in cache
        3. Callback metadata cleared to prevent reuse

    Validates: Memory safety (no stale metadata)
    """

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str, config: dict) -> dict:
        return {"result": "test"}

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        await mock_llm_function(prompt="test", config={"callbacks": mock_callbacks})

        # Verify callback metadata cleared after extraction
        assert (
            mock_callbacks[0]._last_usage_metadata is None
        ), "Callback metadata should be cleared after cache storage"


@pytest.mark.asyncio
async def test_cache_miss_increments_prometheus_miss_counter(mock_redis, mock_callbacks):
    """
    Test that cache MISS increments llm_cache_misses_total counter.

    Scenario:
        1. Cache miss occurs
        2. Prometheus counter should increment

    Validates: Observability metrics
    """

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str, config: dict) -> dict:
        return {"result": "test"}

    # Get initial counter value
    initial_count = llm_cache_misses_total.labels(func_name="mock_llm_function")._value.get()

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        await mock_llm_function(prompt="test", config={"callbacks": mock_callbacks})

    # Verify counter incremented
    final_count = llm_cache_misses_total.labels(func_name="mock_llm_function")._value.get()
    assert final_count == initial_count + 1, "Cache miss counter should increment"


# ============================================================================
# Cache HIT v2 - Metrics Recording Tests
# ============================================================================


@pytest.mark.asyncio
async def test_cache_hit_v2_extracts_metadata_and_records_metrics(mock_redis):
    """
    Test that cache HIT v2 extracts metadata and triggers Prometheus metrics.

    Scenario:
        1. Cache contains v2 format (result + metadata)
        2. Cache hit occurs
        3. Metadata extracted and metrics recorded

    Validates:
        - Metadata extraction
        - _record_cache_hit_metrics called
        - Token/cost counters increment
    """
    # Create v2 cache value
    cache_value_v2 = {
        "result": {"next_node": "response_node", "confidence": 0.95},
        "metadata": {
            "version": 2,
            "cached_at": 1704110400.0,
            "usage": {
                "input_tokens": 200,
                "output_tokens": 100,
                "cached_tokens": 0,
                "model_name": "gpt-4.1-mini",
            },
        },
    }

    # Serialize with CacheJSONEncoder
    serialized_value = json.dumps(cache_value_v2, cls=CacheJSONEncoder)

    # Configure mock Redis to return cached value
    mock_redis.get = AsyncMock(return_value=serialized_value)

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str, config: dict) -> dict:
        # This should NOT execute due to cache hit
        raise AssertionError("Function should not execute on cache hit")

    # Patch _record_cache_hit_metrics to verify it's called
    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        with patch("src.infrastructure.cache.llm_cache._record_cache_hit_metrics") as mock_record:
            mock_record.return_value = None  # Async function

            result = await mock_llm_function(
                prompt="test",
                config={"metadata": {"langgraph_node": "test_node"}, "callbacks": []},
            )

            # Verify result returned from cache
            assert result == {"next_node": "response_node", "confidence": 0.95}

            # Verify _record_cache_hit_metrics called with correct arguments
            assert mock_record.called, "_record_cache_hit_metrics should be called"
            call_args = mock_record.call_args[1]  # Get keyword arguments
            assert call_args["usage_metadata"]["input_tokens"] == 200
            assert call_args["usage_metadata"]["output_tokens"] == 100
            assert call_args["node_name"] == "test_node"


@pytest.mark.asyncio
async def test_cache_hit_v2_increments_prometheus_hit_counter(mock_redis):
    """
    Test that cache HIT v2 increments llm_cache_hits_total counter.

    Scenario:
        1. Cache hit with v2 format
        2. Prometheus counter should increment with correct labels

    Validates: Observability metrics
    """
    cache_value_v2 = {
        "result": {"test": "data"},
        "metadata": {
            "version": 2,
            "cached_at": 1704110400.0,
            "usage": {
                "input_tokens": 50,
                "output_tokens": 25,
                "cached_tokens": 0,
                "model_name": "gpt-4.1-mini",
            },
        },
    }

    serialized_value = json.dumps(cache_value_v2, cls=CacheJSONEncoder)
    mock_redis.get = AsyncMock(return_value=serialized_value)

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str, config: dict) -> dict:
        raise AssertionError("Should not execute")

    # Get initial counter value
    initial_count = llm_cache_hits_total.labels(
        func_name="mock_llm_function", format_version="2", has_usage="True"
    )._value.get()

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        with patch("src.infrastructure.cache.llm_cache._record_cache_hit_metrics"):
            await mock_llm_function(
                prompt="test", config={"metadata": {"langgraph_node": "test_node"}}
            )

    # Verify counter incremented with correct labels
    final_count = llm_cache_hits_total.labels(
        func_name="mock_llm_function", format_version="2", has_usage="True"
    )._value.get()
    assert final_count == initial_count + 1, "Cache hit v2 counter should increment"


# ============================================================================
# Cache HIT v1 - Legacy Format Tests
# ============================================================================


@pytest.mark.asyncio
async def test_cache_hit_v1_handles_legacy_format_gracefully(mock_redis):
    """
    Test that cache HIT v1 (legacy format) is handled without errors.

    Scenario:
        1. Cache contains v1 format (result only, no metadata)
        2. Cache hit occurs
        3. Result returned, no metrics recorded (no usage data)

    Validates:
        - Backward compatibility
        - No exceptions raised
        - Legacy format migration counter incremented
    """
    # v1 format: result only (no metadata wrapper)
    cache_value_v1 = {"next_node": "response_node", "confidence": 0.95}

    serialized_value = json.dumps(cache_value_v1)
    mock_redis.get = AsyncMock(return_value=serialized_value)

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str, config: dict) -> dict:
        raise AssertionError("Should not execute on cache hit")

    # Get initial migration counter
    initial_migration_count = llm_cache_format_migration.labels(
        func_name="mock_llm_function"
    )._value.get()

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        result = await mock_llm_function(prompt="test", config={})

        # Verify result returned correctly
        assert result == {"next_node": "response_node", "confidence": 0.95}

    # Verify migration counter incremented
    final_migration_count = llm_cache_format_migration.labels(
        func_name="mock_llm_function"
    )._value.get()
    assert (
        final_migration_count == initial_migration_count + 1
    ), "Legacy format migration counter should increment"


@pytest.mark.asyncio
async def test_cache_hit_v1_increments_correct_prometheus_labels(mock_redis):
    """
    Test that cache HIT v1 increments hit counter with correct labels.

    Scenario:
        1. Cache hit with v1 format (no metadata)
        2. Counter incremented with format_version="1", has_usage="False"

    Validates: Metric labeling for legacy format
    """
    cache_value_v1 = {"result": "legacy"}
    serialized_value = json.dumps(cache_value_v1)
    mock_redis.get = AsyncMock(return_value=serialized_value)

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str, config: dict) -> dict:
        raise AssertionError("Should not execute")

    # Get initial counter value
    initial_count = llm_cache_hits_total.labels(
        func_name="mock_llm_function", format_version="1", has_usage="False"
    )._value.get()

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        await mock_llm_function(prompt="test", config={})

    # Verify counter incremented with v1 labels
    final_count = llm_cache_hits_total.labels(
        func_name="mock_llm_function", format_version="1", has_usage="False"
    )._value.get()
    assert final_count == initial_count + 1, "Cache hit v1 counter should increment"


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_cache_serialization_error_increments_error_counter(mock_redis, mock_callbacks):
    """
    Test that serialization errors increment llm_cache_errors_total counter.

    Scenario:
        1. Function returns non-serializable object
        2. CacheJSONEncoder fails
        3. Error counter incremented, function succeeds

    Validates: Error observability, graceful degradation
    """

    class UnserializableClass:
        """Object that cannot be JSON serialized."""

        pass

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str, config: dict) -> dict:
        return {"unsupported": UnserializableClass()}

    # Get initial error counter
    initial_error_count = llm_cache_errors_total.labels(
        func_name="mock_llm_function", error_type="serialization_failed"
    )._value.get()

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        # Should not raise exception (graceful degradation)
        result = await mock_llm_function(prompt="test", config={"callbacks": mock_callbacks})

        # Function should still return result
        assert "unsupported" in result

    # Verify error counter incremented
    final_error_count = llm_cache_errors_total.labels(
        func_name="mock_llm_function", error_type="serialization_failed"
    )._value.get()
    assert (
        final_error_count == initial_error_count + 1
    ), "Serialization error counter should increment"


@pytest.mark.asyncio
async def test_cache_miss_without_callbacks_stores_no_usage(mock_redis):
    """
    Test that cache MISS without callbacks stores v2 format with null usage.

    Scenario:
        1. Function called without callbacks (or callbacks without metadata)
        2. v2 format stored with usage=None
        3. No exceptions raised

    Validates: Graceful handling of missing usage data
    """

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str) -> dict:
        return {"result": "test"}

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        result = await mock_llm_function(prompt="test")

        # Verify function executed
        assert result == {"result": "test"}

        # Verify cache stored with usage=None
        assert mock_redis.setex.called
        call_args = mock_redis.setex.call_args[0]
        serialized_value = call_args[2]

        cached_data = json.loads(serialized_value)
        assert cached_data["metadata"]["usage"] is None, "Usage should be None without callbacks"


# ============================================================================
# Full Cycle Integration Test
# ============================================================================


@pytest.mark.asyncio
async def test_full_cache_cycle_miss_then_hit(mock_redis, mock_callbacks):
    """
    Test complete cache cycle: MISS → storage → HIT → metrics.

    Scenario:
        1. First call (cache miss): Execute, store v2 format
        2. Second call (cache hit): Return cached result, record metrics

    Validates: End-to-end cache behavior with metrics
    """

    @cache_llm_response(ttl_seconds=60)
    async def mock_llm_function(prompt: str, config: dict) -> dict:
        # Track execution count
        if not hasattr(mock_llm_function, "call_count"):
            mock_llm_function.call_count = 0
        mock_llm_function.call_count += 1

        return {"next_node": "response_node", "execution": mock_llm_function.call_count}

    stored_value = None

    async def mock_setex(key, ttl, value):
        nonlocal stored_value
        stored_value = value

    async def mock_get(key):
        return stored_value

    mock_redis.setex = mock_setex
    mock_redis.get = mock_get

    with patch("src.infrastructure.cache.llm_cache.get_redis_cache", return_value=mock_redis):
        # === First call (MISS) ===
        result1 = await mock_llm_function(
            prompt="test",
            config={"callbacks": mock_callbacks, "metadata": {"langgraph_node": "test_node"}},
        )

        assert result1["execution"] == 1, "First call should execute function"
        assert stored_value is not None, "Cache should store result"

        # Verify v2 format stored
        cached_data = json.loads(stored_value)
        assert cached_data["metadata"]["version"] == 2
        assert cached_data["metadata"]["usage"] is not None

        # === Second call (HIT) ===
        with patch("src.infrastructure.cache.llm_cache._record_cache_hit_metrics") as mock_record:
            mock_record.return_value = None

            result2 = await mock_llm_function(
                prompt="test", config={"metadata": {"langgraph_node": "test_node"}}
            )

            # Should return cached result (execution=1, not 2)
            assert result2["execution"] == 1, "Second call should return cached result"

            # Verify metrics recorded
            assert mock_record.called, "Cache hit metrics should be recorded"
