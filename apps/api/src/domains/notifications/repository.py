"""
Repository for FCM token management and admin broadcasts.

Provides data access layer for user FCM tokens and broadcast messages.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, exists, literal, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func

from src.core.repository import BaseRepository
from src.domains.notifications.models import (
    AdminBroadcast,
    AdminBroadcastRecipient,
    BroadcastAudience,
    UserBroadcastRead,
    UserFCMToken,
)
from src.domains.users.models import User

#: Ids bound per ``IN (...)`` query when a list can grow with the instance.
_IN_CLAUSE_CHUNK = 1000


@dataclass(frozen=True)
class RecipientRow:
    """One named recipient of a selected-audience broadcast."""

    user_id: UUID
    full_name: str | None
    email: str


@dataclass(frozen=True)
class RecipientSample:
    """The first recipients of a broadcast in name order, and how many there are."""

    total: int
    users: tuple[RecipientRow, ...]


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

    async def unregister_token(self, token: str, user_id: UUID) -> bool:
        """
        Unregister (delete) an FCM token owned by this user.

        The ``user_id`` filter is the authorization check, not an optimisation.
        Deleting on the token value alone let any authenticated caller revoke
        somebody else's device registration by presenting its token — a silent
        denial of service on that person's notifications, with no trace beyond a
        successful-looking response. ``delete_token_by_id`` below always scoped
        its delete this way; this method did not, and both are reachable from
        the same router.

        Args:
            token: FCM token string
            user_id: User UUID (must own the token)

        Returns:
            True if token was deleted, False if not found or not owned
        """
        stmt = delete(UserFCMToken).where(
            UserFCMToken.token == token,
            UserFCMToken.user_id == user_id,
        )
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

    async def get_active_token_strings(self, user_ids: Sequence[UUID]) -> list[str]:
        """The active FCM tokens of several users, in one query.

        A broadcast used to read the tokens of its recipients one user at a
        time — N queries for N accounts on the send path (ADR-312).

        Args:
            user_ids: The users whose devices are reached.

        Returns:
            Their active token strings (possibly empty).
        """
        tokens: list[str] = []
        # Bounded IN lists: asyncpg refuses more than 32 767 bind parameters,
        # and an instance-wide language group can be larger than that.
        for start in range(0, len(user_ids), _IN_CLAUSE_CHUNK):
            chunk = user_ids[start : start + _IN_CLAUSE_CHUNK]
            result = await self.db.scalars(
                select(UserFCMToken.token).where(
                    UserFCMToken.user_id.in_(chunk),
                    UserFCMToken.is_active.is_(True),
                )
            )
            tokens.extend(result.all())
        return tokens

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
        recipient_ids: Sequence[UUID] | None = None,
    ) -> AdminBroadcast:
        """
        Create a new broadcast message with its audience (ADR-312).

        Args:
            message: The broadcast content
            sent_by: Admin user ID who sent it
            expires_at: Optional expiration datetime
            recipient_ids: The accounts a SELECTED broadcast is addressed to;
                None addresses everyone. A duplicate id is one recipient.

        Returns:
            Created AdminBroadcast (flushed, recipients included)
        """
        audience = BroadcastAudience.ALL if recipient_ids is None else BroadcastAudience.SELECTED
        broadcast = AdminBroadcast(
            message=message,
            sent_by=sent_by,
            expires_at=expires_at,
            audience=audience.value,
        )
        self.db.add(broadcast)
        await self.db.flush()
        if recipient_ids is not None:
            self.db.add_all(
                AdminBroadcastRecipient(broadcast_id=broadcast.id, user_id=user_id)
                for user_id in dict.fromkeys(recipient_ids)
            )
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
        - Broadcasts addressed to other accounts (a SELECTED audience the
          user is not part of — ADR-312)
        - Already read broadcasts
        - Expired broadcasts (expires_at < now)
        - Broadcasts created before the user's account (prevents new users from being spammed)
        - Broadcasts outside the N most recent eligible ones (prevents old broadcast waterfall)

        The ``recent_limit`` caps how many of the *most recent eligible* broadcasts
        are considered at all. Only unread broadcasts within that window are returned.
        This prevents a cascade effect where dismissing 3 broadcasts reveals 3 older ones.
        The audience is part of eligibility, so a broadcast to somebody else
        never takes a place in this reader's window.

        Args:
            user_id: User UUID
            user_created_at: User's account creation date (broadcasts before this are excluded)
            recent_limit: Only consider the N most recent eligible broadcasts

        Returns:
            List of unread AdminBroadcast ordered by created_at ASC (oldest first)
        """
        now = func.now()

        # Base conditions for eligible broadcasts (addressed to this user,
        # non-expired, after user signup)
        addressed_to_user = or_(
            AdminBroadcast.audience == BroadcastAudience.ALL.value,
            exists().where(
                AdminBroadcastRecipient.broadcast_id == AdminBroadcast.id,
                AdminBroadcastRecipient.user_id == user_id,
            ),
        )
        eligible_conditions = [
            addressed_to_user,
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

    async def merge_translations(
        self,
        broadcast_id: UUID,
        translations: dict[str, str],
    ) -> None:
        """
        Merge translations into the JSONB cache column (server-side atomic).

        Uses ``coalesce(translations, '{}') || :new`` so concurrent lazy
        backfills from different workers (e.g., two devices reading the same
        historical broadcast) never lose each other's languages — a plain
        read-modify-write reassignment would be last-write-wins.

        Args:
            broadcast_id: Broadcast UUID
            translations: New entries {language: translated text} to merge
        """
        if not translations:
            return

        stmt = (
            update(AdminBroadcast)
            .where(AdminBroadcast.id == broadcast_id)
            .values(
                message_translations=func.coalesce(
                    AdminBroadcast.message_translations,
                    literal({}, type_=JSONB),
                ).op("||")(literal(translations, type_=JSONB))
            )
        )
        await self.db.execute(stmt)

    # ========== HISTORY (ADR-312) ==========

    async def list_page(self, *, limit: int, offset: int) -> tuple[list[AdminBroadcast], int]:
        """One page of every broadcast sent, newest first, with the exact total.

        The ordering ends on the primary key so a page boundary never repeats or
        skips a row when two broadcasts share a timestamp.

        Args:
            limit: Rows per page.
            offset: Rows skipped before the page.

        Returns:
            The page's broadcasts (sender eager-loaded) and the total count.
        """
        total = int(await self.db.scalar(select(func.count(AdminBroadcast.id))) or 0)
        rows = await self.db.scalars(
            select(AdminBroadcast)
            .options(selectinload(AdminBroadcast.sender))
            .order_by(AdminBroadcast.created_at.desc(), AdminBroadcast.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.all()), total

    async def read_counts(self, broadcast_ids: Sequence[UUID]) -> dict[UUID, int]:
        """How many accounts read each broadcast — an aggregate, never a page length.

        Args:
            broadcast_ids: The broadcasts to count.

        Returns:
            ``{broadcast_id: reads}`` for the broadcasts read at least once; an
            absent id was read by nobody.
        """
        if not broadcast_ids:
            return {}
        result = await self.db.execute(
            select(UserBroadcastRead.broadcast_id, func.count(UserBroadcastRead.id))
            .where(UserBroadcastRead.broadcast_id.in_(broadcast_ids))
            .group_by(UserBroadcastRead.broadcast_id)
        )
        return {broadcast_id: int(count) for broadcast_id, count in result.all()}

    async def recipient_samples(
        self, broadcast_ids: Sequence[UUID], *, per_broadcast: int
    ) -> dict[UUID, RecipientSample]:
        """The first recipients of each selected broadcast, and their exact number.

        One statement for the whole page (a window per broadcast), so a page of
        N broadcasts costs one query rather than N.

        Args:
            broadcast_ids: The page's broadcasts.
            per_broadcast: How many recipients to name per broadcast.

        Returns:
            ``{broadcast_id: sample}`` for the broadcasts that have recipient
            rows; a broadcast to all has none and is absent.
        """
        if per_broadcast < 1:
            # A zero window would drop the totals with the names.
            raise ValueError("per_broadcast must be at least 1")
        if not broadcast_ids:
            return {}
        name_order = func.lower(func.coalesce(User.full_name, User.email))
        ranked = (
            select(
                AdminBroadcastRecipient.broadcast_id.label("broadcast_id"),
                User.id.label("user_id"),
                User.full_name.label("full_name"),
                User.email.label("email"),
                func.row_number()
                .over(
                    partition_by=AdminBroadcastRecipient.broadcast_id,
                    order_by=(name_order, User.id),
                )
                .label("rank"),
                func.count().over(partition_by=AdminBroadcastRecipient.broadcast_id).label("total"),
            )
            .join(User, User.id == AdminBroadcastRecipient.user_id)
            .where(AdminBroadcastRecipient.broadcast_id.in_(broadcast_ids))
            .subquery()
        )
        result = await self.db.execute(
            select(ranked)
            .where(ranked.c.rank <= per_broadcast)
            .order_by(ranked.c.broadcast_id, ranked.c.rank)
        )
        users: dict[UUID, list[RecipientRow]] = {}
        totals: dict[UUID, int] = {}
        for row in result.all():
            users.setdefault(row.broadcast_id, []).append(
                RecipientRow(user_id=row.user_id, full_name=row.full_name, email=row.email)
            )
            totals[row.broadcast_id] = int(row.total)
        return {
            broadcast_id: RecipientSample(total=totals[broadcast_id], users=tuple(rows))
            for broadcast_id, rows in users.items()
        }
