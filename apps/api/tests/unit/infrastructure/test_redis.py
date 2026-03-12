"""
Unit tests for Redis Cache and Session Management.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 28.1
Created: 2025-11-21
Target: 34% → 80%+ coverage
Module: infrastructure/cache/redis.py (80 statements)

Test Coverage:
- get_redis_cache: Singleton Redis client for caching (lazy initialization)
- get_redis_session: Singleton Redis client for sessions (lazy initialization)
- close_redis: Connection cleanup for both clients
- CacheService: Generic cache operations (get, set, delete, exists)
- SessionService: Session management with Redis sets
  - User sessions with refresh tokens
  - OAuth state token storage (single-use pattern)
  - Token verification and cleanup

Critical Infrastructure Module:
- Singleton pattern for Redis connections
- Multi-database support (cache DB vs session DB)
- Connection lifecycle management
- OAuth security patterns (single-use tokens)
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.cache.redis import (
    CacheService,
    SessionService,
    close_redis,
    get_redis_cache,
    get_redis_session,
)


class TestGetRedisCache:
    """Tests for get_redis_cache singleton Redis client."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.logger")
    @patch("src.infrastructure.cache.redis.settings")
    @patch("src.infrastructure.cache.redis.aioredis.from_url")
    async def test_get_redis_cache_initializes_on_first_call(
        self, mock_from_url, mock_settings, mock_logger
    ):
        """Test get_redis_cache creates client on first call (Lines 29-42)."""
        # Reset global state
        import src.infrastructure.cache.redis as redis_module

        redis_module._redis_cache = None

        # Mock settings with all required attributes
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.redis_cache_db = 1
        mock_settings.redis_max_connections = 10
        mock_settings.redis_socket_timeout = 5.0
        mock_settings.redis_socket_connect_timeout = 5.0
        mock_settings.redis_health_check_interval = 30

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_from_url.return_value = mock_redis

        # Lines 29-42 executed: First call creates client
        result = await get_redis_cache()

        # Verify client created
        assert result == mock_redis
        mock_from_url.assert_called_once_with(
            "redis://localhost:6379/1",
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            health_check_interval=30,
        )

        # Verify logging
        mock_logger.info.assert_called_once_with(
            "redis_cache_connected",
            db=1,
            max_connections=10,
            socket_timeout=5.0,
            health_check_interval=30,
        )

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.aioredis.from_url")
    async def test_get_redis_cache_returns_existing_client(self, mock_from_url):
        """Test get_redis_cache returns existing client on subsequent calls (Line 29)."""
        # Set up existing client
        import src.infrastructure.cache.redis as redis_module

        mock_existing = AsyncMock()
        redis_module._redis_cache = mock_existing

        # Line 29: Returns existing client without creating new one
        result = await get_redis_cache()

        assert result == mock_existing
        mock_from_url.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.settings")
    @patch("src.infrastructure.cache.redis.aioredis.from_url")
    async def test_get_redis_cache_constructs_url_correctly(self, mock_from_url, mock_settings):
        """Test get_redis_cache constructs cache URL from base URL (Lines 30-33)."""
        # Reset global state
        import src.infrastructure.cache.redis as redis_module

        redis_module._redis_cache = None

        # Mock settings with complex URL and all required attributes
        mock_settings.redis_url = "redis://:password@redis.example.com:6379/0"
        mock_settings.redis_cache_db = 2
        mock_settings.redis_max_connections = 10
        mock_settings.redis_socket_timeout = 5.0
        mock_settings.redis_socket_connect_timeout = 5.0
        mock_settings.redis_health_check_interval = 30

        mock_from_url.return_value = AsyncMock()

        # Lines 30-33: URL construction with base_url.rsplit()
        await get_redis_cache()

        # Verify URL construction
        expected_url = "redis://:password@redis.example.com:6379/2"
        mock_from_url.assert_called_once()
        actual_url = mock_from_url.call_args[0][0]
        assert actual_url == expected_url


