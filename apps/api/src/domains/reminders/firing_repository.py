"""Persistence of the occurrences of reminders that rang (ADR-268 amendment 2026-11-16)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.reminders.models import ReminderFiring


class ReminderFiringRepository(BaseRepository[ReminderFiring]):
    """Reads and writes of ``reminder_firings``, always scoped to an owner."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, ReminderFiring)

    async def get_owned(self, firing_id: UUID, user_id: UUID) -> ReminderFiring | None:
        """The occurrence, when this account owns it.

        Args:
            firing_id: The occurrence a press names.
            user_id: The caller.

        Returns:
            The row, or None for an unknown id AND for another account's — the
            same answer, so an id cannot be probed.
        """
        statement = select(ReminderFiring).where(
            ReminderFiring.id == firing_id, ReminderFiring.user_id == user_id
        )
        return (await self.db.execute(statement)).scalar_one_or_none()

    async def lock_owned(self, firing_id: UUID, user_id: UUID) -> ReminderFiring | None:
        """The owned occurrence, locked until the caller's transaction ends.

        Two presses on the same occurrence — two devices, a double tap — are
        serialised here: the second reads what the first committed.

        Args:
            firing_id: The occurrence a press names.
            user_id: The caller.

        Returns:
            The locked row, or None (unknown or another account's).
        """
        statement = (
            select(ReminderFiring)
            .where(ReminderFiring.id == firing_id, ReminderFiring.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.db.execute(statement)).scalar_one_or_none()

    async def purge_fired_before(self, cutoff: datetime, *, limit: int) -> int:
        """Delete up to ``limit`` occurrences that rang before ``cutoff``.

        One bounded statement per call, oldest first; a row another transaction
        holds (a press being answered) is skipped and taken at the next call.

        Args:
            cutoff: Occurrences that rang before it can no longer be postponed.
            limit: The most rows one call deletes.

        Returns:
            The exact number of rows deleted.
        """
        doomed = (
            select(ReminderFiring.id)
            .where(ReminderFiring.fired_at < cutoff)
            .order_by(ReminderFiring.fired_at.asc(), ReminderFiring.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(
            delete(ReminderFiring).where(ReminderFiring.id.in_(doomed)).returning(ReminderFiring.id)
        )
        return len(result.scalars().all())
