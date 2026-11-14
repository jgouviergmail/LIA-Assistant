"""
Tests for HITLStore helper class.

Tests schema versioning, timestamp tracking, the write an invocation owns and
the read-only decoding of a legacy record.

A pending question is written and removed by the graph invocation that owns its
runtime, through one server-side script that checks the invocation's grant
(``write_runtime_string`` / ``delete_runtime_question``) -- never by a bare
``SET`` or ``DEL``. That script is proven on a real Redis
(``tests/integration/domains/conversations/test_hitl_runtime_authority.py``);
here the client's ``eval`` grants, and the tests read what the store composed
and what it refuses before anything is sent.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.conversation_execution import ExecutionRevoked
from src.core.field_names import FIELD_ACTIVITY_ID, FIELD_INTERRUPT_DATA, FIELD_RUN_ID
from src.domains.agents.utils.hitl_store import SCHEMA_VERSION, HITLStore
from tests.helpers.run_authority import unit_run_authority

OWNER = uuid4()
CONVERSATION = uuid4()
#: A pending question is keyed by its runtime: the thread of a root run.
RUNTIME = uuid4()
THREAD = str(RUNTIME)


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing; its fence script grants."""
    mock = MagicMock()
    mock.set = AsyncMock()
    mock.get = AsyncMock()
    mock.delete = AsyncMock()
    mock.exists = AsyncMock()
    mock.eval = AsyncMock(return_value=1)
    return mock


@pytest.fixture
def hitl_store(mock_redis):
    """HITLStore instance with mocked dependencies."""
    return HITLStore(redis_client=mock_redis, ttl_seconds=3600)


def fenced_write(mock_redis) -> tuple[dict, str]:
    """The record and the lifetime the store handed the fenced writer, once.

    Read by content, not by position: the script's argument layout belongs to
    the writer. The record is the one argument that is a versioned envelope; the
    lifetime travels last, as text.
    """
    mock_redis.eval.assert_awaited_once()
    sent = mock_redis.eval.await_args.args
    assert f"hitl_pending:{THREAD}" in sent
    records = [json.loads(arg) for arg in sent if isinstance(arg, str) and arg.startswith("{")]
    assert len(records) == 1
    return records[0], sent[-1]


class TestHITLStore:
    """Test suite for HITLStore helper."""

    async def test_save_interrupt_with_versioning(self, hitl_store, mock_redis):
        """Test saving interrupt data with schema versioning and timestamp."""
        # Arrange: the invocation that owns the runtime, asking on its own run
        with unit_run_authority(OWNER, CONVERSATION, RUNTIME) as authority:
            interrupt_data = {
                "action_requests": [{"tool": "search_contacts", "args": {"query": "test"}}],
                "review_configs": None,
                "count": 1,
                FIELD_RUN_ID: authority.admission.run_id,
            }

            # Act
            await hitl_store.save_interrupt(THREAD, interrupt_data)

        # Assert: one fenced write, under the runtime's key, never a bare SET
        saved_data, lifetime = fenced_write(mock_redis)
        mock_redis.set.assert_not_called()

        # Check versioned data structure
        assert saved_data["schema_version"] == SCHEMA_VERSION
        assert saved_data[FIELD_INTERRUPT_DATA] == interrupt_data
        # The invocation that wrote it: what lets its own cleanup, and no other, clear it
        assert saved_data[FIELD_ACTIVITY_ID] == str(authority.admission.activity_id)

        # Check TTL
        assert lifetime == "3600"

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

    async def test_get_interrupt_decodes_an_old_schema_record_without_writing(
        self, hitl_store, mock_redis
    ):
        """An old-schema record (plain dict) is read in the v1 shape, for the reader only.

        A read grants no authority over the runtime: the record is decoded and
        handed back, never rewritten, and its lifetime is not extended.
        """
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

        # Assert: the envelope's shape, with no timestamp the old record never carried
        assert result["schema_version"] == SCHEMA_VERSION
        assert result["interrupt_ts"] is None
        assert result[FIELD_INTERRUPT_DATA] == old_schema_data

        # Nothing is saved back to Redis
        mock_redis.set.assert_not_called()
        mock_redis.eval.assert_not_called()

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
        """Test deleting interrupt data: the owning invocation, through the fence."""
        # Act
        with unit_run_authority(OWNER, CONVERSATION, RUNTIME):
            await hitl_store.delete_interrupt(THREAD)

        # Assert: one fenced deletion of the runtime's key, never an unconditional DEL
        mock_redis.eval.assert_awaited_once()
        assert f"hitl_pending:{THREAD}" in mock_redis.eval.await_args.args
        mock_redis.delete.assert_not_called()

    async def test_a_question_is_written_and_removed_by_its_own_invocation_only(
        self, hitl_store, mock_redis
    ):
        """No invocation, or one that owns another runtime, sends nothing at all."""
        # Given: a question its run would be allowed to ask
        other_runtime = uuid4()

        # When/Then: outside any invocation
        with pytest.raises(ExecutionRevoked):
            await hitl_store.save_interrupt(THREAD, {FIELD_RUN_ID: "run_456"})
        with pytest.raises(ExecutionRevoked):
            await hitl_store.delete_interrupt(THREAD)

        # When/Then: under an invocation that owns ANOTHER runtime
        with unit_run_authority(OWNER, CONVERSATION, other_runtime) as authority:
            with pytest.raises(ExecutionRevoked):
                await hitl_store.save_interrupt(THREAD, {FIELD_RUN_ID: authority.admission.run_id})
            with pytest.raises(ExecutionRevoked):
                await hitl_store.delete_interrupt(THREAD)

        mock_redis.eval.assert_not_called()
        mock_redis.set.assert_not_called()
        mock_redis.delete.assert_not_called()

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

    @pytest.mark.parametrize("interrupt_data", [{}, {FIELD_RUN_ID: "another-run"}])
    async def test_save_interrupt_refuses_data_that_does_not_name_its_run(
        self, hitl_store, mock_redis, interrupt_data
    ):
        """Empty data, or another run's: a question is saved by the run that asked it."""
        # Act
        with unit_run_authority(OWNER, CONVERSATION, RUNTIME):
            with pytest.raises(ExecutionRevoked):
                await hitl_store.save_interrupt(THREAD, interrupt_data)

        # Assert: nothing was sent
        mock_redis.eval.assert_not_called()
        mock_redis.set.assert_not_called()

    async def test_save_interrupt_with_minimal_data(self, hitl_store, mock_redis):
        """Test saving interrupt with minimal data: the run that asks, nothing else."""
        # Act
        with unit_run_authority(OWNER, CONVERSATION, RUNTIME) as authority:
            interrupt_data = {FIELD_RUN_ID: authority.admission.run_id}
            await hitl_store.save_interrupt(THREAD, interrupt_data)

        # Assert
        saved_data, _ = fenced_write(mock_redis)
        assert saved_data[FIELD_INTERRUPT_DATA] == interrupt_data
        assert saved_data["schema_version"] == SCHEMA_VERSION
        assert "interrupt_ts" in saved_data

    async def test_ttl_configuration(self, mock_redis):
        """Test TTL configuration is passed correctly."""
        # Arrange
        custom_ttl = 7200  # 2 hours

        # Act
        store = HITLStore(redis_client=mock_redis, ttl_seconds=custom_ttl)
        with unit_run_authority(OWNER, CONVERSATION, RUNTIME) as authority:
            await store.save_interrupt(
                THREAD, {"test": "data", FIELD_RUN_ID: authority.admission.run_id}
            )

        # Assert
        _, lifetime = fenced_write(mock_redis)
        assert lifetime == str(custom_ttl)

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
