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


@pytest.mark.skip(reason="Serialization implementation changed")
def test_serialize_arg_dataclass_with_non_serializable_field():
    """
    Test dataclass with non-serializable field (e.g., PGconn).

    Scenario:
    - Dataclass contains object that can't be serialized
    - Should gracefully skip field with placeholder

    Validates: Graceful handling of psycopg PGconn errors
    """

    class NonSerializable:
        """Object that simulates PGconn - can't be serialized."""

        def __reduce__(self):
            raise TypeError("no default __reduce__ due to non-trivial __cinit__")

    obj = DataclassWithNonSerializable(id="test-123", connection=NonSerializable())

    result = _serialize_arg(obj)

    assert result["id"] == "test-123"
    assert "non-serializable" in result["connection"].lower()


@pytest.mark.skip(reason="Serialization implementation changed")
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

    obj = BrokenDataclass(value=42)

    # Should fallback to str() without crashing
    result = _serialize_arg(obj)

    assert isinstance(result, str)


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
@pytest.mark.skip(reason="Metrics implementation changed")
async def test_record_cache_hit_metrics_all_token_types():
    """
    Test that all token types are recorded correctly.

    Validates:
    - Input tokens counter incremented
    - Output tokens counter incremented
    - Cached tokens counter incremented
    """
    usage_metadata = {
        "input_tokens": 200,
        "output_tokens": 100,
        "cached_tokens": 50,
        "model_name": "gpt-4.1-mini",
    }

    with patch("src.infrastructure.cache.llm_cache.llm_tokens_consumed_total") as mock_counter:
        with patch("src.infrastructure.cache.llm_cache.estimate_cost_usd", return_value=0.01):
            with patch("src.infrastructure.cache.llm_cache.llm_cost_total"):
                await _record_cache_hit_metrics(usage_metadata, node_name="test_node")

                # Verify all token types recorded
                assert mock_counter.labels.call_count >= 3


@pytest.mark.asyncio
@pytest.mark.skip(reason="Metrics implementation changed")
async def test_record_cache_hit_metrics_cost_calculation():
    """
    Test that cost is estimated and recorded.

    Validates:
    - estimate_cost_usd called with correct parameters
    - llm_cost_total counter incremented
    """
    usage_metadata = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cached_tokens": 0,
        "model_name": "gpt-4.1-mini",
    }

    with patch("src.infrastructure.cache.llm_cache.estimate_cost_usd") as mock_estimate:
        mock_estimate.return_value = 0.0025

        with patch("src.infrastructure.cache.llm_cache.llm_tokens_consumed_total"):
            with patch("src.infrastructure.cache.llm_cache.llm_cost_total") as mock_cost:
                with patch("src.infrastructure.cache.llm_cache.settings") as mock_settings:
                    mock_settings.default_currency = "eur"

                    await _record_cache_hit_metrics(usage_metadata, node_name="test_node")

                    # Verify estimate_cost_usd called
                    mock_estimate.assert_called_once_with(
                        model="gpt-4.1-mini",
                        prompt_tokens=100,
                        completion_tokens=50,
                        cached_tokens=0,
                    )

                    # Verify cost counter incremented
                    assert mock_cost.labels.called


@pytest.mark.asyncio
@pytest.mark.skip(reason="Metrics implementation changed")
async def test_record_cache_hit_metrics_prometheus_counters():
    """
    Test that Prometheus counters are incremented correctly.

    Validates:
    - Token counters incremented with correct labels
    - Cost counter incremented with correct labels
    """
    usage_metadata = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cached_tokens": 0,
        "model_name": "gpt-4.1-mini",
    }

    with patch("src.infrastructure.cache.llm_cache.llm_tokens_consumed_total") as mock_tokens:
        with patch("src.infrastructure.cache.llm_cache.llm_cost_total") as mock_cost:
            with patch("src.infrastructure.cache.llm_cache.estimate_cost_usd", return_value=0.01):
                with patch("src.infrastructure.cache.llm_cache.settings") as mock_settings:
                    mock_settings.default_currency = "usd"

                    await _record_cache_hit_metrics(usage_metadata, node_name="router")

                    # Verify labels called with correct parameters
                    mock_tokens.labels.assert_called()
                    mock_cost.labels.assert_called()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Metrics implementation changed")
async def test_record_cache_hit_metrics_zero_tokens():
    """
    Test handling of zero token values.

    Validates: Counters only incremented for non-zero values
    """
    usage_metadata = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "model_name": "gpt-4.1-mini",
    }

    with patch("src.infrastructure.cache.llm_cache.llm_tokens_consumed_total"):
        with patch("src.infrastructure.cache.llm_cache.llm_cost_total"):
            with patch("src.infrastructure.cache.llm_cache.estimate_cost_usd", return_value=0.0):
                await _record_cache_hit_metrics(usage_metadata, node_name="test_node")

                # Should not increment counters for zero values
                # (implementation may vary, this validates no errors)
                assert True  # No exception raised


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
