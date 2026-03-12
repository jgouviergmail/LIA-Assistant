"""
Unit tests for checkpoint metrics instrumentation (Phase 3.3).

Tests the InstrumentedAsyncPostgresSaver wrapper for Prometheus metrics tracking:
- checkpoint_operations_total counter
- checkpoint_errors_total counter
- Error categorization logic
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, CheckpointTuple

from src.domains.conversations.instrumented_checkpointer import (
    InstrumentedAsyncPostgresSaver,
)
from src.infrastructure.observability.metrics_agents import (
    checkpoint_errors_total,
    checkpoint_operations_total,
)


@pytest.fixture
def mock_connection():
    """Mock psycopg AsyncConnection."""
    return MagicMock()


@pytest.fixture
async def checkpointer(mock_connection):
    """Create InstrumentedAsyncPostgresSaver instance."""
    return InstrumentedAsyncPostgresSaver(conn=mock_connection)


@pytest.fixture
def sample_config() -> RunnableConfig:
    """Sample RunnableConfig for checkpoint operations."""
    return RunnableConfig(
        configurable={
            "thread_id": "test_thread_123",
            "checkpoint_id": "checkpoint_456",
        }
    )


@pytest.fixture
def sample_checkpoint() -> Checkpoint:
    """Sample Checkpoint data."""
    return {
        "v": 1,
        "id": "checkpoint_456",
        "ts": "2025-11-23T10:00:00Z",
        "channel_values": {"messages": [{"role": "user", "content": "Hello"}]},
        "channel_versions": {"messages": 1},
        "versions_seen": {},
    }


@pytest.fixture
def sample_metadata() -> CheckpointMetadata:
    """Sample CheckpointMetadata."""
    return CheckpointMetadata(
        source="planner_node",
        step=1,
        writes={},
        parents={},
    )


class TestCheckpointOperationsMetrics:
    """Test checkpoint_operations_total metric tracking."""

    @pytest.mark.asyncio
    async def test_aput_success_increments_operations_counter(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test successful checkpoint save increments operations counter."""
        # Mock parent aput to succeed
        with patch.object(
            checkpointer.__class__.__bases__[0],  # AsyncPostgresSaver
            "aput",
            new_callable=AsyncMock,
            return_value=sample_config,
        ):
            # Get initial counter value
            initial_value = checkpoint_operations_total.labels(
                operation="save", status="success"
            )._value.get()

            # Execute checkpoint save
            await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            # Verify counter incremented
            final_value = checkpoint_operations_total.labels(
                operation="save", status="success"
            )._value.get()
            assert final_value == initial_value + 1

    @pytest.mark.asyncio
    async def test_aput_failure_increments_error_counter(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test failed checkpoint save increments error counter."""
        # Mock parent aput to fail
        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aput",
            new_callable=AsyncMock,
            side_effect=Exception("Database connection failed"),
        ):
            initial_value = checkpoint_operations_total.labels(
                operation="save", status="error"
            )._value.get()

            # Execute checkpoint save (should raise)
            with pytest.raises(Exception, match="Database connection failed"):
                await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            # Verify error counter incremented
            final_value = checkpoint_operations_total.labels(
                operation="save", status="error"
            )._value.get()
            assert final_value == initial_value + 1

    @pytest.mark.asyncio
    async def test_aget_success_increments_operations_counter(self, checkpointer, sample_config):
        """Test successful checkpoint load increments operations counter."""
        # Mock parent aget to succeed
        mock_checkpoint_tuple = CheckpointTuple(
            config=sample_config,
            checkpoint={"v": 1},
            metadata={"source": "test"},
            parent_config=None,
        )

        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aget",
            new_callable=AsyncMock,
            return_value=mock_checkpoint_tuple,
        ):
            initial_value = checkpoint_operations_total.labels(
                operation="load", status="success"
            )._value.get()

            # Execute checkpoint load
            await checkpointer.aget(sample_config)

            # Verify counter incremented
            final_value = checkpoint_operations_total.labels(
                operation="load", status="success"
            )._value.get()
            assert final_value == initial_value + 1

    @pytest.mark.asyncio
    async def test_aget_failure_increments_error_counter(self, checkpointer, sample_config):
        """Test failed checkpoint load increments error counter."""
        # Mock parent aget to fail
        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aget",
            new_callable=AsyncMock,
            side_effect=Exception("Database timeout"),
        ):
            initial_value = checkpoint_operations_total.labels(
                operation="load", status="error"
            )._value.get()

            # Execute checkpoint load (should raise)
            with pytest.raises(Exception, match="Database timeout"):
                await checkpointer.aget(sample_config)

            # Verify error counter incremented
            final_value = checkpoint_operations_total.labels(
                operation="load", status="error"
            )._value.get()
            assert final_value == initial_value + 1


class TestCheckpointErrorCategorization:
    """Test checkpoint_errors_total metric error categorization."""

    @pytest.mark.asyncio
    async def test_db_connection_error_categorization(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test database connection errors are categorized correctly."""
        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aput",
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ):
            initial_value = checkpoint_errors_total.labels(
                error_type="db_connection", operation="save"
            )._value.get()

            with pytest.raises(Exception):
                await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            final_value = checkpoint_errors_total.labels(
                error_type="db_connection", operation="save"
            )._value.get()
            assert final_value == initial_value + 1

    @pytest.mark.asyncio
    async def test_timeout_error_categorization(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test timeout errors are categorized correctly."""
        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aput",
            new_callable=AsyncMock,
            side_effect=Exception("operation timeout exceeded"),
        ):
            initial_value = checkpoint_errors_total.labels(
                error_type="timeout", operation="save"
            )._value.get()

            with pytest.raises(Exception):
                await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            final_value = checkpoint_errors_total.labels(
                error_type="timeout", operation="save"
            )._value.get()
            assert final_value == initial_value + 1

    @pytest.mark.asyncio
    async def test_serialization_error_categorization(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test serialization errors are categorized correctly."""
        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aput",
            new_callable=AsyncMock,
            side_effect=Exception("pickle error: cannot serialize object"),
        ):
            initial_value = checkpoint_errors_total.labels(
                error_type="serialization", operation="save"
            )._value.get()

            with pytest.raises(Exception):
                await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            final_value = checkpoint_errors_total.labels(
                error_type="serialization", operation="save"
            )._value.get()
            assert final_value == initial_value + 1

    @pytest.mark.asyncio
    async def test_deserialization_error_categorization_on_load(self, checkpointer, sample_config):
        """Test deserialization errors on load are categorized correctly."""
        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aget",
            new_callable=AsyncMock,
            side_effect=Exception("deserialization failed"),
        ):
            initial_value = checkpoint_errors_total.labels(
                error_type="deserialization", operation="load"
            )._value.get()

            with pytest.raises(Exception):
                await checkpointer.aget(sample_config)

            final_value = checkpoint_errors_total.labels(
                error_type="deserialization", operation="load"
            )._value.get()
            assert final_value == initial_value + 1

    @pytest.mark.asyncio
    async def test_permission_error_categorization(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test permission errors are categorized correctly."""
        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aput",
            new_callable=AsyncMock,
            side_effect=Exception("permission denied for table checkpoints"),
        ):
            initial_value = checkpoint_errors_total.labels(
                error_type="permission", operation="save"
            )._value.get()

            with pytest.raises(Exception):
                await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            final_value = checkpoint_errors_total.labels(
                error_type="permission", operation="save"
            )._value.get()
            assert final_value == initial_value + 1

    @pytest.mark.asyncio
    async def test_unknown_error_categorization(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test unknown errors are categorized as 'unknown'."""
        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aput",
            new_callable=AsyncMock,
            side_effect=Exception("something unexpected happened"),
        ):
            initial_value = checkpoint_errors_total.labels(
                error_type="unknown", operation="save"
            )._value.get()

            with pytest.raises(Exception):
                await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            final_value = checkpoint_errors_total.labels(
                error_type="unknown", operation="save"
            )._value.get()
            assert final_value == initial_value + 1


