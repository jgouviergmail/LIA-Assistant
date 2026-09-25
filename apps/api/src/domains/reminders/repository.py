"""
Reminder repository for database operations.

Includes the scheduler's claim, settlement and stale-claim recovery (ADR-304).

Phase: Reminders with FCM notifications
Created: 2025-12-28
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.reminders.models import Reminder, ReminderStatus

logger = structlog.get_logger(__name__)


class ReminderRepository(BaseRepository[Reminder]):
    """Repository for reminder CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, Reminder)

    async def get_pending_for_user(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Reminder]:
        """Get pending reminders for a user, soonest first.

        Args:
            user_id: Owner — scopes the read.
            limit: Page size.
            offset: How many of the soonest to skip. The secondary sort on the
                primary key gives a TOTAL order, without which two reminders
                sharing a trigger instant could repeat or vanish across a page
                boundary.

        Returns:
            The page, soonest first.
        """
        stmt = (
            select(Reminder)
            .where(Reminder.user_id == user_id)
            .where(Reminder.status == ReminderStatus.PENDING.value)
            .order_by(Reminder.trigger_at.asc(), Reminder.id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_pending_for_user(self, user_id: UUID) -> int:
        """How many reminders are still waiting to fire.

        An aggregate over the whole set, never the length of a page: a count
        shown to the reader is a claim, and it is exact or it does not exist
        (ADR-185).

        Args:
            user_id: Owner — scopes the read.

        Returns:
            Exact number of pending reminders.
        """
        stmt = (
            select(func.count())
            .select_from(Reminder)
            .where(Reminder.user_id == user_id)
            .where(Reminder.status == ReminderStatus.PENDING.value)
        )
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def get_all_for_user(
        self,
        user_id: UUID,
        include_cancelled: bool = False,
        limit: int = 100,
    ) -> list[Reminder]:
        """Get all reminders for a user."""
        stmt = select(Reminder).where(Reminder.user_id == user_id)

        if not include_cancelled:
            stmt = stmt.where(Reminder.status != ReminderStatus.CANCELLED.value)

        stmt = stmt.order_by(Reminder.trigger_at.asc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def claim_next_due(self) -> Reminder | None:
        """Claim ONE due reminder for notification: PENDING → PROCESSING.

        ``FOR UPDATE SKIP LOCKED`` keeps two workers off the same row while the
        claim is taken; the CALLER commits at once, which releases the row lock
        and leaves the PROCESSING status as the claim (ADR-304). Nothing is
        notified under the lock: a batch of 100 claimed together used to keep
        every row locked — and one transaction open — through every model call
        and every push of the batch. A claim a crash abandons is released by
        :meth:`recover_stale_processing`.

        Returns:
            The claimed reminder, or None when nothing is due.
        """
        stmt = (
            select(Reminder)
            .where(Reminder.status == ReminderStatus.PENDING.value)
            .where(Reminder.trigger_at <= datetime.now(UTC))
            .order_by(Reminder.trigger_at.asc(), Reminder.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        reminder = (await self.db.execute(stmt)).scalar_one_or_none()
        if reminder is not None:
            reminder.status = ReminderStatus.PROCESSING.value
            await self.db.flush()
        return reminder

    async def get_processing_for_update(self, reminder_id: UUID) -> Reminder | None:
        """A claimed reminder, locked for its settlement — None when no longer claimed.

        The settlement of a notified reminder is conditioned on the claim still
        standing: a reminder its owner deleted meanwhile, or one released as
        stale and claimed again, is left to whoever holds it now.

        Args:
            reminder_id: The reminder claimed by :meth:`claim_next_due`.

        Returns:
            The row, locked until the caller commits, or None.
        """
        stmt = (
            select(Reminder)
            .where(Reminder.id == reminder_id)
            .where(Reminder.status == ReminderStatus.PROCESSING.value)
            .with_for_update()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def recover_stale_processing(self, timeout_minutes: int) -> int:
        """Release the claims a crashed worker left behind (crash recovery).

        A reminder PROCESSING for longer than ``timeout_minutes`` — measured on
        ``updated_at``, which the claim itself bumped — goes back to PENDING,
        so the next claim picks it up. The timeout must exceed the time one
        notification can take, or a live claim would be released under its
        worker.

        Args:
            timeout_minutes: Age past which a claim is considered abandoned.

        Returns:
            Number of released reminders (exact).
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)
        stmt = (
            update(Reminder)
            .where(Reminder.status == ReminderStatus.PROCESSING.value)
            .where(Reminder.updated_at < cutoff)
            .values(status=ReminderStatus.PENDING.value)
            .returning(Reminder.id)
        )
        released = list((await self.db.execute(stmt)).scalars().all())
        if released:
            logger.warning(
                "reminders_stale_claims_released",
                count=len(released),
                timeout_minutes=timeout_minutes,
            )
        return len(released)

    async def get_all_pending_for_user(self, user_id: UUID) -> list[Reminder]:
        """Every reminder still waiting, whatever its trigger time.

        Unlike `get_pending_for_user`, this one is not a page and takes no
        window: the timezone recalculation must see them all or it would move
        some clocks and not others.

        Args:
            user_id: Owner of the reminders.

        Returns:
            The pending reminders, oldest trigger first.
        """
        stmt = (
            select(Reminder)
            .where(Reminder.user_id == user_id)
            .where(Reminder.status == ReminderStatus.PENDING.value)
            .order_by(Reminder.trigger_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def cancel_reminder(self, reminder: Reminder) -> Reminder:
        """Cancel a pending reminder by deleting it completely."""
        reminder_id = reminder.id

        # Delete the reminder completely instead of setting status to CANCELLED
        await self.db.delete(reminder)
        await self.db.flush()

        logger.info(
            "reminder_deleted",
            reminder_id=str(reminder_id),
        )
        return reminder
