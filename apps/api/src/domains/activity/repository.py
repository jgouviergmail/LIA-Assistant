"""Read-only aggregation repository for the activity timeline (Lot 1-A1).

Cross-domain READ model: queries the source domains' tables directly
(same reuse doctrine as ``briefing/fetchers.py`` importing other domains'
repositories). Never writes. Statement builders are pure module-level
functions so unit tests can assert the compiled SQL predicates without a
database.

Counting doctrine (ADR-185): every total is an exact ``COUNT(*)`` over the
whole window; rows only are capped. A cap is stated by the caller
(``truncated`` flag), never applied in silence.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, or_, select

from src.domains.activity.constants import TIMELINE_JOURNAL_SOURCES
from src.domains.habits.models import UserHabit
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.interests.models import InterestNotification
from src.domains.journals.models import JournalEntry, JournalEntryStatus
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
from src.domains.scheduled_actions.models import ScheduledAction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_ENDED_LOOP_STATUSES = (OpenLoopStatus.CLOSED.value, OpenLoopStatus.EXPIRED.value)

_RowT = TypeVar("_RowT")


# =============================================================================
# Pure statement builders (unit-testable WHERE clauses)
# =============================================================================


def heartbeat_rows_stmt(
    user_id: UUID, since: datetime, cap: int
) -> Select[tuple[HeartbeatNotification]]:
    """Heartbeat notifications in the window, newest first, capped."""
    return (
        select(HeartbeatNotification)
        .where(
            HeartbeatNotification.user_id == user_id,
            HeartbeatNotification.created_at >= since,
        )
        .order_by(HeartbeatNotification.created_at.desc())
        .limit(cap)
    )


def interest_rows_stmt(
    user_id: UUID, since: datetime, cap: int
) -> Select[tuple[InterestNotification]]:
    """Interest notifications in the window, newest first, capped."""
    return (
        select(InterestNotification)
        .where(
            InterestNotification.user_id == user_id,
            InterestNotification.created_at >= since,
        )
        .order_by(InterestNotification.created_at.desc())
        .limit(cap)
    )


def journal_rows_stmt(user_id: UUID, since: datetime, cap: int) -> Select[tuple[JournalEntry]]:
    """ACTIVE automatic journal entries in the window (manual excluded)."""
    return (
        select(JournalEntry)
        .where(
            JournalEntry.user_id == user_id,
            JournalEntry.created_at >= since,
            JournalEntry.status == JournalEntryStatus.ACTIVE.value,
            JournalEntry.source.in_(TIMELINE_JOURNAL_SOURCES),
        )
        .order_by(JournalEntry.created_at.desc())
        .limit(cap)
    )


def habit_rows_stmt(user_id: UUID, since: datetime, cap: int) -> Select[tuple[UserHabit]]:
    """Habits DETECTED in the window (whatever their current status)."""
    return (
        select(UserHabit)
        .where(UserHabit.user_id == user_id, UserHabit.created_at >= since)
        .order_by(UserHabit.created_at.desc())
        .limit(cap)
    )


def open_loop_rows_stmt(user_id: UUID, since: datetime, cap: int) -> Select[tuple[OpenLoop]]:
    """Loops with a lifecycle event in the window (created, or ended).

    ``updated_at`` is an honest end timestamp: a loop leaves OPEN exactly
    once (repository docstring contract) and is never touched afterwards.
    """
    return (
        select(OpenLoop)
        .where(
            OpenLoop.user_id == user_id,
            or_(
                OpenLoop.created_at >= since,
                (OpenLoop.status.in_(_ENDED_LOOP_STATUSES)) & (OpenLoop.updated_at >= since),
            ),
        )
        .order_by(OpenLoop.updated_at.desc())
        .limit(cap)
    )


def scheduled_action_rows_stmt(
    user_id: UUID, since: datetime, cap: int
) -> Select[tuple[ScheduledAction]]:
    """Scheduled actions whose LAST execution falls in the window.

    There is no runs table: one event per action (its most recent run),
    a documented v1 limitation — never a per-run history claim.
    """
    return (
        select(ScheduledAction)
        .where(
            ScheduledAction.user_id == user_id,
            ScheduledAction.last_executed_at.is_not(None),
            ScheduledAction.last_executed_at >= since,
        )
        .order_by(ScheduledAction.last_executed_at.desc())
        .limit(cap)
    )


def _count_from(stmt: Select[tuple[_RowT]]) -> Select[tuple[int]]:
    """Exact COUNT(*) over a rows statement's WHERE (order/limit stripped)."""
    return select(func.count()).select_from(stmt.order_by(None).limit(None).subquery())