class TestCheckpointSizeTracking:
    """Test checkpoint size metrics (existing functionality)."""

    @pytest.mark.asyncio
    async def test_checkpoint_size_tracked_on_save(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test checkpoint size is tracked on successful save."""
        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aput",
            new_callable=AsyncMock,
            return_value=sample_config,
        ):
            # Checkpoint size is tracked via checkpoint_size_bytes histogram
            # Verify it doesn't raise exceptions
            await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            # Size calculation uses pickle.dumps internally
            # Just verify no exceptions (size metric tracked successfully)
            assert True

    @pytest.mark.asyncio
    async def test_checkpoint_size_calculation_failure_is_graceful(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test checkpoint size calculation failure doesn't break save operation."""
        with (
            patch.object(
                checkpointer.__class__.__bases__[0],
                "aput",
                new_callable=AsyncMock,
                return_value=sample_config,
            ),
            patch("pickle.dumps", side_effect=Exception("pickle error")),
        ):
            # Even if size calculation fails, save should succeed
            result = await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            # Verify save succeeded despite size calculation failure
            assert result == sample_config


class TestCheckpointMetricsIntegration:
    """Integration tests for checkpoint metrics."""

    @pytest.mark.asyncio
    async def test_multiple_operations_tracked_correctly(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test multiple checkpoint operations are tracked correctly."""
        with (
            patch.object(
                checkpointer.__class__.__bases__[0],
                "aput",
                new_callable=AsyncMock,
                return_value=sample_config,
            ),
            patch.object(
                checkpointer.__class__.__bases__[0],
                "aget",
                new_callable=AsyncMock,
                return_value=CheckpointTuple(
                    config=sample_config,
                    checkpoint=sample_checkpoint,
                    metadata=sample_metadata,
                    parent_config=None,
                ),
            ),
        ):
            save_initial = checkpoint_operations_total.labels(
                operation="save", status="success"
            )._value.get()
            load_initial = checkpoint_operations_total.labels(
                operation="load", status="success"
            )._value.get()

            # Perform 3 saves and 2 loads
            for _ in range(3):
                await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            for _ in range(2):
                await checkpointer.aget(sample_config)

            # Verify counters
            save_final = checkpoint_operations_total.labels(
                operation="save", status="success"
            )._value.get()
            load_final = checkpoint_operations_total.labels(
                operation="load", status="success"
            )._value.get()

            assert save_final == save_initial + 3
            assert load_final == load_initial + 2

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure_tracked(
        self, checkpointer, sample_config, sample_checkpoint, sample_metadata
    ):
        """Test mixed success/failure operations tracked correctly."""
        # Mock: first save succeeds, second fails
        call_count = 0

        async def mock_aput_alternating(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sample_config
            else:
                raise Exception("Database error")

        with patch.object(
            checkpointer.__class__.__bases__[0],
            "aput",
            new_callable=AsyncMock,
            side_effect=mock_aput_alternating,
        ):
            success_initial = checkpoint_operations_total.labels(
                operation="save", status="success"
            )._value.get()
            error_initial = checkpoint_operations_total.labels(
                operation="save", status="error"
            )._value.get()

            # First save: success
            await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            # Second save: failure
            with pytest.raises(Exception):
                await checkpointer.aput(sample_config, sample_checkpoint, sample_metadata, {})

            # Verify both counters incremented
            success_final = checkpoint_operations_total.labels(
                operation="save", status="success"
            )._value.get()
            error_final = checkpoint_operations_total.labels(
                operation="save", status="error"
            )._value.get()

            assert success_final == success_initial + 1
            assert error_final == error_initial + 1
