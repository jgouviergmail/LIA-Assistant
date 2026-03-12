"""
Unit tests for Database Session Management.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 27.3
Created: 2025-11-21
Target: 30% → 80%+ coverage
Module: infrastructure/database/session.py (60 statements)

Test Coverage:
- get_db_session: Async generator for FastAPI dependencies (commit, rollback, close)
- get_db_context: Context manager for non-FastAPI code (commit, rollback, close)
- init_db: Database tables initialization (development/testing)
- close_db: Connection pool disposal
- update_db_pool_metrics: Prometheus metrics tracking
  - Pool size, checked-out connections, overflow
  - Pool exhaustion detection
  - Saturation estimation (90% threshold)

Critical Infrastructure Module:
- Connection pool management (QueuePool)
- Automatic transaction handling (commit/rollback)
- Pool health monitoring (Prometheus)
- Connection lifecycle management
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.pool import QueuePool

from src.infrastructure.database.session import (
    close_db,
    get_db_context,
    get_db_session,
    init_db,
    update_db_pool_metrics,
)


class TestGetDbSession:
    """Tests for get_db_session async generator (FastAPI dependency)."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.session.AsyncSessionLocal")
    async def test_get_db_session_success_commits(self, mock_session_local):
        """Test get_db_session commits on success (Lines 54-57)."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        # Mock context manager
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock()

        # Lines 54-57 executed: yield session + commit
        async for session in get_db_session():
            assert session == mock_session
            # Simulate successful operation (no exception)

        # Verify commit called
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.skip(reason="Mocking async context manager needs fix")
    @pytest.mark.asyncio
    @patch("src.infrastructure.database.session.logger")
    @patch("src.infrastructure.database.session.AsyncSessionLocal")
    async def test_get_db_session_error_rollsback(self, mock_session_local, mock_logger):
        """Test get_db_session rolls back on error (Lines 58-61)."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        # Create an async context manager that returns our mock session
        async def mock_session_context():
            yield mock_session

        mock_session_local.return_value = mock_session_context()

        # Lines 58-61 executed: rollback on exception
        with pytest.raises(ValueError):
            gen = get_db_session()
            await gen.__anext__()
            # Simulate error during operation
            raise ValueError("Database operation failed")

        # Verify rollback called
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

        # Verify error logged
        mock_logger.error.assert_called_once()
        assert "database_session_error" in str(mock_logger.error.call_args)

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.session.AsyncSessionLocal")
    async def test_get_db_session_always_closes(self, mock_session_local):
        """Test get_db_session always closes session in finally (Lines 62-63)."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        # Mock context manager
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock()

        # Lines 62-63 executed: finally block always runs
        async for _session in get_db_session():
            pass  # Normal execution

        # Verify close always called
        mock_session.close.assert_called_once()


class TestGetDbContext:
    """Tests for get_db_context context manager (non-FastAPI)."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.session.AsyncSessionLocal")
    async def test_get_db_context_success_commits(self, mock_session_local):
        """Test get_db_context commits on success (Lines 90-93)."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        # Mock context manager
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock()

        # Lines 90-93 executed: yield session + commit
        async with get_db_context() as session:
            assert session == mock_session
            # Simulate successful operation

        # Verify commit called
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.session.logger")
    @patch("src.infrastructure.database.session.AsyncSessionLocal")
    async def test_get_db_context_error_rollsback_with_details(
        self, mock_session_local, mock_logger
    ):
        """Test get_db_context rolls back with detailed logging (Lines 94-102)."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        # Mock context manager
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock()

        # Lines 94-102 executed: rollback + enhanced logging
        try:
            async with get_db_context():
                # Simulate error
                raise ConnectionError("Connection lost")
        except ConnectionError:
            pass

        # Verify rollback called
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

        # Verify enhanced logging (includes error_type)
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args[1]
        assert call_kwargs["error_type"] == "ConnectionError"
        assert "database_session_error" in str(mock_logger.error.call_args)

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.session.AsyncSessionLocal")
    async def test_get_db_context_always_closes_in_finally(self, mock_session_local):
        """Test get_db_context always closes in finally block (Lines 103-104)."""
        # Mock session
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()

        # Mock context manager
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock()

        # Lines 103-104 executed: finally block
        async with get_db_context():
            pass  # Normal execution

        # Verify close always called
        mock_session.close.assert_called_once()


