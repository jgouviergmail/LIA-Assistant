"""
Tests for Unit of Work pattern.

Tests cover:
- Basic commit/rollback semantics
- Nested transactions (savepoints)
- Exception handling
- Decorator usage
- Edge cases (double commit, commit after rollback, etc.)
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.unit_of_work import UnitOfWork, transactional
from src.domains.users.models import User


class TestUnitOfWork:
    """Tests for UnitOfWork class."""

    @pytest.mark.asyncio
    async def test_commit_persists_changes(self, db_session: AsyncSession):
        """Test that explicit commit persists changes."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "full_name": "Test User",
            "hashed_password": "hashedpass123",
        }

        # Act
        async with UnitOfWork(db_session) as uow:
            user = User(**user_data)
            db_session.add(user)
            await db_session.flush()  # Get ID
            user_id = user.id
            await uow.commit()

        # Assert - verify user persisted
        result = await db_session.execute(select(User).where(User.id == user_id))
        persisted_user = result.scalar_one_or_none()
        assert persisted_user is not None
        assert persisted_user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_no_commit_rolls_back(self, db_session: AsyncSession):
        """Test that exiting without commit rolls back changes."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "full_name": "Test User",
            "hashed_password": "hashedpass123",
        }

        # Act
        user_id = None
        async with UnitOfWork(db_session):
            user = User(**user_data)
            db_session.add(user)
            await db_session.flush()
            user_id = user.id
            # Note: No commit called

        # Assert - verify user NOT persisted
        result = await db_session.execute(select(User).where(User.id == user_id))
        persisted_user = result.scalar_one_or_none()
        assert persisted_user is None

    @pytest.mark.asyncio
    async def test_exception_rolls_back(self, db_session: AsyncSession):
        """Test that exceptions trigger rollback."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "full_name": "Test User",
            "hashed_password": "hashedpass123",
        }

        # Act
        user_id = None
        with pytest.raises(ValueError, match="Simulated error"):
            async with UnitOfWork(db_session):
                user = User(**user_data)
                db_session.add(user)
                await db_session.flush()
                user_id = user.id
                raise ValueError("Simulated error")

        # Assert - verify rollback occurred
        result = await db_session.execute(select(User).where(User.id == user_id))
        persisted_user = result.scalar_one_or_none()
        assert persisted_user is None

    @pytest.mark.asyncio
    async def test_explicit_rollback(self, db_session: AsyncSession):
        """Test explicit rollback."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "full_name": "Test User",
            "hashed_password": "hashedpass123",
        }

        # Act
        user_id = None
        async with UnitOfWork(db_session) as uow:
            user = User(**user_data)
            db_session.add(user)
            await db_session.flush()
            user_id = user.id
            await uow.rollback()

        # Assert - verify rollback occurred
        result = await db_session.execute(select(User).where(User.id == user_id))
        persisted_user = result.scalar_one_or_none()
        assert persisted_user is None

    @pytest.mark.asyncio
    async def test_double_commit_raises(self, db_session: AsyncSession):
        """Test that double commit raises error."""
        async with UnitOfWork(db_session) as uow:
            await uow.commit()
            with pytest.raises(RuntimeError, match="already committed"):
                await uow.commit()

    @pytest.mark.asyncio
    async def test_commit_after_rollback_raises(self, db_session: AsyncSession):
        """Test that commit after rollback raises error."""
        async with UnitOfWork(db_session) as uow:
            await uow.rollback()
            with pytest.raises(RuntimeError, match="Cannot commit a rolled back transaction"):
                await uow.commit()

    @pytest.mark.asyncio
    async def test_rollback_after_commit_raises(self, db_session: AsyncSession):
        """Test that rollback after commit raises error."""
        async with UnitOfWork(db_session) as uow:
            await uow.commit()
            with pytest.raises(RuntimeError, match="Cannot rollback a committed transaction"):
                await uow.rollback()

    @pytest.mark.asyncio
    async def test_nested_commit_persists(self, db_session: AsyncSession):
        """Test nested transaction with commit."""
        # Arrange
        user1_data = {
            "email": "user1@example.com",
            "full_name": "User One",
            "hashed_password": "pass1",
        }
        user2_data = {
            "email": "user2@example.com",
            "full_name": "User Two",
            "hashed_password": "pass2",
        }

        # Act
        user1_id = None
        user2_id = None
        async with UnitOfWork(db_session) as uow:
            # Create first user
            user1 = User(**user1_data)
            db_session.add(user1)
            await db_session.flush()
            user1_id = user1.id

            # Nested transaction for second user
            async with uow.nested() as nested_uow:
                user2 = User(**user2_data)
                db_session.add(user2)
                await db_session.flush()
                user2_id = user2.id
                await nested_uow.commit()

            await uow.commit()

        # Assert - both users persisted
        result1 = await db_session.execute(select(User).where(User.id == user1_id))
        result2 = await db_session.execute(select(User).where(User.id == user2_id))
        assert result1.scalar_one_or_none() is not None
        assert result2.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_nested_rollback_preserves_outer(self, db_session: AsyncSession):
        """Test nested rollback doesn't affect outer transaction."""
        # Arrange
        user1_data = {
            "email": "user1@example.com",
            "full_name": "User One",
            "hashed_password": "pass1",
        }
        user2_data = {
            "email": "user2@example.com",
            "full_name": "User Two",
            "hashed_password": "pass2",
        }

        # Act
        user1_id = None
        user2_id = None
        async with UnitOfWork(db_session) as uow:
            # Create first user
            user1 = User(**user1_data)
            db_session.add(user1)
            await db_session.flush()
            user1_id = user1.id

            # Nested transaction that will rollback
            async with uow.nested() as nested_uow:
                user2 = User(**user2_data)
                db_session.add(user2)
                await db_session.flush()
                user2_id = user2.id
                await nested_uow.rollback()

            # Commit outer transaction
            await uow.commit()

        # Assert - only user1 persisted
        result1 = await db_session.execute(select(User).where(User.id == user1_id))
        result2 = await db_session.execute(select(User).where(User.id == user2_id))
        assert result1.scalar_one_or_none() is not None
        assert result2.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_nested_exception_rolls_back_both(self, db_session: AsyncSession):
        """Test exception in nested transaction rolls back both."""
        # Arrange
        user1_data = {
            "email": "user1@example.com",
            "full_name": "User One",
            "hashed_password": "pass1",
        }
        user2_data = {
            "email": "user2@example.com",
            "full_name": "User Two",
            "hashed_password": "pass2",
        }

        # Act
        user1_id = None
        user2_id = None
        with pytest.raises(ValueError):
            async with UnitOfWork(db_session) as uow:
                user1 = User(**user1_data)
                db_session.add(user1)
                await db_session.flush()
                user1_id = user1.id

                async with uow.nested():
                    user2 = User(**user2_data)
                    db_session.add(user2)
                    await db_session.flush()
                    user2_id = user2.id
                    raise ValueError("Nested error")

        # Assert - neither user persisted
        result1 = await db_session.execute(select(User).where(User.id == user1_id))
        result2 = await db_session.execute(select(User).where(User.id == user2_id))
        assert result1.scalar_one_or_none() is None
        assert result2.scalar_one_or_none() is None


