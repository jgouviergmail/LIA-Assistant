"""
Channel binding repository for database operations.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.channels.models import UserChannelBinding


class UserChannelBindingRepository(BaseRepository[UserChannelBinding]):
    """Repository for user channel binding CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, UserChannelBinding)

    async def get_all_for_user(
        self,
        user_id: UUID,
    ) -> list[UserChannelBinding]:
        """Get all channel bindings for a user, ordered by channel_type."""
        stmt = (
            select(UserChannelBinding)
            .where(UserChannelBinding.user_id == user_id)
            .order_by(UserChannelBinding.channel_type.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_active_for_user(
        self,
        user_id: UUID,
    ) -> list[UserChannelBinding]:
        """
        Get active channel bindings for a user.

        Used by NotificationDispatcher to send notifications to linked channels.
        """
        stmt = (
            select(UserChannelBinding)
            .where(UserChannelBinding.user_id == user_id)
            .where(UserChannelBinding.is_active.is_(True))
            .order_by(UserChannelBinding.channel_type.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_channel_id(
        self,
        channel_type: str,
        channel_user_id: str,
        *,
        include_inactive: bool = False,
    ) -> UserChannelBinding | None:
        """
        Get binding by channel type and provider-specific user ID.

        This is the hot path for webhook processing: when a Telegram message
        arrives, we look up the binding by (telegram, chat_id) to find the
        LIA user. The active-only read uses the partial index
        ``ix_channel_bindings_active_lookup``; with ``include_inactive`` — the
        webhook's own reading — the pair's unique index serves it.

        Args:
            channel_type: The channel (``telegram``).
            channel_user_id: The user's id on that channel.
            include_inactive: Also read a binding its owner switched off — for
                a caller that must TELL that person so (ADR-323). The pair is
                unique whatever the state (``uq_channel_type_user_id``).

        Returns:
            The binding, or None.
        """
        stmt = (
            select(UserChannelBinding)
            .where(UserChannelBinding.channel_type == channel_type)
            .where(UserChannelBinding.channel_user_id == channel_user_id)
        )
        if not include_inactive:
            stmt = stmt.where(UserChannelBinding.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_type(
        self,
        user_id: UUID,
        channel_type: str,
    ) -> UserChannelBinding | None:
        """Get binding for a specific user and channel type."""
        stmt = (
            select(UserChannelBinding)
            .where(UserChannelBinding.user_id == user_id)
            .where(UserChannelBinding.channel_type == channel_type)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_bindings_by_type(
        self,
        user_id: UUID,
        channel_type: str,
    ) -> list[UserChannelBinding]:
        """
        Get active bindings for a user filtered by channel type.

        Used for outbound notifications to a specific channel.
        """
        stmt = (
            select(UserChannelBinding)
            .where(UserChannelBinding.user_id == user_id)
            .where(UserChannelBinding.channel_type == channel_type)
            .where(UserChannelBinding.is_active.is_(True))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