class TestGetRedisSession:
    """Tests for get_redis_session singleton Redis client."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.logger")
    @patch("src.infrastructure.cache.redis.settings")
    @patch("src.infrastructure.cache.redis.aioredis.from_url")
    async def test_get_redis_session_initializes_on_first_call(
        self, mock_from_url, mock_settings, mock_logger
    ):
        """Test get_redis_session creates client on first call (Lines 54-67)."""
        # Reset global state
        import src.infrastructure.cache.redis as redis_module

        redis_module._redis_session = None

        # Mock settings with all required attributes
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.redis_session_db = 3
        mock_settings.redis_max_connections = 10
        mock_settings.redis_socket_timeout = 5.0
        mock_settings.redis_socket_connect_timeout = 5.0
        mock_settings.redis_health_check_interval = 30

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_from_url.return_value = mock_redis

        # Lines 54-67 executed: First call creates client
        result = await get_redis_session()

        # Verify client created
        assert result == mock_redis
        mock_from_url.assert_called_once_with(
            "redis://localhost:6379/3",
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            health_check_interval=30,
        )

        # Verify logging
        mock_logger.info.assert_called_once_with(
            "redis_session_connected",
            db=3,
            max_connections=10,
            socket_timeout=5.0,
            health_check_interval=30,
        )

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.aioredis.from_url")
    async def test_get_redis_session_returns_existing_client(self, mock_from_url):
        """Test get_redis_session returns existing client (Line 54)."""
        # Set up existing client
        import src.infrastructure.cache.redis as redis_module

        mock_existing = AsyncMock()
        redis_module._redis_session = mock_existing

        # Line 54: Returns existing client
        result = await get_redis_session()

        assert result == mock_existing
        mock_from_url.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.settings")
    @patch("src.infrastructure.cache.redis.aioredis.from_url")
    async def test_get_redis_session_constructs_url_correctly(self, mock_from_url, mock_settings):
        """Test get_redis_session constructs session URL (Lines 55-58)."""
        # Reset global state
        import src.infrastructure.cache.redis as redis_module

        redis_module._redis_session = None

        # Mock settings with all required attributes
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.redis_session_db = 4
        mock_settings.redis_max_connections = 10
        mock_settings.redis_socket_timeout = 5.0
        mock_settings.redis_socket_connect_timeout = 5.0
        mock_settings.redis_health_check_interval = 30

        mock_from_url.return_value = AsyncMock()

        # Lines 55-58: URL construction
        await get_redis_session()

        # Verify URL construction
        expected_url = "redis://localhost:6379/4"
        actual_url = mock_from_url.call_args[0][0]
        assert actual_url == expected_url


class TestCloseRedis:
    """Tests for close_redis connection cleanup."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.logger")
    async def test_close_redis_closes_both_clients(self, mock_logger):
        """Test close_redis closes both cache and session clients (Lines 74-80)."""
        # Set up both clients
        import src.infrastructure.cache.redis as redis_module

        mock_cache = AsyncMock()
        mock_session = AsyncMock()
        redis_module._redis_cache = mock_cache
        redis_module._redis_session = mock_session

        # Lines 74-80 executed: Close both clients
        await close_redis()

        # Verify both clients closed
        mock_cache.close.assert_called_once()
        mock_session.close.assert_called_once()

        # Verify logging
        assert mock_logger.info.call_count == 2
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert "redis_cache_closed" in log_calls
        assert "redis_session_closed" in log_calls

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.logger")
    async def test_close_redis_handles_none_cache(self, mock_logger):
        """Test close_redis handles None cache client gracefully (Line 74)."""
        # Set up only session client
        import src.infrastructure.cache.redis as redis_module

        redis_module._redis_cache = None
        mock_session = AsyncMock()
        redis_module._redis_session = mock_session

        # Line 74: Cache is None, only session closed
        await close_redis()

        # Verify only session closed
        mock_session.close.assert_called_once()
        mock_logger.info.assert_called_once_with("redis_session_closed")

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.logger")
    async def test_close_redis_handles_none_session(self, mock_logger):
        """Test close_redis handles None session client gracefully (Line 78)."""
        # Set up only cache client
        import src.infrastructure.cache.redis as redis_module

        mock_cache = AsyncMock()
        redis_module._redis_cache = mock_cache
        redis_module._redis_session = None

        # Line 78: Session is None, only cache closed
        await close_redis()

        # Verify only cache closed
        mock_cache.close.assert_called_once()
        mock_logger.info.assert_called_once_with("redis_cache_closed")

    @pytest.mark.asyncio
    async def test_close_redis_handles_both_none(self):
        """Test close_redis handles both clients as None (Lines 74, 78)."""
        # Set up no clients
        import src.infrastructure.cache.redis as redis_module

        redis_module._redis_cache = None
        redis_module._redis_session = None

        # Lines 74, 78: Both None, no errors
        await close_redis()

        # No assertions needed - just verify no exceptions