class TestTransactionalDecorator:
    """Tests for @transactional decorator."""

    @pytest.mark.asyncio
    async def test_transactional_auto_commits(self, db_session: AsyncSession):
        """Test that @transactional auto-commits on success."""

        @transactional
        async def create_user(db: AsyncSession, email: str) -> User:
            user = User(email=email, full_name="Test User", hashed_password="pass")
            db.add(user)
            await db.flush()
            return user

        # Act
        user = await create_user(db=db_session, email="test@example.com")

        # Assert - verify auto-commit
        result = await db_session.execute(select(User).where(User.id == user.id))
        persisted_user = result.scalar_one_or_none()
        assert persisted_user is not None

    @pytest.mark.asyncio
    async def test_transactional_rolls_back_on_exception(self, db_session: AsyncSession):
        """Test that @transactional rolls back on exception."""

        @transactional
        async def create_user_and_fail(db: AsyncSession, email: str) -> User:
            user = User(email=email, full_name="Test User", hashed_password="pass")
            db.add(user)
            await db.flush()
            raise ValueError("Simulated error")

        # Act
        with pytest.raises(ValueError):
            await create_user_and_fail(db=db_session, email="test@example.com")

        # Assert - verify rollback
        result = await db_session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 0

    @pytest.mark.asyncio
    async def test_transactional_with_positional_db(self, db_session: AsyncSession):
        """Test @transactional with db as positional argument."""

        @transactional
        async def create_user(db: AsyncSession, email: str) -> User:
            user = User(email=email, full_name="Test User", hashed_password="pass")
            db.add(user)
            await db.flush()
            return user

        # Act - pass db as positional
        user = await create_user(db_session, email="test@example.com")

        # Assert
        result = await db_session.execute(select(User).where(User.id == user.id))
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_transactional_invalid_db_raises(self):
        """Test that @transactional raises if db is not AsyncSession."""

        @transactional
        async def create_user(db: AsyncSession, email: str) -> User:
            pass

        # Act & Assert
        with pytest.raises(ValueError, match="AsyncSession"):
            await create_user(db="not a session", email="test@example.com")


class TestEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_multiple_sequential_transactions(self, db_session: AsyncSession):
        """Test multiple transactions in sequence."""
        # Act - create users in separate transactions
        async with UnitOfWork(db_session) as uow1:
            user1 = User(email="user1@example.com", full_name="User One", hashed_password="pass1")
            db_session.add(user1)
            await db_session.flush()
            await uow1.commit()

        async with UnitOfWork(db_session) as uow2:
            user2 = User(email="user2@example.com", full_name="User Two", hashed_password="pass2")
            db_session.add(user2)
            await db_session.flush()
            await uow2.commit()

        # Assert - both persisted
        result = await db_session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 2

    @pytest.mark.asyncio
    async def test_idempotent_rollback(self, db_session: AsyncSession):
        """Test that multiple rollbacks are idempotent."""
        async with UnitOfWork(db_session) as uow:
            await uow.rollback()
            await uow.rollback()  # Should not raise
            await uow.rollback()  # Should not raise

        # Should complete without error
        assert True
