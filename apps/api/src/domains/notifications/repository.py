"""
Repository for FCM token management and admin broadcasts.

Provides data access layer for user FCM tokens and broadcast messages.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func

from src.core.repository import BaseRepository
from src.domains.notifications.models import AdminBroadcast, UserBroadcastRead, UserFCMToken


class FCMTokenRepository(BaseRepository[UserFCMToken]):
    """
    Repository for FCM token CRUD operations.

    Follows the BaseRepository pattern used across the codebase.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with database session."""
        super().__init__(db, UserFCMToken)

    async def get_by_token(self, token: str) -> UserFCMToken | None:
        """
        Get FCM token record by token string.

        Args:
            token: FCM token string

        Returns:
            UserFCMToken if found, None otherwise
        """
        stmt = select(UserFCMToken).where(UserFCMToken.token == token)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_tokens_for_user(self, user_id: UUID) -> list[UserFCMToken]:
        """
        Get all active FCM tokens for a user.

        Args:
            user_id: User UUID

        Returns:
            List of active FCM tokens
        """
        stmt = (
            select(UserFCMToken)
            .where(UserFCMToken.user_id == user_id)
            .where(UserFCMToken.is_active.is_(True))
            .order_by(UserFCMToken.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_all_tokens_for_user(self, user_id: UUID) -> list[UserFCMToken]:
        """
        Get all FCM tokens for a user (active and inactive).

        Args:
            user_id: User UUID

        Returns:
            List of all FCM tokens
        """
        stmt = (
            select(UserFCMToken)
            .where(UserFCMToken.user_id == user_id)
            .order_by(UserFCMToken.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def register_token(
        self,
        user_id: UUID,
        token: str,
        device_type: str,
        device_name: str | None = None,
    ) -> UserFCMToken:
        """
        Register a new FCM token or update existing one.

        If the token already exists:
        - If owned by same user: update and reactivate
        - If owned by different user: reassign to new user

        Args:
            user_id: User UUID
            token: FCM token string
            device_type: Device type (android, ios, web)
            device_name: Optional device name

        Returns:
            Created or updated UserFCMToken
        """
        existing = await self.get_by_token(token)

        if existing:
            # Token exists - update it
            existing.user_id = user_id
            existing.device_type = device_type
            existing.device_name = device_name
            existing.is_active = True
            existing.last_error = None
            existing.updated_at = datetime.now(UTC)
            await self.db.flush()
            return existing

        # Create new token
        fcm_token = UserFCMToken(
            user_id=user_id,
            token=token,
            device_type=device_type,
            device_name=device_name,
            is_active=True,
        )
        self.db.add(fcm_token)
        await self.db.flush()
        return fcm_token

    async def unregister_token(self, token: str) -> bool:
        """
        Unregister (delete) an FCM token.

        Args:
            token: FCM token string

        Returns:
            True if token was deleted, False if not found
        """
        stmt = delete(UserFCMToken).where(UserFCMToken.token == token)
        result = await self.db.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    async def delete_token_by_id(
        self,
        token_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Delete an FCM token by ID (with user ownership check).

        Args:
            token_id: Token UUID
            user_id: User UUID (must own the token)

        Returns:
            True if token was deleted, False if not found or not owned
        """
        stmt = (
            delete(UserFCMToken)
            .where(UserFCMToken.id == token_id)
            .where(UserFCMToken.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    async def deactivate_token(self, token: str, error: str | None = None) -> bool:
        """
        Deactivate an FCM token (mark as inactive).

        Used when FCM reports the token as invalid.

        Args:
            token: FCM token string
            error: Error message from FCM

        Returns:
            True if token was deactivated, False if not found
        """
        stmt = (
            update(UserFCMToken)
            .where(UserFCMToken.token == token)
            .values(
                is_active=False,
                last_error=error,
                updated_at=datetime.now(UTC),
            )
        )
        result = await self.db.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    async def update_last_used(self, token_id: UUID) -> None:
        """
        Update the last_used_at timestamp for a token.

        Args:
            token_id: Token UUID
        """
        stmt = (
            update(UserFCMToken)
            .where(UserFCMToken.id == token_id)
            .values(last_used_at=datetime.now(UTC))
        )
        await self.db.execute(stmt)

    async def cleanup_inactive_tokens(self, older_than_days: int = 30) -> int:
        """
        Delete inactive tokens older than specified days.

        Args:
            older_than_days: Delete inactive tokens older than this

        Returns:
            Number of tokens deleted
        """
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        stmt = (
            delete(UserFCMToken)
            .where(UserFCMToken.is_active.is_(False))
            .where(UserFCMToken.updated_at < cutoff)
        )
        result = await self.db.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined, no-any-return]


class BroadcastRepository(BaseRepository[AdminBroadcast]):
    """
    Repository for admin broadcast CRUD operations.

    Follows the BaseRepository pattern used across the codebase.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with database session."""
        super().__init__(db, AdminBroadcast)

    async def create_broadcast(
        self,
        message: str,
        sent_by: UUID,
        expires_at: datetime | None = None,
    ) -> AdminBroadcast:
        """
        Create a new broadcast message.

        Args:
            message: The broadcast content
            sent_by: Admin user ID who sent it
            expires_at: Optional expiration datetime

        Returns:
            Created AdminBroadcast
        """
        broadcast = AdminBroadcast(
            message=message,
            sent_by=sent_by,
            expires_at=expires_at,
        )
        self.db.add(broadcast)
        await self.db.flush()
        return broadcast

    async def get_unread_for_user(
        self,
        user_id: UUID,
        user_created_at: datetime | None = None,
        recent_limit: int | None = None,
    ) -> list[AdminBroadcast]:
        """
        Get broadcasts that user hasn't read yet.

        Excludes:
        - Already read broadcasts
        - Expired broadcasts (expires_at < now)
        - Broadcasts created before the user's account (prevents new users from being spammed)
        - Broadcasts outside the N most recent eligible ones (prevents old broadcast waterfall)

        The ``recent_limit`` caps how many of the *most recent eligible* broadcasts
        are considered at all. Only unread broadcasts within that window are returned.
        This prevents a cascade effect where dismissing 3 broadcasts reveals 3 older ones.

        Args:
            user_id: User UUID
            user_created_at: User's account creation date (broadcasts before this are excluded)
            recent_limit: Only consider the N most recent eligible broadcasts

        Returns:
            List of unread AdminBroadcast ordered by created_at ASC (oldest first)
        """
        now = func.now()

        # Base conditions for eligible broadcasts (non-expired, after user signup)
        eligible_conditions = [
            or_(AdminBroadcast.expires_at.is_(None), AdminBroadcast.expires_at > now),
        ]
        if user_created_at is not None:
            eligible_conditions.append(AdminBroadcast.created_at >= user_created_at)

        # Subquery: IDs of the N most recent eligible broadcasts
        eligible_ids_subquery = (
            select(AdminBroadcast.id)
            .where(*eligible_conditions)
            .order_by(AdminBroadcast.created_at.desc())
        )
        if recent_limit is not None:
            eligible_ids_subquery = eligible_ids_subquery.limit(recent_limit)

        # Subquery: IDs of broadcasts already read by this user
        read_ids_subquery = select(UserBroadcastRead.broadcast_id).where(
            UserBroadcastRead.user_id == user_id
        )

        # Main query: unread broadcasts within the eligible window
        stmt = (
            select(AdminBroadcast)
            .options(selectinload(AdminBroadcast.sender))
            .where(
                AdminBroadcast.id.in_(eligible_ids_subquery),
                AdminBroadcast.id.notin_(read_ids_subquery),
            )
            .order_by(AdminBroadcast.created_at.asc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def mark_as_read(self, user_id: UUID, broadcast_id: UUID) -> bool:
        """
        Mark a broadcast as read for a user.

        Idempotent: Returns True even if already marked (ON CONFLICT DO NOTHING).

        Args:
            user_id: User UUID
            broadcast_id: Broadcast UUID

        Returns:
            True (always succeeds due to ON CONFLICT DO NOTHING)
        """
        stmt = (
            pg_insert(UserBroadcastRead)
            .values(
                user_id=user_id,
                broadcast_id=broadcast_id,
            )
            .on_conflict_do_nothing(constraint="uq_user_broadcast_read")
        )

        await self.db.execute(stmt)
        return True

    async def update_stats(
        self,
        broadcast_id: UUID,
        total_recipients: int,
        fcm_sent: int,
        fcm_failed: int,
    ) -> None:
        """
        Update broadcast statistics after sending.

        Args:
            broadcast_id: Broadcast UUID
            total_recipients: Total number of active users
            fcm_sent: Number of FCM notifications sent
            fcm_failed: Number of FCM notifications failed
        """
        stmt = (
            update(AdminBroadcast)
            .where(AdminBroadcast.id == broadcast_id)
            .values(
                total_recipients=total_recipients,
                fcm_sent=fcm_sent,
                fcm_failed=fcm_failed,
            )
        )
        await self.db.execute(stmt)