class TestCacheService:
    """Tests for CacheService generic cache operations."""

    @pytest.mark.asyncio
    async def test_cache_service_get_returns_value(self):
        """Test CacheService.get returns cached value (Lines 89-92)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="cached_value")
        service = CacheService(mock_redis)

        # Lines 89-92 executed
        result = await service.get("test_key")

        assert result == "cached_value"
        mock_redis.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_cache_service_get_returns_none_when_missing(self):
        """Test CacheService.get returns None for missing key (Line 92)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        service = CacheService(mock_redis)

        # Line 92: Returns None when result is None
        result = await service.get("missing_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_service_set_with_expiration(self):
        """Test CacheService.set stores value with TTL (Lines 94-101)."""
        mock_redis = AsyncMock()
        service = CacheService(mock_redis)

        # Lines 94-101 executed: Set with expiration
        await service.set("test_key", "test_value", expire=3600)

        mock_redis.set.assert_called_once_with("test_key", "test_value", ex=3600)

    @pytest.mark.asyncio
    async def test_cache_service_set_without_expiration(self):
        """Test CacheService.set stores value without TTL (Line 101)."""
        mock_redis = AsyncMock()
        service = CacheService(mock_redis)

        # Line 101: Set without expiration (ex=None)
        await service.set("test_key", "test_value", expire=None)

        mock_redis.set.assert_called_once_with("test_key", "test_value", ex=None)

    @pytest.mark.asyncio
    async def test_cache_service_delete(self):
        """Test CacheService.delete removes key (Lines 103-105)."""
        mock_redis = AsyncMock()
        service = CacheService(mock_redis)

        # Lines 103-105 executed
        await service.delete("test_key")

        mock_redis.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_cache_service_exists_returns_true(self):
        """Test CacheService.exists returns True for existing key (Lines 107-109)."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)
        service = CacheService(mock_redis)

        # Lines 107-109 executed: Key exists
        result = await service.exists("existing_key")

        assert result is True
        mock_redis.exists.assert_called_once_with("existing_key")

    @pytest.mark.asyncio
    async def test_cache_service_exists_returns_false(self):
        """Test CacheService.exists returns False for missing key (Line 109)."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)
        service = CacheService(mock_redis)

        # Line 109: bool(0) = False
        result = await service.exists("missing_key")

        assert result is False


class TestSessionService:
    """Tests for SessionService session management operations."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_SESSION_PREFIX", "session:")
    async def test_session_service_create_session(self):
        """Test SessionService.create_session stores refresh token (Lines 118-127)."""
        mock_redis = AsyncMock()
        service = SessionService(mock_redis)

        # Lines 118-127 executed: Create session with expiration
        await service.create_session("user123", "refresh_token_abc", expire_days=7)

        # Verify sadd called with prefixed key
        mock_redis.sadd.assert_called_once_with("session:user123", "refresh_token_abc")

        # Verify expire called with 7 days in seconds
        expected_seconds = 7 * 24 * 3600
        mock_redis.expire.assert_called_once_with("session:user123", expected_seconds)

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_SESSION_PREFIX", "session:")
    async def test_session_service_create_session_custom_expiry(self):
        """Test SessionService.create_session with custom expiry (Line 127)."""
        mock_redis = AsyncMock()
        service = SessionService(mock_redis)

        # Line 127: Custom expire_days
        await service.create_session("user123", "token", expire_days=14)

        # Verify 14 days in seconds
        expected_seconds = 14 * 24 * 3600
        mock_redis.expire.assert_called_once_with("session:user123", expected_seconds)

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_SESSION_PREFIX", "session:")
    async def test_session_service_get_sessions_returns_tokens(self):
        """Test SessionService.get_sessions returns all user tokens (Lines 129-133)."""
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={"token1", "token2", "token3"})
        service = SessionService(mock_redis)

        # Lines 129-133 executed
        result = await service.get_sessions("user123")

        assert result == {"token1", "token2", "token3"}
        mock_redis.smembers.assert_called_once_with("session:user123")

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_SESSION_PREFIX", "session:")
    async def test_session_service_get_sessions_returns_empty_set(self):
        """Test SessionService.get_sessions returns empty set (Line 133)."""
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value=set())
        service = SessionService(mock_redis)

        # Line 133: Empty set conversion
        result = await service.get_sessions("user_no_sessions")

        assert result == set()

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_SESSION_PREFIX", "session:")
    async def test_session_service_remove_session(self):
        """Test SessionService.remove_session removes specific token (Lines 135-138)."""
        mock_redis = AsyncMock()
        service = SessionService(mock_redis)

        # Lines 135-138 executed
        await service.remove_session("user123", "token_to_remove")

        mock_redis.srem.assert_called_once_with("session:user123", "token_to_remove")

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_SESSION_PREFIX", "session:")
    async def test_session_service_remove_all_sessions(self):
        """Test SessionService.remove_all_sessions deletes key (Lines 140-143)."""
        mock_redis = AsyncMock()
        service = SessionService(mock_redis)

        # Lines 140-143 executed: Delete entire key
        await service.remove_all_sessions("user123")

        mock_redis.delete.assert_called_once_with("session:user123")

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_SESSION_PREFIX", "session:")
    async def test_session_service_verify_refresh_token_returns_true(self):
        """Test SessionService.verify_refresh_token returns True (Lines 145-149)."""
        mock_redis = AsyncMock()
        mock_redis.sismember = AsyncMock(return_value=1)  # Token exists
        service = SessionService(mock_redis)

        # Lines 145-149 executed: Token exists
        result = await service.verify_refresh_token("user123", "valid_token")

        assert result is True
        mock_redis.sismember.assert_called_once_with("session:user123", "valid_token")

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_SESSION_PREFIX", "session:")
    async def test_session_service_verify_refresh_token_returns_false(self):
        """Test SessionService.verify_refresh_token returns False (Line 149)."""
        mock_redis = AsyncMock()
        mock_redis.sismember = AsyncMock(return_value=0)  # Token doesn't exist
        service = SessionService(mock_redis)

        # Line 149: bool(0) = False
        result = await service.verify_refresh_token("user123", "invalid_token")

        assert result is False

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_OAUTH_STATE_PREFIX", "oauth_state:")
    async def test_session_service_store_oauth_state(self):
        """Test SessionService.store_oauth_state stores JSON data (Lines 151-156)."""
        mock_redis = AsyncMock()
        service = SessionService(mock_redis)

        state_data = {"connector_type": "google", "redirect_uri": "http://localhost"}

        # Lines 151-156 executed: Store with JSON serialization
        await service.store_oauth_state("state_abc123", state_data, expire_minutes=5)

        # Verify setex called with JSON
        import json

        expected_json = json.dumps(state_data)
        expected_seconds = 5 * 60
        mock_redis.setex.assert_called_once_with(
            "oauth_state:state_abc123", expected_seconds, expected_json
        )

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_OAUTH_STATE_PREFIX", "oauth_state:")
    async def test_session_service_store_oauth_state_custom_expiry(self):
        """Test SessionService.store_oauth_state with custom expiry (Line 156)."""
        mock_redis = AsyncMock()
        service = SessionService(mock_redis)

        # Line 156: Custom expire_minutes
        await service.store_oauth_state("state", {"data": "test"}, expire_minutes=10)

        # Verify 10 minutes in seconds
        expected_seconds = 10 * 60
        call_args = mock_redis.setex.call_args[0]
        assert call_args[1] == expected_seconds

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_OAUTH_STATE_PREFIX", "oauth_state:")
    async def test_session_service_get_oauth_state_returns_data_and_deletes(self):
        """Test SessionService.get_oauth_state returns data and deletes (Lines 158-179)."""
        mock_redis = AsyncMock()
        import json

        state_data = {"connector_type": "google", "user_id": "user123"}
        mock_redis.get = AsyncMock(return_value=json.dumps(state_data))
        service = SessionService(mock_redis)

        # Lines 158-179 executed: Get and delete (single-use pattern)
        result = await service.get_oauth_state("state_abc123")

        # Verify data returned
        assert result == state_data

        # Verify get and delete called
        mock_redis.get.assert_called_once_with("oauth_state:state_abc123")
        mock_redis.delete.assert_called_once_with("oauth_state:state_abc123")

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_OAUTH_STATE_PREFIX", "oauth_state:")
    async def test_session_service_get_oauth_state_returns_none_when_missing(self):
        """Test SessionService.get_oauth_state returns None for missing state (Line 179)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        service = SessionService(mock_redis)

        # Line 179: Returns None when data is None
        result = await service.get_oauth_state("missing_state")

        assert result is None
        # Verify delete NOT called when state doesn't exist
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_OAUTH_STATE_PREFIX", "oauth_state:")
    async def test_session_service_delete_oauth_state(self):
        """Test SessionService.delete_oauth_state explicitly deletes (Lines 181-193)."""
        mock_redis = AsyncMock()
        service = SessionService(mock_redis)

        # Lines 181-193 executed: Explicit delete for error cleanup
        await service.delete_oauth_state("state_to_delete")

        mock_redis.delete.assert_called_once_with("oauth_state:state_to_delete")

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.REDIS_KEY_OAUTH_STATE_PREFIX", "oauth_state:")
    async def test_session_service_get_oauth_state_handles_json_parse(self):
        """Test SessionService.get_oauth_state parses complex JSON (Lines 172-177)."""
        mock_redis = AsyncMock()
        import json

        complex_data = {
            "connector_type": "google",
            "user_id": "user123",
            "redirect_uri": "http://localhost:3000/callback",
            "nested": {"key": "value"},
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(complex_data))
        service = SessionService(mock_redis)

        # Lines 172-177: JSON parsing with complex structure
        result = await service.get_oauth_state("state")

        assert result == complex_data
        assert result["nested"]["key"] == "value"