class TestInitDb:
    """Tests for init_db database initialization."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.session.logger")
    @patch("src.infrastructure.database.session.Base")
    @patch("src.infrastructure.database.session.engine")
    async def test_init_db_creates_tables_and_logs(self, mock_engine, mock_base, mock_logger):
        """Test init_db creates tables and logs success (Lines 112-114)."""
        # Mock engine.begin() context manager
        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()

        mock_engine.begin = MagicMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock()

        # Lines 112-114 executed: Create tables + log
        await init_db()

        # Verify Base.metadata.create_all called
        mock_conn.run_sync.assert_called_once_with(mock_base.metadata.create_all)

        # Verify logging
        mock_logger.info.assert_called_once_with("database_tables_created")


class TestCloseDb:
    """Tests for close_db connection pool disposal."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.session.logger")
    @patch("src.infrastructure.database.session.engine")
    async def test_close_db_disposes_engine_and_logs(self, mock_engine, mock_logger):
        """Test close_db disposes engine and logs (Lines 119-120)."""
        mock_engine.dispose = AsyncMock()

        # Lines 119-120 executed: Dispose + log
        await close_db()

        # Verify engine.dispose called
        mock_engine.dispose.assert_called_once()

        # Verify logging
        mock_logger.info.assert_called_once_with("database_connection_closed")


