"""
Reminder repository for database operations.

Includes anti-concurrence locking for scheduler.

Phase: Reminders with FCM notifications
Created: 2025-12-28
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
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
    ) -> list[Reminder]:
        """Get pending reminders for a user."""
        stmt = (
            select(Reminder)
            .where(Reminder.user_id == user_id)
            .where(Reminder.status == ReminderStatus.PENDING.value)
            .order_by(Reminder.trigger_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

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

    async def get_and_lock_pending_reminders(
        self,
        limit: int = 100,
    ) -> list[Reminder]:
        """
        Get pending reminders due for notification AND lock them atomically.

        Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing:
        - Locks selected rows
        - Skips rows already locked by another transaction
        - Prevents duplicate notifications

        Returns:
            List of reminders transitioned to PROCESSING status
        """
        now = datetime.now(UTC)

        stmt = (
            select(Reminder)
            .where(Reminder.status == ReminderStatus.PENDING.value)
            .where(Reminder.trigger_at <= now)
            .order_by(Reminder.trigger_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        result = await self.db.execute(stmt)
        reminders = list(result.scalars().all())

        # Immediately transition to PROCESSING to release lock
        for reminder in reminders:
            reminder.status = ReminderStatus.PROCESSING.value

        await self.db.flush()

        if reminders:
            logger.info(
                "reminders_locked_for_processing",
                count=len(reminders),
                reminder_ids=[str(r.id) for r in reminders],
            )

        return reminders

    async def cancel_reminder(self, reminder: Reminder) -> Reminder:
        """Cancel a pending reminder by deleting it completely."""
        reminder_id = reminder.id
        reminder_content = reminder.content

        # Delete the reminder completely instead of setting status to CANCELLED
        await self.db.delete(reminder)
        await self.db.flush()

        logger.info(
            "reminder_deleted",
            reminder_id=str(reminder_id),
            content=reminder_content,
        )
        return reminder