def open_loops_created_count_stmt(user_id: UUID, since: datetime) -> Select[tuple[int]]:
    """Exact count of loops CREATED in the window."""
    return select(func.count()).where(OpenLoop.user_id == user_id, OpenLoop.created_at >= since)


def open_loops_closed_count_stmt(user_id: UUID, since: datetime) -> Select[tuple[int]]:
    """Exact count of loops ENDED (closed or expired) in the window."""
    return select(func.count()).where(
        OpenLoop.user_id == user_id,
        OpenLoop.status.in_(_ENDED_LOOP_STATUSES),
        OpenLoop.updated_at >= since,
    )


# =============================================================================
# Repository
# =============================================================================


class ActivityReadRepository:
    """Thin executor over the pure statement builders. Read-only."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind to an AsyncSession owned by the calling fetcher."""
        self.db = db

    async def _rows_and_count(self, rows_stmt: Select[tuple[_RowT]]) -> tuple[list[_RowT], int]:
        rows = list((await self.db.execute(rows_stmt)).scalars().all())
        total = (await self.db.execute(_count_from(rows_stmt))).scalar_one()
        return rows, int(total)

    async def heartbeat_notifications_since(
        self, user_id: UUID, since: datetime, cap: int
    ) -> tuple[list[HeartbeatNotification], int]:
        """Windowed heartbeat notifications + exact total."""
        return await self._rows_and_count(heartbeat_rows_stmt(user_id, since, cap))

    async def interest_notifications_since(
        self, user_id: UUID, since: datetime, cap: int
    ) -> tuple[list[InterestNotification], int]:
        """Windowed interest notifications + exact total."""
        return await self._rows_and_count(interest_rows_stmt(user_id, since, cap))

    async def journal_entries_since(
        self, user_id: UUID, since: datetime, cap: int
    ) -> tuple[list[JournalEntry], int]:
        """Windowed automatic journal entries + exact total."""
        return await self._rows_and_count(journal_rows_stmt(user_id, since, cap))

    async def habits_since(
        self, user_id: UUID, since: datetime, cap: int
    ) -> tuple[list[UserHabit], int]:
        """Windowed detected habits + exact total."""
        return await self._rows_and_count(habit_rows_stmt(user_id, since, cap))

    async def open_loops_since(
        self, user_id: UUID, since: datetime, cap: int
    ) -> tuple[list[OpenLoop], int, int]:
        """Windowed loop rows + exact created/ended totals (two counts)."""
        rows = list(
            (await self.db.execute(open_loop_rows_stmt(user_id, since, cap))).scalars().all()
        )
        created = (
            await self.db.execute(open_loops_created_count_stmt(user_id, since))
        ).scalar_one()
        closed = (await self.db.execute(open_loops_closed_count_stmt(user_id, since))).scalar_one()
        return rows, int(created), int(closed)

    async def scheduled_action_runs_since(
        self, user_id: UUID, since: datetime, cap: int
    ) -> tuple[list[ScheduledAction], int]:
        """Windowed last-executions + exact total."""
        return await self._rows_and_count(scheduled_action_rows_stmt(user_id, since, cap))
