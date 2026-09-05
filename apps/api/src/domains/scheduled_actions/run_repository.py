"""Run history of the routines: written at the result, read by the week (ADR-265).

A separate module from :mod:`repository`: that file owns the routine rows and
the scheduler's locking, and it is frozen at its audited size. The run
repository has three operations and no ORM update path at all — a run row is
never modified.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.scheduled_actions.models import ScheduledActionRun, ScheduledRunOutcome

logger = structlog.get_logger(__name__)

#: The column bound of ``scheduled_actions.last_error`` applied here too: one
#: message, one ceiling.
RUN_ERROR_MAX_LENGTH = 2000


class ScheduledActionRunRepository:
    """Insert, read by week, purge by age."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        *,
        scheduled_action_id: UUID,
        user_id: UUID,
        slot_at: datetime | None,
        started_at: datetime,
        ended_at: datetime,
        outcome: ScheduledRunOutcome,
        attempts: int,
        manual: bool,
        error: str | None = None,
    ) -> ScheduledActionRun:
        """Insert one run row and flush it into the caller's transaction.

        Args:
            scheduled_action_id: The routine.
            user_id: Its owner.
            slot_at: The scheduled instant served, ``None`` for a rehearsal.
            started_at: When the tick started (UTC).
            ended_at: When the outcome was known (UTC).
            outcome: How it ended.
            attempts: Pipeline attempts made; 0 when the pipeline never ran.
            manual: Whether the user started it.
            error: The failure message, truncated here.

        Returns:
            The flushed row.
        """
        row = ScheduledActionRun(
            scheduled_action_id=scheduled_action_id,
            user_id=user_id,
            slot_at=slot_at,
            started_at=started_at,
            ended_at=ended_at,
            outcome=outcome,
            attempts=attempts,
            manual=manual,
            error=error[:RUN_ERROR_MAX_LENGTH] if error else None,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_since(self, user_id: UUID, since: datetime) -> list[ScheduledActionRun]:
        """Every run of an account started at or after ``since``, oldest first.

        Oldest first so a reader folding them per slot keeps the LAST one by
        simply overwriting — the latest attempt at a slot is its state.

        Args:
            user_id: Whose runs.
            since: Inclusive lower bound on ``started_at`` (UTC).

        Returns:
            The matching rows.
        """
        stmt = (
            select(ScheduledActionRun)
            .where(
                ScheduledActionRun.user_id == user_id,
                ScheduledActionRun.started_at >= since,
            )
            .order_by(ScheduledActionRun.started_at.asc(), ScheduledActionRun.id.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def purge_older_than(self, cutoff: datetime) -> int:
        """Delete every run started before ``cutoff``; the count is logged.

        Args:
            cutoff: Exclusive bound on ``started_at`` (UTC).

        Returns:
            How many rows went.
        """
        result = await self.db.execute(
            delete(ScheduledActionRun).where(ScheduledActionRun.started_at < cutoff)
        )
        # A DELETE yields a ``CursorResult``, which is what carries ``rowcount``
        # (same idiom as the effects repository); the async ``Result`` type
        # does not declare it.
        purged = int(result.rowcount or 0)  # type: ignore[attr-defined]
        if purged:
            logger.info(
                "scheduled_action_runs_purged",
                purged=purged,
                cutoff=cutoff.isoformat(),
            )
        return purged
