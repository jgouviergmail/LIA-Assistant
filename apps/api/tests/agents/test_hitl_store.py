"""
Tests for HITLStore helper class.

Tests schema versioning, timestamp tracking, and fallback migration.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.agents.utils.hitl_store import SCHEMA_VERSION, HITLStore


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    mock = MagicMock()
    mock.set = AsyncMock()
    mock.get = AsyncMock()
    mock.delete = AsyncMock()
    mock.exists = AsyncMock()
    return mock


@pytest.fixture
def hitl_store(mock_redis):
    """HITLStore instance with mocked dependencies."""
    return HITLStore(redis_client=mock_redis, ttl_seconds=3600)


class TestHITLStore:
    """Test suite for HITLStore helper."""

    async def test_save_interrupt_with_versioning(self, hitl_store, mock_redis):
        """Test saving interrupt data with schema versioning and timestamp."""
        # Arrange
        thread_id = "thread_123"
        interrupt_data = {
            "action_requests": [{"tool": "search_contacts", "args": {"query": "test"}}],
            "review_configs": None,
            "count": 1,
            "run_id": "run_456",
        }

        # Act
        await hitl_store.save_interrupt(thread_id, interrupt_data)

        # Assert
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args

        # Check key format
        assert call_args[0][0] == "hitl_pending:thread_123"

        # Check versioned data structure
        saved_json = call_args[0][1]
        saved_data = json.loads(saved_json)
        assert saved_data["schema_version"] == SCHEMA_VERSION
        assert "interrupt_ts" in saved_data
        assert saved_data["interrupt_data"] == interrupt_data

        # Check TTL
        assert call_args[1]["ex"] == 3600

        # Check timestamp format (ISO 8601)
        interrupt_ts = saved_data["interrupt_ts"]
        parsed_ts = datetime.fromisoformat(interrupt_ts)
        assert parsed_ts.tzinfo is not None  # Should be timezone-aware

    async def test_get_interrupt_with_new_schema(self, hitl_store, mock_redis):
        """Test retrieving interrupt data with new schema (v1)."""
        # Arrange
        thread_id = "thread_123"
        versioned_data = {
            "schema_version": 1,
            "interrupt_ts": "2025-01-31T10:00:00+00:00",
            "interrupt_data": {
                "action_requests": [{"tool": "search_contacts"}],
                "run_id": "run_456",
            },
        }
        mock_redis.get.return_value = json.dumps(versioned_data)

        # Act
        result = await hitl_store.get_interrupt(thread_id)

        # Assert
        assert result == versioned_data
        mock_redis.get.assert_called_once_with("hitl_pending:thread_123")

    async def test_get_interrupt_with_old_schema_migration(self, hitl_store, mock_redis):
        """Test automatic migration from old schema (plain dict) to v1."""
        # Arrange
        thread_id = "thread_123"
        old_schema_data = {
            # Old schema: plain dict without versioning
            "action_requests": [{"tool": "search_contacts"}],
            "review_configs": None,
            "run_id": "run_456",
        }
        mock_redis.get.return_value = json.dumps(old_schema_data)

        # Act
        result = await hitl_store.get_interrupt(thread_id)

        # Assert
        # Should migrate to new schema
        assert result["schema_version"] == SCHEMA_VERSION
        assert "interrupt_ts" in result
        assert result["interrupt_data"] == old_schema_data

        # Should save migrated version back to Redis
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "hitl_pending:thread_123"
        migrated_json = call_args[0][1]
        migrated_data = json.loads(migrated_json)
        assert migrated_data["schema_version"] == SCHEMA_VERSION

    async def test_get_interrupt_not_found(self, hitl_store, mock_redis):
        """Test retrieving interrupt when none exists."""
        # Arrange
        thread_id = "thread_123"
        mock_redis.get.return_value = None

        # Act
        result = await hitl_store.get_interrupt(thread_id)

        # Assert
        assert result is None

    async def test_delete_interrupt(self, hitl_store, mock_redis):
        """Test deleting interrupt data."""
        # Arrange
        thread_id = "thread_123"

        # Act
        await hitl_store.delete_interrupt(thread_id)

        # Assert
        mock_redis.delete.assert_called_once_with("hitl_pending:thread_123")

    async def test_has_interrupt_exists(self, hitl_store, mock_redis):
        """Test checking if interrupt exists (positive case)."""
        # Arrange
        thread_id = "thread_123"
        mock_redis.exists.return_value = 1

        # Act
        result = await hitl_store.has_interrupt(thread_id)

        # Assert
        assert result is True

    async def test_has_interrupt_not_exists(self, hitl_store, mock_redis):
        """Test checking if interrupt exists (negative case)."""
        # Arrange
        thread_id = "thread_123"
        mock_redis.exists.return_value = 0

        # Act
        result = await hitl_store.has_interrupt(thread_id)

        # Assert
        assert result is False

    def test_schema_version_constant(self):
        """Test schema version constant is defined."""
        assert SCHEMA_VERSION == 1

    async def test_save_interrupt_with_empty_data(self, hitl_store, mock_redis):
        """Test saving interrupt with minimal/empty data."""
        # Arrange
        thread_id = "thread_123"
        interrupt_data = {}

        # Act
        await hitl_store.save_interrupt(thread_id, interrupt_data)

        # Assert
        mock_redis.set.assert_called_once()
        saved_json = mock_redis.set.call_args[0][1]
        saved_data = json.loads(saved_json)
        assert saved_data["interrupt_data"] == {}
        assert saved_data["schema_version"] == SCHEMA_VERSION
        assert "interrupt_ts" in saved_data

    async def test_ttl_configuration(self, mock_redis):
        """Test TTL configuration is passed correctly."""
        # Arrange
        custom_ttl = 7200  # 2 hours

        # Act
        store = HITLStore(redis_client=mock_redis, ttl_seconds=custom_ttl)
        await store.save_interrupt("thread_123", {"test": "data"})

        # Assert
        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == custom_ttl

    async def test_migration_preserves_data_integrity(self, hitl_store, mock_redis):
        """Test old schema migration preserves all data fields."""
        # Arrange
        thread_id = "thread_123"
        old_data = {
            "action_requests": [
                {"name": "search_contacts", "args": {"query": "test"}},
                {"name": "get_contact_details", "args": {"contact_id": "123"}},
            ],
            "review_configs": {"confidence_threshold": 0.7},
            "count": 2,
            "run_id": "run_789",
        }
        mock_redis.get.return_value = json.dumps(old_data)

        # Act
        result = await hitl_store.get_interrupt(thread_id)

        # Assert
        # All fields from old data should be preserved in interrupt_data
        assert result["interrupt_data"] == old_data
        assert result["interrupt_data"]["action_requests"] == old_data["action_requests"]
        assert result["interrupt_data"]["review_configs"] == old_data["review_configs"]
        assert result["interrupt_data"]["count"] == old_data["count"]
        assert result["interrupt_data"]["run_id"] == old_data["run_id"]
