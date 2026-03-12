"""
Unit tests for HITL store helper.

Phase: Session 10 - Tests Quick Wins (utils/hitl_store)
Created: 2025-11-20

Focus: HITLStore Redis operations, schema versioning, timestamp tracking
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.utils.hitl_store import SCHEMA_VERSION, HITLStore


class TestHITLStoreInit:
    """Tests for HITLStore initialization."""

    def test_init_with_redis_client(self):
        """Test HITLStore initialization with Redis client."""
        mock_redis = AsyncMock()
        ttl = 3600

        store = HITLStore(redis_client=mock_redis, ttl_seconds=ttl)

        assert store.redis is mock_redis
        assert store.ttl_seconds == ttl

    def test_init_with_custom_ttl(self):
        """Test HITLStore initialization with custom TTL."""
        mock_redis = AsyncMock()
        custom_ttl = 7200

        store = HITLStore(redis_client=mock_redis, ttl_seconds=custom_ttl)

        assert store.ttl_seconds == custom_ttl


class TestSaveInterrupt:
    """Tests for save_interrupt() method."""

    @pytest.mark.asyncio
    async def test_save_interrupt_success(self):
        """Test saving interrupt data successfully."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        thread_id = "thread_123"
        interrupt_data = {
            "action_requests": [{"action": "edit_contacts"}],
            "review_configs": None,
            "run_id": "run_456",
        }

        await store.save_interrupt(thread_id, interrupt_data)

        # Verify Redis set called
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args

        # Verify key
        assert call_args[0][0] == "hitl_pending:thread_123"

        # Verify data structure
        saved_data = json.loads(call_args[0][1])
        assert saved_data["schema_version"] == SCHEMA_VERSION
        assert "interrupt_ts" in saved_data
        assert saved_data["interrupt_data"] == interrupt_data

        # Verify TTL
        assert call_args[1]["ex"] == 3600

    @pytest.mark.asyncio
    async def test_save_interrupt_timestamp_format(self):
        """Test that save_interrupt adds ISO format timestamp."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        with patch("src.domains.agents.utils.hitl_store.datetime") as mock_datetime:
            # Mock datetime.now()
            mock_now = datetime(2025, 11, 20, 10, 30, 45, tzinfo=UTC)
            mock_datetime.now.return_value = mock_now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            await store.save_interrupt("thread_123", {"test": "data"})

            # Verify timestamp in saved data
            saved_json = mock_redis.set.call_args[0][1]
            saved_data = json.loads(saved_json)
            assert saved_data["interrupt_ts"] == "2025-11-20T10:30:45+00:00"

    @pytest.mark.asyncio
    async def test_save_interrupt_with_complex_data(self):
        """Test saving interrupt with complex nested data."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        complex_data = {
            "action_requests": [
                {"action": "create", "args": {"name": "John", "email": "john@test.com"}},
                {"action": "update", "args": {"id": 123, "fields": ["name", "email"]}},
            ],
            "review_configs": {"require_approval": True, "timeout": 300},
            "metadata": {"user_id": "user_789", "session_id": "session_456"},
        }

        await store.save_interrupt("thread_123", complex_data)

        # Verify complex data serialized correctly
        saved_json = mock_redis.set.call_args[0][1]
        saved_data = json.loads(saved_json)
        assert saved_data["interrupt_data"] == complex_data


