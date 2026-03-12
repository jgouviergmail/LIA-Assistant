"""
Unit of Work Pattern for Transaction Management

This module implements the Unit of Work pattern to provide clear transaction boundaries
and consistent commit/rollback semantics across the application.

Architecture Decision:
- Granularity: 1 HTTP request = 1 transaction (see docs/design/ADR-001-unit-of-work-pattern.md)
- Nested transactions: Supported via SQLAlchemy savepoints
- Rollback: Automatic on exception, manual via rollback()
- Commit: Explicit only, never implicit

Usage:
    # Basic usage (HTTP request boundary)
    async with UnitOfWork(db) as uow:
        user = await user_service.create_user(data)
        await connector_service.create_connector(user.id, connector_data)
        await uow.commit()  # Explicit commit
    # Auto-rollback on exception

    # Decorator usage
    @transactional
    async def create_user_with_connector(db: AsyncSession, data: dict):
        user = await user_service.create_user(data)
        connector = await connector_service.create_connector(user.id, data)
        return user, connector

    # Nested transactions (advanced)
    async with UnitOfWork(db) as uow:
        await outer_operation()
        async with uow.nested() as nested_uow:
            await inner_operation()
            await nested_uow.commit()  # Savepoint
        await uow.commit()
"""

from __future__ import annotations

import functools
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction
from structlog import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class UnitOfWork:
    """
    Manages transaction lifecycle with explicit commit/rollback semantics.

    This class ensures that all database operations within a context are atomic:
    - Committed together on success
    - Rolled back together on failure

    Attributes:
        db: SQLAlchemy async session
        _committed: Whether transaction has been committed
        _rolled_back: Whether transaction has been rolled back
        _is_nested: Whether this is a nested transaction (savepoint)

    Example:
        async with UnitOfWork(db) as uow:
            # Perform database operations
            user = await user_repo.create(user_data)
            await connector_repo.create(connector_data)

            # Explicit commit required
            await uow.commit()
        # Auto-rollback if commit not called or exception raised
    """

    def __init__(self, db: AsyncSession, is_nested: bool = False) -> None:
        """
        Initialize Unit of Work.

        Args:
            db: SQLAlchemy async session
            is_nested: Whether this is a nested transaction (internal use)
        """
        self.db = db
        self._committed = False
        self._rolled_back = False
        self._is_nested = is_nested
        self._savepoint: AsyncSessionTransaction | None = None

    async def __aenter__(self) -> UnitOfWork:
        """
        Enter transaction context.

        For nested transactions, creates a savepoint.
        For top-level transactions, uses the session's transaction.
        """
        if self._is_nested:
            # Create savepoint for nested transaction
            self._savepoint = await self.db.begin_nested()
            logger.debug("uow_nested_transaction_started", savepoint=str(self._savepoint))
        else:
            # Top-level transaction (session manages this automatically)
            logger.debug("uow_transaction_started", session_id=id(self.db))

        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any
    ) -> bool | None:
        """
        Exit transaction context.

        If exception occurred:
            - Rollback transaction
            - Propagate exception
        If no exception but not committed:
            - Rollback transaction (uncommitted changes are not persisted)
            - Log warning about implicit rollback
        """
        if exc_type is not None:
            # Exception occurred, rollback
            await self.rollback()
            logger.warning(
                "uow_transaction_rolled_back_due_to_exception",
                exc_type=exc_type.__name__,
                exc_val=str(exc_val),
                is_nested=self._is_nested,
            )
            return False  # Propagate exception

        if not self._committed and not self._rolled_back:
            # Exiting without explicit commit or rollback
            await self.rollback()
            logger.warning(
                "uow_implicit_rollback",
                message="Transaction exited without explicit commit - changes rolled back",
                is_nested=self._is_nested,
            )

        logger.debug(
            "uow_transaction_completed",
            committed=self._committed,
            rolled_back=self._rolled_back,
            is_nested=self._is_nested,
        )
        return None  # Don't suppress exceptions

    async def commit(self) -> None:
        """
        Commit the transaction.

        For nested transactions: Commits the savepoint
        For top-level transactions: Commits the session

        Raises:
            RuntimeError: If already committed or rolled back
        """
        if self._committed:
            raise RuntimeError("Transaction already committed")
        if self._rolled_back:
            raise RuntimeError("Cannot commit a rolled back transaction")

        if self._is_nested:
            # Commit savepoint
            if self._savepoint is not None:
                await self._savepoint.commit()
                logger.debug("uow_savepoint_committed", savepoint=str(self._savepoint))
        else:
            # Commit session
            await self.db.commit()
            logger.info("uow_transaction_committed", session_id=id(self.db))

        self._committed = True

    async def rollback(self) -> None:
        """
        Rollback the transaction.

        For nested transactions: Rolls back the savepoint
        For top-level transactions: Rolls back the session

        Raises:
            RuntimeError: If already committed or rolled back
        """
        if self._committed:
            raise RuntimeError("Cannot rollback a committed transaction")
        if self._rolled_back:
            logger.debug("uow_already_rolled_back", is_nested=self._is_nested)
            return  # Already rolled back, idempotent

        if self._is_nested:
            # Rollback savepoint
            if self._savepoint is not None:
                await self._savepoint.rollback()
                logger.debug("uow_savepoint_rolled_back", savepoint=str(self._savepoint))
        else:
            # Rollback session
            await self.db.rollback()
            logger.info("uow_transaction_rolled_back", session_id=id(self.db))

        self._rolled_back = True

    @asynccontextmanager
    async def nested(self) -> AsyncGenerator[UnitOfWork, None]:
        """
        Create a nested transaction (savepoint).

        Allows for partial rollback within a larger transaction.

        Example:
            async with UnitOfWork(db) as uow:
                await create_user(user_data)

                # Try to create connector, rollback if fails
                async with uow.nested() as nested_uow:
                    await create_connector(connector_data)
                    await nested_uow.commit()

                # User is still created even if connector fails
                await uow.commit()

        Yields:
            UnitOfWork: Nested unit of work with savepoint
        """
        nested_uow = UnitOfWork(self.db, is_nested=True)
        async with nested_uow:
            yield nested_uow


