"""
Unit tests for Unit of Work pattern implementation.

Tests coverage for:
- UnitOfWork class: Transaction lifecycle, commit, rollback, nested transactions
- transactional decorator: Auto-wrapping functions in transactions
- get_transaction: Legacy context manager

Target: 80%+ coverage for core/unit_of_work.py
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.unit_of_work import UnitOfWork, get_transaction, transactional

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_session():
    """Create mock AsyncSession."""
    session = MagicMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.begin_nested = AsyncMock()

    # Mock savepoint
    savepoint = MagicMock()
    savepoint.commit = AsyncMock()
    savepoint.rollback = AsyncMock()
    session.begin_nested.return_value = savepoint

    return session


@pytest.fixture
def mock_savepoint():
    """Create mock savepoint transaction."""
    savepoint = MagicMock()
    savepoint.commit = AsyncMock()
    savepoint.rollback = AsyncMock()
    return savepoint


# =============================================================================
# UnitOfWork - Basic Tests
# =============================================================================


class TestUnitOfWorkBasic:
    """Basic tests for UnitOfWork class."""

    def test_init_default_state(self, mock_session):
        """Test UnitOfWork initializes with correct default state."""
        uow = UnitOfWork(mock_session)

        assert uow.db is mock_session
        assert uow._committed is False
        assert uow._rolled_back is False
        assert uow._is_nested is False
        assert uow._savepoint is None

    def test_init_nested_transaction(self, mock_session):
        """Test UnitOfWork initializes correctly for nested transaction."""
        uow = UnitOfWork(mock_session, is_nested=True)

        assert uow._is_nested is True

    @pytest.mark.asyncio
    async def test_context_manager_enter(self, mock_session):
        """Test entering UnitOfWork context."""
        uow = UnitOfWork(mock_session)

        async with uow as entered_uow:
            assert entered_uow is uow

    @pytest.mark.asyncio
    async def test_nested_context_creates_savepoint(self, mock_session):
        """Test nested transaction creates savepoint on enter."""
        uow = UnitOfWork(mock_session, is_nested=True)

        async with uow:
            pass

        mock_session.begin_nested.assert_called_once()


# =============================================================================
# UnitOfWork - Commit Tests
# =============================================================================


class TestUnitOfWorkCommit:
    """Tests for UnitOfWork commit behavior."""

    @pytest.mark.asyncio
    async def test_commit_calls_session_commit(self, mock_session):
        """Test commit calls session commit for top-level transaction."""
        async with UnitOfWork(mock_session) as uow:
            await uow.commit()

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_commit_sets_committed_flag(self, mock_session):
        """Test commit sets _committed flag."""
        async with UnitOfWork(mock_session) as uow:
            await uow.commit()
            assert uow._committed is True

    @pytest.mark.asyncio
    async def test_commit_twice_raises_error(self, mock_session):
        """Test committing twice raises RuntimeError."""
        async with UnitOfWork(mock_session) as uow:
            await uow.commit()

            with pytest.raises(RuntimeError) as exc_info:
                await uow.commit()

            assert "already committed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_commit_after_rollback_raises_error(self, mock_session):
        """Test committing after rollback raises RuntimeError."""
        async with UnitOfWork(mock_session) as uow:
            await uow.rollback()

            with pytest.raises(RuntimeError) as exc_info:
                await uow.commit()

            assert "rolled back transaction" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_nested_commit_calls_savepoint_commit(self, mock_session, mock_savepoint):
        """Test nested transaction commit calls savepoint commit."""
        mock_session.begin_nested.return_value = mock_savepoint

        uow = UnitOfWork(mock_session, is_nested=True)
        async with uow:
            await uow.commit()

        mock_savepoint.commit.assert_called_once()
        mock_session.commit.assert_not_called()


# =============================================================================
# UnitOfWork - Rollback Tests
# =============================================================================


class TestUnitOfWorkRollback:
    """Tests for UnitOfWork rollback behavior."""

    @pytest.mark.asyncio
    async def test_rollback_calls_session_rollback(self, mock_session):
        """Test rollback calls session rollback for top-level transaction."""
        async with UnitOfWork(mock_session) as uow:
            await uow.rollback()

        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_sets_rolled_back_flag(self, mock_session):
        """Test rollback sets _rolled_back flag."""
        async with UnitOfWork(mock_session) as uow:
            await uow.rollback()
            assert uow._rolled_back is True

    @pytest.mark.asyncio
    async def test_rollback_after_commit_raises_error(self, mock_session):
        """Test rollback after commit raises RuntimeError."""
        async with UnitOfWork(mock_session) as uow:
            await uow.commit()

            with pytest.raises(RuntimeError) as exc_info:
                await uow.rollback()

            assert "committed transaction" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rollback_twice_is_idempotent(self, mock_session):
        """Test rollback twice is idempotent (no error)."""
        async with UnitOfWork(mock_session) as uow:
            await uow.rollback()
            await uow.rollback()  # Should not raise

        # Rollback should only be called once
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_nested_rollback_calls_savepoint_rollback(self, mock_session, mock_savepoint):
        """Test nested transaction rollback calls savepoint rollback."""
        mock_session.begin_nested.return_value = mock_savepoint

        uow = UnitOfWork(mock_session, is_nested=True)
        async with uow:
            await uow.rollback()

        mock_savepoint.rollback.assert_called_once()
        mock_session.rollback.assert_not_called()


# =============================================================================
# UnitOfWork - Implicit Rollback Tests
# =============================================================================


class TestUnitOfWorkImplicitRollback:
    """Tests for implicit rollback behavior."""

    @pytest.mark.asyncio
    async def test_implicit_rollback_on_no_commit(self, mock_session):
        """Test implicit rollback when exiting without commit."""
        async with UnitOfWork(mock_session) as uow:
            pass  # No commit

        # Should have rolled back
        mock_session.rollback.assert_called_once()
        assert uow._rolled_back is True

    @pytest.mark.asyncio
    async def test_implicit_rollback_on_exception(self, mock_session):
        """Test rollback on exception within context."""
        with pytest.raises(ValueError):
            async with UnitOfWork(mock_session) as uow:
                raise ValueError("Test error")

        mock_session.rollback.assert_called_once()
        assert uow._rolled_back is True

    @pytest.mark.asyncio
    async def test_exception_propagates_after_rollback(self, mock_session):
        """Test that exception propagates after rollback."""
        with pytest.raises(ValueError) as exc_info:
            async with UnitOfWork(mock_session):
                raise ValueError("Original error")

        assert "Original error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_rollback_after_explicit_commit(self, mock_session):
        """Test no implicit rollback after explicit commit."""
        async with UnitOfWork(mock_session) as uow:
            await uow.commit()

        mock_session.rollback.assert_not_called()


# =============================================================================
# UnitOfWork - Nested Transaction Tests
# =============================================================================


class TestUnitOfWorkNested:
    """Tests for nested transaction functionality."""

    @pytest.mark.asyncio
    async def test_nested_context_manager(self, mock_session):
        """Test nested() creates nested UnitOfWork."""
        async with UnitOfWork(mock_session) as uow:
            async with uow.nested() as nested_uow:
                assert nested_uow._is_nested is True
                assert nested_uow.db is mock_session

    @pytest.mark.asyncio
    async def test_nested_commit_does_not_affect_outer(self, mock_session, mock_savepoint):
        """Test nested commit doesn't commit outer transaction."""
        mock_session.begin_nested.return_value = mock_savepoint

        async with UnitOfWork(mock_session) as uow:
            async with uow.nested() as nested_uow:
                await nested_uow.commit()

            # Outer should not be committed yet
            mock_session.commit.assert_not_called()
            mock_savepoint.commit.assert_called_once()

            await uow.commit()

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_nested_rollback_does_not_affect_outer(self, mock_session, mock_savepoint):
        """Test nested rollback doesn't rollback outer transaction."""
        mock_session.begin_nested.return_value = mock_savepoint

        async with UnitOfWork(mock_session) as uow:
            async with uow.nested() as nested_uow:
                await nested_uow.rollback()

            # Outer should still be able to commit
            mock_session.rollback.assert_not_called()
            mock_savepoint.rollback.assert_called_once()

            await uow.commit()

        mock_session.commit.assert_called_once()


