"""
Unit tests for WebSearchCache.

Tests coverage for:
- get_search / set_search: Cache hit, miss, TTL, disabled, errors
- get_fetch / set_fetch: Cache hit, miss, TTL, disabled, errors
- Key generation: Query + recency composite, URL hashing
- Multi-tenant isolation: User ID in cache keys

Target: 80%+ coverage for infrastructure/cache/web_search_cache.py
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.cache.web_search_cache import WebSearchCache

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Create mock Redis client for testing."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    return redis


@pytest.fixture
def user_id():
    """Test user ID."""
    return uuid4()


@pytest.fixture
def cache(mock_redis):
    """Create WebSearchCache with mock Redis."""
    return WebSearchCache(mock_redis)


def _make_cache_entry(data: dict) -> str:
    """Create a V2 cache entry JSON string."""
    return json.dumps(
        {
            "data": data,
            "cached_at": datetime.now(UTC).isoformat(),
            "ttl": 300,
        }
    )


# =============================================================================
# Web Search Cache - get_search
# =============================================================================


class TestGetSearch:
    """Tests for WebSearchCache.get_search()."""

    @pytest.mark.asyncio
    async def test_cache_miss_returns_empty_result(self, cache, user_id, mock_redis):
        """Cache miss returns CacheResult with from_cache=False."""
        mock_redis.get.return_value = None

        result = await cache.get_search(user_id, "test query")

        assert not result.from_cache
        assert result.data is None

    @pytest.mark.asyncio
    async def test_cache_hit_returns_data(self, cache, user_id, mock_redis):
        """Cache hit returns CacheResult with from_cache=True and data."""
        cached_data = {"message": "cached results", "metadata": {"query": "test"}}
        mock_redis.get.return_value = _make_cache_entry(cached_data)

        result = await cache.get_search(user_id, "test query")

        assert result.from_cache
        assert result.data == cached_data
        assert result.cache_age_seconds is not None

    @pytest.mark.asyncio
    async def test_different_recency_different_keys(self, cache, user_id, mock_redis):
        """Different recency filters produce different cache keys."""
        mock_redis.get.return_value = None

        await cache.get_search(user_id, "test query", recency=None)
        key_none = mock_redis.get.call_args_list[0][0][0]

        await cache.get_search(user_id, "test query", recency="day")
        key_day = mock_redis.get.call_args_list[1][0][0]

        assert key_none != key_day

    @pytest.mark.asyncio
    async def test_disabled_cache_returns_miss(self, cache, user_id, mock_redis):
        """When cache is disabled, always returns miss without Redis call."""
        with patch("src.infrastructure.cache.web_search_cache.settings") as mock_settings:
            mock_settings.web_search_cache_enabled = False

            result = await cache.get_search(user_id, "test query")

            assert not result.from_cache
            mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_error_returns_miss(self, cache, user_id, mock_redis):
        """Redis connection error returns graceful cache miss."""
        mock_redis.get.side_effect = ConnectionError("Redis down")

        result = await cache.get_search(user_id, "test query")

        assert not result.from_cache
        assert result.data is None


# =============================================================================
# Web Search Cache - set_search
# =============================================================================


class TestSetSearch:
    """Tests for WebSearchCache.set_search()."""

    @pytest.mark.asyncio
    async def test_stores_with_v2_format(self, cache, user_id, mock_redis):
        """Data is stored in CacheEntryV2 format with TTL."""
        data = {"message": "test results", "metadata": {}}

        await cache.set_search(user_id, "test query", data)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        stored_json = call_args[0][1]
        stored_data = json.loads(stored_json)

        assert "data" in stored_data
        assert "cached_at" in stored_data
        assert "ttl" in stored_data
        assert stored_data["data"] == data

    @pytest.mark.asyncio
    async def test_custom_ttl(self, cache, user_id, mock_redis):
        """Custom TTL is passed to Redis set."""
        await cache.set_search(user_id, "test", {}, ttl_seconds=60)

        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs["ex"] == 60

    @pytest.mark.asyncio
    async def test_disabled_cache_skips_store(self, cache, user_id, mock_redis):
        """When cache is disabled, does not store."""
        with patch("src.infrastructure.cache.web_search_cache.settings") as mock_settings:
            mock_settings.web_search_cache_enabled = False

            await cache.set_search(user_id, "test", {})

            mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_error_does_not_raise(self, cache, user_id, mock_redis):
        """Redis error during store does not propagate."""
        mock_redis.set.side_effect = ConnectionError("Redis down")

        # Should not raise
        await cache.set_search(user_id, "test", {"data": "test"})


# =============================================================================
# Web Fetch Cache - get_fetch
# =============================================================================


class TestGetFetch:
    """Tests for WebSearchCache.get_fetch()."""

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache, user_id, mock_redis):
        """Fetch cache miss returns empty result."""
        mock_redis.get.return_value = None

        result = await cache.get_fetch(user_id, "https://example.com")

        assert not result.from_cache

    @pytest.mark.asyncio
    async def test_cache_hit(self, cache, user_id, mock_redis):
        """Fetch cache hit returns stored data."""
        cached_data = {"message": "page content", "structured_data": {"title": "Test"}}
        mock_redis.get.return_value = _make_cache_entry(cached_data)

        result = await cache.get_fetch(user_id, "https://example.com")

        assert result.from_cache
        assert result.data == cached_data


# =============================================================================
# Web Fetch Cache - set_fetch
# =============================================================================


class TestSetFetch:
    """Tests for WebSearchCache.set_fetch()."""

    @pytest.mark.asyncio
    async def test_stores_fetch_result(self, cache, user_id, mock_redis):
        """Fetch data is stored correctly."""
        data = {"message": "content", "structured_data": {}}

        await cache.set_fetch(user_id, "https://example.com", data)

        mock_redis.set.assert_called_once()


# =============================================================================
# Multi-Tenant Isolation
# =============================================================================


class TestMultiTenantIsolation:
    """Tests for user ID isolation in cache keys."""

    @pytest.mark.asyncio
    async def test_different_users_different_keys(self, mock_redis):
        """Different users get different cache keys for same query."""
        cache = WebSearchCache(mock_redis)
        user_a = uuid4()
        user_b = uuid4()

        mock_redis.get.return_value = None

        await cache.get_search(user_a, "same query")
        key_a = mock_redis.get.call_args_list[0][0][0]

        await cache.get_search(user_b, "same query")
        key_b = mock_redis.get.call_args_list[1][0][0]

        assert key_a != key_b
        assert str(user_a) in key_a
        assert str(user_b) in key_b