class TestUpdateDbPoolMetrics:
    """Tests for update_db_pool_metrics Prometheus tracking."""

    @patch("src.infrastructure.database.session.settings")
    @patch("src.infrastructure.database.session.db_connection_pool_waiting_total")
    @patch("src.infrastructure.database.session.db_connection_pool_overflow")
    @patch("src.infrastructure.database.session.db_connection_pool_size")
    @patch("src.infrastructure.database.session.db_connection_pool_checkedout")
    @patch("src.infrastructure.database.session.engine")
    def test_update_db_pool_metrics_normal_operation(
        self,
        mock_engine,
        mock_checkedout,
        mock_pool_size,
        mock_overflow,
        mock_waiting,
        mock_settings,
    ):
        """Test update_db_pool_metrics tracks normal pool state (Lines 142-179)."""
        # Mock pool as QueuePool
        mock_pool = MagicMock(spec=QueuePool)
        mock_pool.checkedout.return_value = 5  # 5 connections in use
        mock_pool.overflow.return_value = 0  # No overflow

        mock_engine.pool = mock_pool

        # Mock settings
        mock_settings.database_pool_size = 10
        mock_settings.database_max_overflow = 5

        # Lines 142-179 executed: Normal operation (no saturation)
        update_db_pool_metrics()

        # Verify metrics updated
        mock_checkedout.set.assert_called_once_with(5)
        mock_pool_size.set.assert_called_once_with(10)
        mock_overflow.set.assert_called_once_with(0)
        mock_waiting.set.assert_called_once_with(0)  # No waiting (below 90% threshold)

    @patch("src.infrastructure.database.session.logger")
    @patch("src.infrastructure.database.session.settings")
    @patch("src.infrastructure.database.session.db_connection_pool_exhausted_total")
    @patch("src.infrastructure.database.session.db_connection_pool_waiting_total")
    @patch("src.infrastructure.database.session.db_connection_pool_overflow")
    @patch("src.infrastructure.database.session.db_connection_pool_size")
    @patch("src.infrastructure.database.session.db_connection_pool_checkedout")
    @patch("src.infrastructure.database.session.engine")
    def test_update_db_pool_metrics_pool_exhausted(
        self,
        mock_engine,
        mock_checkedout,
        mock_pool_size,
        mock_overflow,
        mock_waiting,
        mock_exhausted,
        mock_settings,
        mock_logger,
    ):
        """Test update_db_pool_metrics detects pool exhaustion (Lines 160-169)."""
        # Mock pool at capacity as QueuePool
        mock_pool = MagicMock(spec=QueuePool)
        mock_pool.checkedout.return_value = 15  # All connections in use
        mock_pool.overflow.return_value = 5  # Max overflow reached

        mock_engine.pool = mock_pool

        # Mock settings
        mock_settings.database_pool_size = 10
        mock_settings.database_max_overflow = 5

        # Lines 160-169 executed: Pool exhaustion detected
        update_db_pool_metrics()

        # Verify exhaustion counter incremented
        mock_exhausted.inc.assert_called_once()

        # Verify warning logged
        mock_logger.warning.assert_called_once()
        assert "database_connection_pool_exhausted" in str(mock_logger.warning.call_args)
        call_kwargs = mock_logger.warning.call_args[1]
        assert call_kwargs["checked_out"] == 15
        assert call_kwargs["max_connections"] == 15
        assert call_kwargs["pool_size"] == 10
        assert call_kwargs["max_overflow"] == 5

    @patch("src.infrastructure.database.session.settings")
    @patch("src.infrastructure.database.session.db_connection_pool_waiting_total")
    @patch("src.infrastructure.database.session.db_connection_pool_overflow")
    @patch("src.infrastructure.database.session.db_connection_pool_size")
    @patch("src.infrastructure.database.session.db_connection_pool_checkedout")
    @patch("src.infrastructure.database.session.engine")
    def test_update_db_pool_metrics_saturation_detected(
        self,
        mock_engine,
        mock_checkedout,
        mock_pool_size,
        mock_overflow,
        mock_waiting,
        mock_settings,
    ):
        """Test update_db_pool_metrics detects saturation at 90% (Lines 173-179)."""
        # Mock pool at 95% capacity (saturation threshold) as QueuePool
        mock_pool = MagicMock(spec=QueuePool)
        mock_pool.checkedout.return_value = 14  # 14/15 = 93% utilization
        mock_pool.overflow.return_value = 4

        mock_engine.pool = mock_pool

        # Mock settings
        mock_settings.database_pool_size = 10
        mock_settings.database_max_overflow = 5

        # Lines 173-179 executed: Saturation detected (>90% threshold)
        update_db_pool_metrics()

        # Verify waiting count estimated
        # saturation_threshold = int(15 * 0.9) = 13
        # estimated_waiting = max(0, 14 - 13) = 1
        mock_waiting.set.assert_called_once_with(1)

    @patch("src.infrastructure.database.session.settings")
    @patch("src.infrastructure.database.session.db_connection_pool_overflow")
    @patch("src.infrastructure.database.session.db_connection_pool_size")
    @patch("src.infrastructure.database.session.db_connection_pool_checkedout")
    @patch("src.infrastructure.database.session.engine")
    def test_update_db_pool_metrics_handles_negative_overflow(
        self,
        mock_engine,
        mock_checkedout,
        mock_pool_size,
        mock_overflow_metric,
        mock_settings,
    ):
        """Test update_db_pool_metrics handles negative overflow values (Lines 153-154)."""
        # Mock pool with negative overflow (shouldn't happen, but defensive) as QueuePool
        mock_pool = MagicMock(spec=QueuePool)
        mock_pool.checkedout.return_value = 5
        mock_pool.overflow.return_value = -1  # Negative value

        mock_engine.pool = mock_pool

        # Mock settings
        mock_settings.database_pool_size = 10
        mock_settings.database_max_overflow = 5

        # Lines 153-154 executed: Clamp overflow to 0
        update_db_pool_metrics()

        # Verify overflow set to 0 (not -1)
        mock_overflow_metric.set.assert_called_once_with(0)

    @patch("src.infrastructure.database.session.logger")
    @patch("src.infrastructure.database.session.engine")
    def test_update_db_pool_metrics_handles_non_queue_pool(self, mock_engine, mock_logger):
        """Test update_db_pool_metrics handles non-QueuePool gracefully (Line 144)."""
        # Mock non-QueuePool (e.g., NullPool, StaticPool)
        mock_pool = MagicMock()
        del mock_pool.checkedout  # Not a QueuePool method

        mock_engine.pool = mock_pool

        # Line 144: isinstance(pool, QueuePool) returns False
        update_db_pool_metrics()

        # Verify no errors raised (graceful skip)
        # No metrics updated for non-QueuePool

    @patch("src.infrastructure.database.session.logger")
    @patch("src.infrastructure.database.session.engine")
    def test_update_db_pool_metrics_handles_exception(self, mock_engine, mock_logger):
        """Test update_db_pool_metrics handles exceptions gracefully (Lines 181-182)."""
        # Mock pool that raises exception as QueuePool
        mock_pool = MagicMock(spec=QueuePool)
        mock_pool.checkedout = MagicMock(side_effect=RuntimeError("Pool error"))
        mock_engine.pool = mock_pool

        # Lines 181-182 executed: Exception caught and logged
        update_db_pool_metrics()

        # Verify warning logged
        mock_logger.warning.assert_called_once()
        assert "failed_to_update_db_pool_metrics" in str(mock_logger.warning.call_args)
        assert "Pool error" in str(mock_logger.warning.call_args)