# =============================================================================
# transactional Decorator Tests
# =============================================================================


class TestTransactionalDecorator:
    """Tests for transactional decorator."""

    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self, mock_session):
        """Test decorator wraps function in transaction."""

        @transactional
        async def my_func(db):
            return "result"

        result = await my_func(mock_session)

        assert result == "result"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_decorator_auto_commits_on_success(self, mock_session):
        """Test decorator auto-commits on successful function."""

        @transactional
        async def success_func(db):
            return {"data": "value"}

        await success_func(mock_session)

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_decorator_auto_rollbacks_on_exception(self, mock_session):
        """Test decorator auto-rollbacks on exception."""

        @transactional
        async def failing_func(db):
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await failing_func(mock_session)

        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_decorator_with_kwargs(self, mock_session):
        """Test decorator works with keyword argument for db."""

        @transactional
        async def func_with_kwargs(db, extra_param=None):
            return extra_param

        result = await func_with_kwargs(db=mock_session, extra_param="test")

        assert result == "test"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_decorator_raises_on_invalid_db_type(self):
        """Test decorator raises ValueError for invalid db type."""

        @transactional
        async def my_func(db):
            return "result"

        with pytest.raises(ValueError) as exc_info:
            await my_func("not a session")

        assert "AsyncSession" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self, mock_session):
        """Test decorator preserves original function metadata."""

        @transactional
        async def documented_func(db):
            """This is the docstring."""
            return "result"

        # functools.wraps should preserve metadata
        assert documented_func.__name__ == "documented_func"
        assert "docstring" in documented_func.__doc__

    @pytest.mark.asyncio
    async def test_decorator_with_multiple_params(self, mock_session):
        """Test decorator works with multiple parameters."""

        @transactional
        async def multi_param_func(db, param1, param2, *, keyword_param=None):
            return param1 + param2 + (keyword_param or 0)

        result = await multi_param_func(mock_session, 1, 2, keyword_param=3)

        assert result == 6
        mock_session.commit.assert_called_once()


