"""
Auth repository for database operations.
Implements Repository pattern for User model CRUD operations.

REFACTORED (2025-11-16 - Session 15 - Phase 2):
AuthRepository now inherits from BaseRepository to eliminate code duplication.
Shared methods (get_by_id, get_by_email, delete, soft_delete, update, create)
are now provided by BaseRepository.

This eliminates 34 lines of duplicated CRUD code between AuthRepository and UserRepository.
"""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.auth.models import User

logger = structlog.get_logger(__name__)


class AuthRepository(BaseRepository[User]):
    """Repository for authentication-related database operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, User)

    # ============================================================================
    # Inherited from BaseRepository:
    # - get_by_id(user_id: UUID) -> User | None
    # - get_by_email(email: str) -> User | None
    # - create(data: dict) -> User
    # - update(instance: User, data: dict) -> User
    # - soft_delete(instance: User) -> User  # Sets is_active=False
    # - delete(instance: User) -> None  # Hard delete (permanent)
    # ============================================================================

    async def get_by_oauth_provider(self, provider: str, provider_id: str) -> User | None:
        """
        Get user by OAuth provider and provider ID.

        Args:
            provider: OAuth provider name (e.g., 'google')
            provider_id: Provider's user ID

        Returns:
            User object or None if not found
        """
        result = await self.db.execute(
            select(User).where(
                User.oauth_provider == provider,
                User.oauth_provider_id == provider_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, user_data: dict) -> User:
        """
        Create a new user.

        Args:
            user_data: Dictionary containing user fields

        Returns:
            Created User object
        """
        user = await super().create(user_data)
        logger.info("user_created", user_id=str(user.id), email=user.email)
        return user

    async def update(self, user: User, update_data: dict) -> User:
        """
        Update user fields.

        Args:
            user: User object to update
            update_data: Dictionary of fields to update

        Returns:
            Updated User object
        """
        user = await super().update(user, update_data)
        logger.info("user_updated", user_id=str(user.id))
        return user

    async def delete(self, user: User) -> None:
        """
        Delete a user (soft delete by setting is_active=False).

        Args:
            user: User object to delete
        """
        await self.soft_delete(user)
        logger.info("user_deleted", user_id=str(user.id))

    async def hard_delete(self, user: User) -> None:
        """
        Permanently delete a user from database.

        Args:
            user: User object to delete
        """
        await BaseRepository.delete(self, user)
        logger.info("user_hard_deleted", user_id=str(user.id))

    async def activate_user(self, user: User) -> User:
        """
        Activate user account (set is_active=True, is_verified=True).

        Args:
            user: User object to activate

        Returns:
            Activated User object
        """
        user.is_active = True
        user.is_verified = True
        await self.db.flush()
        await self.db.refresh(user)

        logger.info("user_activated", user_id=str(user.id), email=user.email)
        return user

    async def update_password(self, user: User, hashed_password: str) -> User:
        """
        Update user password.

        Args:
            user: User object
            hashed_password: New hashed password

        Returns:
            Updated User object
        """
        user.hashed_password = hashed_password
        await self.db.flush()
        await self.db.refresh(user)

        logger.info("user_password_updated", user_id=str(user.id))
        return user

    async def get_all_superusers(self) -> list[User]:
        """
        Get all active superusers (admins).

        Returns:
            List of active superuser accounts
        """
        result = await self.db.execute(
            select(User).where(
                User.is_superuser == True,  # noqa: E712 - SQLAlchemy requires == True
                User.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())