class TestGetInterrupt:
    """Tests for get_interrupt() method."""

    @pytest.mark.asyncio
    async def test_get_interrupt_success(self):
        """Test retrieving existing interrupt data."""
        mock_redis = AsyncMock()
        stored_data = {
            "schema_version": SCHEMA_VERSION,
            "interrupt_ts": "2025-11-20T10:30:00+00:00",
            "interrupt_data": {"action": "test"},
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(stored_data))
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.get_interrupt("thread_123")

        # Verify Redis get called
        mock_redis.get.assert_called_once_with("hitl_pending:thread_123")

        # Verify returned data
        assert result == stored_data

    @pytest.mark.asyncio
    async def test_get_interrupt_not_found(self):
        """Test retrieving non-existent interrupt returns None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.get_interrupt("thread_123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_interrupt_invalid_json(self):
        """Test retrieving interrupt with invalid JSON returns None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="invalid json{")
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.get_interrupt("thread_123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_interrupt_migrates_old_schema(self):
        """Test that old schema (plain dict) is migrated to v1."""
        mock_redis = AsyncMock()
        # Old schema: plain dict without schema_version
        old_data = {"action": "test", "run_id": "run_123"}
        mock_redis.get = AsyncMock(return_value=json.dumps(old_data))
        mock_redis.set = AsyncMock()
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.get_interrupt("thread_123")

        # Verify returned data is migrated
        assert result["schema_version"] == SCHEMA_VERSION
        assert "interrupt_ts" in result
        assert result["interrupt_data"] == old_data

        # Verify migrated data saved back to Redis
        mock_redis.set.assert_called_once()
        saved_key = mock_redis.set.call_args[0][0]
        saved_json = mock_redis.set.call_args[0][1]
        assert saved_key == "hitl_pending:thread_123"

        saved_data = json.loads(saved_json)
        assert saved_data["schema_version"] == SCHEMA_VERSION
        assert saved_data["interrupt_data"] == old_data

    @pytest.mark.asyncio
    async def test_get_interrupt_preserves_ttl_on_migration(self):
        """Test that TTL is preserved when migrating old schema."""
        mock_redis = AsyncMock()
        old_data = {"action": "test"}
        mock_redis.get = AsyncMock(return_value=json.dumps(old_data))
        mock_redis.set = AsyncMock()
        store = HITLStore(redis_client=mock_redis, ttl_seconds=7200)

        await store.get_interrupt("thread_123")

        # Verify TTL preserved on migration
        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs["ex"] == 7200


class TestDeleteInterrupt:
    """Tests for delete_interrupt() method."""

    @pytest.mark.asyncio
    async def test_delete_interrupt_success(self):
        """Test deleting interrupt data."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        await store.delete_interrupt("thread_123")

        # Verify Redis delete called
        mock_redis.delete.assert_called_once_with("hitl_pending:thread_123")


class TestClearInterrupt:
    """Tests for clear_interrupt() method."""

    @pytest.mark.asyncio
    async def test_clear_interrupt_calls_delete(self):
        """Test clear_interrupt is alias for delete_interrupt."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        await store.clear_interrupt("thread_123")

        # Verify Redis delete called (through delete_interrupt)
        mock_redis.delete.assert_called_once_with("hitl_pending:thread_123")


class TestHasInterrupt:
    """Tests for has_interrupt() method."""

    @pytest.mark.asyncio
    async def test_has_interrupt_true(self):
        """Test has_interrupt returns True when data exists."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.has_interrupt("thread_123")

        # Verify Redis exists called
        mock_redis.exists.assert_called_once_with("hitl_pending:thread_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_has_interrupt_false(self):
        """Test has_interrupt returns False when data doesn't exist."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.has_interrupt("thread_123")

        assert result is False


class TestSetRequestTimestamp:
    """Tests for set_request_timestamp() method."""

    @pytest.mark.asyncio
    async def test_set_request_timestamp_success(self):
        """Test storing request timestamp."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        timestamp = 1700000000.123
        await store.set_request_timestamp("thread_123", timestamp)

        # Verify Redis set called
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args

        # Verify key and value
        assert call_args[0][0] == "hitl:request_ts:thread_123"
        assert call_args[0][1] == str(timestamp)

        # Verify TTL
        assert call_args[1]["ex"] == 3600

    @pytest.mark.asyncio
    async def test_set_request_timestamp_with_custom_ttl(self):
        """Test storing timestamp with custom TTL."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        store = HITLStore(redis_client=mock_redis, ttl_seconds=1800)

        await store.set_request_timestamp("thread_123", 1700000000.0)

        # Verify custom TTL used
        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs["ex"] == 1800


class TestGetRequestTimestamp:
    """Tests for get_request_timestamp() method."""

    @pytest.mark.asyncio
    async def test_get_request_timestamp_success(self):
        """Test retrieving request timestamp."""
        mock_redis = AsyncMock()
        timestamp = 1700000000.123
        mock_redis.get = AsyncMock(return_value=str(timestamp))
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.get_request_timestamp("thread_123")

        # Verify Redis get called
        mock_redis.get.assert_called_once_with("hitl:request_ts:thread_123")

        # Verify timestamp parsed correctly
        assert result == timestamp

    @pytest.mark.asyncio
    async def test_get_request_timestamp_not_found(self):
        """Test retrieving non-existent timestamp returns None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.get_request_timestamp("thread_123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_request_timestamp_invalid_format(self):
        """Test retrieving timestamp with invalid format returns None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="not_a_number")
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.get_request_timestamp("thread_123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_request_timestamp_empty_string(self):
        """Test retrieving empty string timestamp returns None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="")
        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        result = await store.get_request_timestamp("thread_123")

        assert result is None


class TestSchemaVersion:
    """Tests for schema version constant."""

    def test_schema_version_is_one(self):
        """Test that SCHEMA_VERSION constant is 1."""
        assert SCHEMA_VERSION == 1


class TestIntegration:
    """Integration tests for HITLStore lifecycle."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_cycle(self):
        """Test complete save → retrieve → delete cycle."""
        mock_redis = AsyncMock()
        stored_value = None

        # Mock Redis behavior
        async def mock_set(key, value, ex):
            nonlocal stored_value
            stored_value = value

        async def mock_get(key):
            return stored_value

        async def mock_delete(key):
            nonlocal stored_value
            stored_value = None

        mock_redis.set = mock_set
        mock_redis.get = mock_get
        mock_redis.delete = mock_delete

        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        # Save
        interrupt_data = {"action": "test", "args": {"id": 123}}
        await store.save_interrupt("thread_123", interrupt_data)

        # Retrieve
        retrieved = await store.get_interrupt("thread_123")
        assert retrieved["schema_version"] == SCHEMA_VERSION
        assert retrieved["interrupt_data"] == interrupt_data

        # Delete
        await store.delete_interrupt("thread_123")

        # Verify deleted
        deleted_result = await store.get_interrupt("thread_123")
        assert deleted_result is None

    @pytest.mark.asyncio
    async def test_timestamp_tracking_cycle(self):
        """Test complete timestamp set → get cycle."""
        mock_redis = AsyncMock()
        stored_ts = None

        # Mock Redis behavior
        async def mock_set(key, value, ex):
            nonlocal stored_ts
            stored_ts = value

        async def mock_get(key):
            return stored_ts

        mock_redis.set = mock_set
        mock_redis.get = mock_get

        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        # Set timestamp
        timestamp = 1700000000.456
        await store.set_request_timestamp("thread_123", timestamp)

        # Get timestamp
        retrieved_ts = await store.get_request_timestamp("thread_123")
        assert retrieved_ts == timestamp

    @pytest.mark.asyncio
    async def test_schema_migration_integration(self):
        """Test old schema migration works end-to-end."""
        mock_redis = AsyncMock()
        stored_value = None

        # Mock Redis behavior
        async def mock_set(key, value, ex):
            nonlocal stored_value
            stored_value = value

        async def mock_get(key):
            return stored_value

        mock_redis.set = mock_set
        mock_redis.get = mock_get

        store = HITLStore(redis_client=mock_redis, ttl_seconds=3600)

        # Simulate old schema data in Redis
        old_data = {"action": "legacy_action", "run_id": "run_old"}
        stored_value = json.dumps(old_data)

        # Retrieve (should trigger migration)
        retrieved = await store.get_interrupt("thread_123")

        # Verify migrated
        assert retrieved["schema_version"] == SCHEMA_VERSION
        assert retrieved["interrupt_data"] == old_data

        # Verify stored value updated with new schema
        stored_parsed = json.loads(stored_value)
        assert stored_parsed["schema_version"] == SCHEMA_VERSION
        assert stored_parsed["interrupt_data"] == old_data
