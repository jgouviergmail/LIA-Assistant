"""
Unit tests for Redis cache helpers.

Tests coverage for:
- cache_set_json: JSON serialization and storage with TTL
- cache_get_json: JSON deserialization and retrieval
- cache_get_or_compute: Cache-aside pattern
- cache_invalidate_pattern: Pattern-based cache invalidation

Target: 80%+ coverage for infrastructure/cache/redis_helpers.py
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.cache.redis_helpers import (
    cache_get_json,
    cache_get_or_compute,
    cache_invalidate_pattern,
    cache_set_json,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Create mock Redis client for testing."""
    redis = MagicMock()
    redis.setex = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)
    redis.scan = AsyncMock(return_value=(0, []))
    return redis


# =============================================================================
# cache_set_json - Unit Tests
# =============================================================================


class TestCacheSetJson:
    """Tests for cache_set_json function."""

    @pytest.mark.asyncio
    async def test_set_json_dict(self, mock_redis):
        """Test setting a dict in cache."""
        data = {"key": "value", "number": 42}

        await cache_set_json(mock_redis, "test:key", data, 300)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "test:key"
        assert call_args[0][1] == 300
        # Verify JSON structure
        stored_data = json.loads(call_args[0][2])
        assert stored_data["data"] == data
        assert "cached_at" in stored_data

    @pytest.mark.asyncio
    async def test_set_json_list(self, mock_redis):
        """Test setting a list in cache."""
        data = [1, 2, "three", {"nested": "value"}]

        await cache_set_json(mock_redis, "test:list", data, 600)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])
        assert stored_data["data"] == data

    @pytest.mark.asyncio
    async def test_set_json_without_timestamp(self, mock_redis):
        """Test setting JSON without automatic timestamp."""
        data = {"test": "data"}

        await cache_set_json(mock_redis, "test:key", data, 300, add_timestamp=False)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])
        assert "cached_at" not in stored_data
        assert stored_data["data"] == data

    @pytest.mark.asyncio
    async def test_set_json_with_timestamp(self, mock_redis):
        """Test that timestamp is added by default."""
        data = {"test": "data"}

        await cache_set_json(mock_redis, "test:key", data, 300)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])
        assert "cached_at" in stored_data
        # Verify timestamp is valid ISO format
        timestamp = datetime.fromisoformat(stored_data["cached_at"])
        assert timestamp is not None

    @pytest.mark.asyncio
    async def test_set_json_unicode_data(self, mock_redis):
        """Test setting JSON with unicode characters."""
        data = {"message": "Bonjour, café! 你好"}

        await cache_set_json(mock_redis, "test:unicode", data, 300)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])
        assert stored_data["data"]["message"] == "Bonjour, café! 你好"

    @pytest.mark.asyncio
    async def test_set_json_nested_structure(self, mock_redis):
        """Test setting deeply nested JSON structure."""
        data = {"level1": {"level2": {"level3": [1, 2, {"level4": "value"}]}}}

        await cache_set_json(mock_redis, "test:nested", data, 300)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])
        assert stored_data["data"]["level1"]["level2"]["level3"][2]["level4"] == "value"

    @pytest.mark.asyncio
    async def test_set_json_raises_on_non_serializable(self, mock_redis):
        """Test that non-serializable data raises TypeError."""

        # Create non-serializable data
        class CustomClass:
            pass

        data = {"object": CustomClass()}

        with pytest.raises(TypeError) as exc_info:
            await cache_set_json(mock_redis, "test:key", data, 300)

        assert "not JSON-serializable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_json_propagates_redis_error(self, mock_redis):
        """Test that Redis errors are propagated."""
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis connection error"))

        with pytest.raises(Exception) as exc_info:
            await cache_set_json(mock_redis, "test:key", {"data": "value"}, 300)

        assert "Redis connection error" in str(exc_info.value)


# =============================================================================
# cache_get_json - Unit Tests
# =============================================================================