def transactional[T](func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """
    Decorator to mark a function as transactional.

    Automatically wraps the function in a Unit of Work context.
    The first parameter must be an AsyncSession named 'db'.

    Args:
        func: Async function to wrap

    Returns:
        Wrapped function with transaction management

    Example:
        @transactional
        async def create_user_with_profile(
            db: AsyncSession,
            user_data: dict,
            profile_data: dict
        ) -> User:
            user = await user_service.create_user(db, user_data)
            await profile_service.create_profile(db, user.id, profile_data)
            return user
        # Auto-commits on success, auto-rollbacks on exception

    Raises:
        ValueError: If first parameter is not named 'db' or not AsyncSession
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        # Extract db session from arguments
        db = kwargs.get("db") or (args[0] if args else None)

        if not isinstance(db, AsyncSession):
            raise ValueError(
                f"@transactional requires first parameter 'db' to be AsyncSession, "
                f"got {type(db).__name__}"
            )

        async with UnitOfWork(db) as uow:
            # Call original function
            result = await func(*args, **kwargs)

            # Auto-commit on success
            await uow.commit()
            logger.debug(
                "transactional_auto_commit",
                function=func.__name__,
                module=func.__module__,
            )

            return result

    return wrapper


# Utility context manager for backward compatibility
@asynccontextmanager
async def get_transaction(db: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """
    Legacy context manager for transaction management.

    DEPRECATED: Use UnitOfWork directly for better control.

    Example:
        async with get_transaction(db):
            # Perform operations
            pass
        # Auto-commits on success

    Yields:
        AsyncSession: Database session
    """
    async with UnitOfWork(db) as uow:
        yield db
        await uow.commit()