# =============================================================================
# get_transaction Tests
# =============================================================================


class TestGetTransaction:
    """Tests for legacy get_transaction context manager."""

    @pytest.mark.asyncio
    async def test_get_transaction_yields_session(self, mock_session):
        """Test get_transaction yields the database session."""
        async with get_transaction(mock_session) as db:
            assert db is mock_session

    @pytest.mark.asyncio
    async def test_get_transaction_auto_commits(self, mock_session):
        """Test get_transaction auto-commits on success."""
        async with get_transaction(mock_session):
            pass

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transaction_rollbacks_on_exception(self, mock_session):
        """Test get_transaction rollbacks on exception."""
        with pytest.raises(ValueError):
            async with get_transaction(mock_session):
                raise ValueError("Test error")

        mock_session.rollback.assert_called_once()


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestUnitOfWorkIntegration:
    """Integration-style tests for complex scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_operations_atomic(self, mock_session):
        """Test multiple operations are atomic."""
        operations_completed = []

        async with UnitOfWork(mock_session) as uow:
            operations_completed.append("op1")
            operations_completed.append("op2")
            operations_completed.append("op3")
            await uow.commit()

        assert len(operations_completed) == 3
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_partial_failure_rolls_back_all(self, mock_session):
        """Test partial failure rolls back all operations."""
        operations_completed = []

        with pytest.raises(ValueError):
            async with UnitOfWork(mock_session):
                operations_completed.append("op1")
                operations_completed.append("op2")
                raise ValueError("Failure after op2")
                operations_completed.append("op3")  # Never reached

        # All operations tracked but will be rolled back
        assert len(operations_completed) == 2
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_nested_with_outer_commit(self, mock_session, mock_savepoint):
        """Test nested transaction followed by outer commit."""
        mock_session.begin_nested.return_value = mock_savepoint

        async with UnitOfWork(mock_session) as uow:
            # Outer operations
            pass

            # Nested operations
            async with uow.nested() as nested_uow:
                await nested_uow.commit()

            # More outer operations
            pass

            await uow.commit()

        mock_savepoint.commit.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_state_tracking_accuracy(self, mock_session):
        """Test state tracking is accurate throughout lifecycle."""
        uow = UnitOfWork(mock_session)

        # Initial state
        assert uow._committed is False
        assert uow._rolled_back is False

        async with uow:
            # Still uncommitted
            assert uow._committed is False
            assert uow._rolled_back is False

            await uow.commit()

            # Now committed
            assert uow._committed is True
            assert uow._rolled_back is False

        # Final state
        assert uow._committed is True
        assert uow._rolled_back is False