class TestCacheGetJson:
    """Tests for cache_get_json function."""

    @pytest.mark.asyncio
    async def test_get_json_hit(self, mock_redis):
        """Test cache hit returns deserialized data."""
        cached_data = {"data": {"key": "value"}, "cached_at": datetime.now(UTC).isoformat()}
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        result = await cache_get_json(mock_redis, "test:key")

        assert result is not None
        assert result["data"] == {"key": "value"}
        assert "cached_at" in result

    @pytest.mark.asyncio
    async def test_get_json_miss(self, mock_redis):
        """Test cache miss returns None."""
        mock_redis.get = AsyncMock(return_value=None)

        result = await cache_get_json(mock_redis, "test:nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_json_empty_string(self, mock_redis):
        """Test empty string returns None."""
        mock_redis.get = AsyncMock(return_value="")

        result = await cache_get_json(mock_redis, "test:empty")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_json_corrupted_deletes_key(self, mock_redis):
        """Test corrupted JSON data deletes the key and returns None."""
        mock_redis.get = AsyncMock(return_value="not valid json {{{")
        mock_redis.delete = AsyncMock()

        result = await cache_get_json(mock_redis, "test:corrupted")

        assert result is None
        mock_redis.delete.assert_called_once_with("test:corrupted")

    @pytest.mark.asyncio
    async def test_get_json_list_data(self, mock_redis):
        """Test retrieving cached list data."""
        cached_data = {"data": [1, 2, 3, "four"], "cached_at": datetime.now(UTC).isoformat()}
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        result = await cache_get_json(mock_redis, "test:list")

        assert result["data"] == [1, 2, 3, "four"]

    @pytest.mark.asyncio
    async def test_get_json_without_timestamp(self, mock_redis):
        """Test retrieving data without timestamp."""
        cached_data = {"data": {"key": "value"}}  # No cached_at
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        result = await cache_get_json(mock_redis, "test:key")

        assert result["data"] == {"key": "value"}
        assert "cached_at" not in result

    @pytest.mark.asyncio
    async def test_get_json_propagates_redis_error(self, mock_redis):
        """Test that Redis errors are propagated."""
        mock_redis.get = AsyncMock(side_effect=Exception("Redis connection error"))

        with pytest.raises(Exception) as exc_info:
            await cache_get_json(mock_redis, "test:key")

        assert "Redis connection error" in str(exc_info.value)


# =============================================================================
# cache_get_or_compute - Unit Tests
# =============================================================================


class TestCacheGetOrCompute:
    """Tests for cache_get_or_compute function."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self, mock_redis):
        """Test cache hit returns cached data without computing."""
        cached_data = {"data": {"result": "cached"}, "cached_at": datetime.now(UTC).isoformat()}
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        compute_fn = AsyncMock(return_value={"result": "computed"})

        result = await cache_get_or_compute(mock_redis, "test:key", 300, compute_fn)

        assert result["from_cache"] is True
        assert result["data"] == {"result": "cached"}
        compute_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_computes_and_caches(self, mock_redis):
        """Test cache miss computes data and caches it."""
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        compute_fn = AsyncMock(return_value={"result": "computed"})

        result = await cache_get_or_compute(mock_redis, "test:key", 300, compute_fn)

        assert result["from_cache"] is False
        assert result["data"] == {"result": "computed"}
        compute_fn.assert_called_once()
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, mock_redis):
        """Test force_refresh=True bypasses cache."""
        cached_data = {"data": {"result": "cached"}, "cached_at": datetime.now(UTC).isoformat()}
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))
        mock_redis.setex = AsyncMock()

        compute_fn = AsyncMock(return_value={"result": "fresh"})

        result = await cache_get_or_compute(
            mock_redis, "test:key", 300, compute_fn, force_refresh=True
        )

        assert result["from_cache"] is False
        assert result["data"] == {"result": "fresh"}
        compute_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_calculates_age(self, mock_redis):
        """Test cache hit calculates cache age correctly."""
        # Cache data 60 seconds ago
        from datetime import timedelta

        cached_at = datetime.now(UTC) - timedelta(seconds=60)
        cached_data = {"data": {"result": "cached"}, "cached_at": cached_at.isoformat()}
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        compute_fn = AsyncMock()

        result = await cache_get_or_compute(mock_redis, "test:key", 300, compute_fn)

        assert "cache_age_seconds" in result
        # Allow some tolerance for test execution time
        assert 55 < result["cache_age_seconds"] < 65

    @pytest.mark.asyncio
    async def test_cache_hit_without_timestamp(self, mock_redis):
        """Test cache hit without timestamp sets cache_age_seconds to None."""
        cached_data = {"data": {"result": "cached"}}  # No cached_at
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        compute_fn = AsyncMock()

        result = await cache_get_or_compute(mock_redis, "test:key", 300, compute_fn)

        assert result["from_cache"] is True
        assert result.get("cache_age_seconds") is None

    @pytest.mark.asyncio
    async def test_computed_data_has_fresh_timestamp(self, mock_redis):
        """Test computed data includes fresh timestamp."""
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        compute_fn = AsyncMock(return_value={"result": "computed"})

        result = await cache_get_or_compute(mock_redis, "test:key", 300, compute_fn)

        assert "cached_at" in result
        # Verify timestamp is recent (within last second)
        timestamp = datetime.fromisoformat(result["cached_at"])
        age = (datetime.now(UTC) - timestamp).total_seconds()
        assert age < 1


# =============================================================================
# cache_invalidate_pattern - Unit Tests
# =============================================================================


class TestCacheInvalidatePattern:
    """Tests for cache_invalidate_pattern function."""

    @pytest.mark.asyncio
    async def test_invalidate_no_matching_keys(self, mock_redis):
        """Test invalidation with no matching keys."""
        mock_redis.scan = AsyncMock(return_value=(0, []))

        count = await cache_invalidate_pattern(mock_redis, "test:*")

        assert count == 0
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalidate_single_batch(self, mock_redis):
        """Test invalidation with single batch of keys."""
        mock_redis.scan = AsyncMock(return_value=(0, ["test:key1", "test:key2"]))
        mock_redis.delete = AsyncMock(return_value=2)

        count = await cache_invalidate_pattern(mock_redis, "test:*")

        assert count == 2
        mock_redis.delete.assert_called_once_with("test:key1", "test:key2")

    @pytest.mark.asyncio
    async def test_invalidate_multiple_batches(self, mock_redis):
        """Test invalidation with multiple SCAN iterations."""
        # First call returns cursor=1 (more results), second returns cursor=0 (done)
        mock_redis.scan = AsyncMock(
            side_effect=[
                (1, ["test:key1", "test:key2"]),
                (0, ["test:key3"]),
            ]
        )
        mock_redis.delete = AsyncMock(side_effect=[2, 1])

        count = await cache_invalidate_pattern(mock_redis, "test:*")

        assert count == 3
        assert mock_redis.scan.call_count == 2
        assert mock_redis.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_propagates_redis_error(self, mock_redis):
        """Test that Redis errors are propagated."""
        mock_redis.scan = AsyncMock(side_effect=Exception("Redis connection error"))

        with pytest.raises(Exception) as exc_info:
            await cache_invalidate_pattern(mock_redis, "test:*")

        assert "Redis connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalidate_handles_empty_batch(self, mock_redis):
        """Test invalidation handles empty intermediate batch."""
        mock_redis.scan = AsyncMock(
            side_effect=[
                (1, []),  # Empty batch but not done
                (0, ["test:key1"]),  # Final batch
            ]
        )
        mock_redis.delete = AsyncMock(return_value=1)

        count = await cache_invalidate_pattern(mock_redis, "test:*")

        assert count == 1
        # delete should only be called once (for non-empty batch)
        mock_redis.delete.assert_called_once_with("test:key1")


# =============================================================================
# Integration-style Tests (testing functions together)
# =============================================================================


class TestCacheHelperIntegration:
    """Integration-style tests for cache helpers working together."""

    @pytest.mark.asyncio
    async def test_set_then_get_roundtrip(self, mock_redis):
        """Test data survives set/get roundtrip."""
        original_data = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ],
            "total": 2,
        }

        # Capture what was set
        stored_json = None

        async def capture_setex(key, ttl, value):
            nonlocal stored_json
            stored_json = value

        mock_redis.setex = capture_setex

        # Set data
        await cache_set_json(mock_redis, "test:users", original_data, 300)

        # Now mock get to return what was stored
        mock_redis.get = AsyncMock(return_value=stored_json)

        # Get data
        result = await cache_get_json(mock_redis, "test:users")

        assert result is not None
        assert result["data"] == original_data
        assert "cached_at" in result

    @pytest.mark.asyncio
    async def test_empty_dict_storage(self, mock_redis):
        """Test storing and retrieving empty dict."""
        mock_redis.setex = AsyncMock()

        await cache_set_json(mock_redis, "test:empty", {}, 300)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])
        assert stored_data["data"] == {}

    @pytest.mark.asyncio
    async def test_empty_list_storage(self, mock_redis):
        """Test storing and retrieving empty list."""
        mock_redis.setex = AsyncMock()

        await cache_set_json(mock_redis, "test:empty", [], 300)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])
        assert stored_data["data"] == []

    @pytest.mark.asyncio
    async def test_null_values_in_dict(self, mock_redis):
        """Test dict with null values."""
        data = {"key": None, "nested": {"also_null": None}}
        mock_redis.setex = AsyncMock()

        await cache_set_json(mock_redis, "test:nulls", data, 300)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])
        assert stored_data["data"]["key"] is None
        assert stored_data["data"]["nested"]["also_null"] is None

    @pytest.mark.asyncio
    async def test_numeric_types_preserved(self, mock_redis):
        """Test that numeric types are preserved."""
        data = {
            "integer": 42,
            "float": 3.14159,
            "negative": -100,
            "zero": 0,
            "big_int": 9999999999999999,
        }
        mock_redis.setex = AsyncMock()

        await cache_set_json(mock_redis, "test:numbers", data, 300)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])

        assert stored_data["data"]["integer"] == 42
        assert abs(stored_data["data"]["float"] - 3.14159) < 0.0001
        assert stored_data["data"]["negative"] == -100
        assert stored_data["data"]["zero"] == 0
        assert stored_data["data"]["big_int"] == 9999999999999999

    @pytest.mark.asyncio
    async def test_boolean_values_preserved(self, mock_redis):
        """Test that boolean values are preserved."""
        data = {"true_val": True, "false_val": False}
        mock_redis.setex = AsyncMock()

        await cache_set_json(mock_redis, "test:bools", data, 300)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])

        assert stored_data["data"]["true_val"] is True
        assert stored_data["data"]["false_val"] is False
