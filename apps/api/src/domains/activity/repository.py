"""Owned, windowed timeline reads; literal matching precedes every source cap.

Each source returns rows and an exact total from one SQL snapshot. Creation
and closure are separate streams because their ordering dates differ.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, SQLColumnExpression, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, raiseload

from src.domains.activity.constants import TIMELINE_JOURNAL_SOURCES
from src.domains.activity.schemas import ActivityCriteria
from src.domains.habits.models import UserHabit
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.interests.models import InterestNotification
from src.domains.journals.models import JournalEntry, JournalEntryStatus
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.shared.display_queries import read_display_rows

_ENDED_LOOP_STATUSES = (OpenLoopStatus.CLOSED.value, OpenLoopStatus.EXPIRED.value)


def _ordered[T](
    statement: Select[tuple[T]],
    instant: SQLColumnExpression[datetime | None],
    identity: SQLColumnExpression[UUID],
    cap: int,
    criteria: ActivityCriteria | None,
) -> Select[tuple[T]]:
    """Apply the upper instant and stable direction before the source cap."""
    query = criteria or ActivityCriteria()
    if query.as_of is not None:
        statement = statement.where(instant <= query.as_of)
    order = instant.asc() if query.sort == "oldest" else instant.desc()
    return statement.options(raiseload("*")).order_by(order, identity.asc()).limit(cap)


def heartbeat_rows_stmt(
    user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
) -> Select[tuple[HeartbeatNotification]]:
    """Heartbeat notifications owned by the reader, ordered on their send instant."""
    return _ordered(
        select(HeartbeatNotification)
        .options(
            load_only(
                HeartbeatNotification.id,
                HeartbeatNotification.created_at,
                HeartbeatNotification.content,
                HeartbeatNotification.priority,
                raiseload=True,
            )
        )
        .where(
            HeartbeatNotification.user_id == user_id,
            HeartbeatNotification.created_at >= since,
        ),
        HeartbeatNotification.created_at,
        HeartbeatNotification.id,
        cap,
        criteria,
    )


def interest_rows_stmt(
    user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
) -> Select[tuple[InterestNotification]]:
    """Interest notifications owned by the reader; historical content may be null."""
    return _ordered(
        select(InterestNotification)
        .options(
            load_only(
                InterestNotification.id,
                InterestNotification.created_at,
                InterestNotification.content,
                raiseload=True,
            )
        )
        .where(
            InterestNotification.user_id == user_id,
            InterestNotification.created_at >= since,
        ),
        InterestNotification.created_at,
        InterestNotification.id,
        cap,
        criteria,
    )


def journal_rows_stmt(
    user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
) -> Select[tuple[JournalEntry]]:
    """Active automatic entries only; manual and archived entries are not proactive work."""
    return _ordered(
        select(JournalEntry)
        .options(
            load_only(
                JournalEntry.id,
                JournalEntry.created_at,
                JournalEntry.title,
                JournalEntry.source,
                raiseload=True,
            )
        )
        .where(
            JournalEntry.user_id == user_id,
            JournalEntry.created_at >= since,
            JournalEntry.status == JournalEntryStatus.ACTIVE.value,
            JournalEntry.source.in_(TIMELINE_JOURNAL_SOURCES),
        ),
        JournalEntry.created_at,
        JournalEntry.id,
        cap,
        criteria,
    )


def habit_rows_stmt(
    user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
) -> Select[tuple[UserHabit]]:
    """Detection is the creation date, whatever the habit's current status."""
    return _ordered(
        select(UserHabit)
        .options(
            load_only(
                UserHabit.id,
                UserHabit.created_at,
                UserHabit.key,
                UserHabit.status,
                raiseload=True,
            )
        )
        .where(
            UserHabit.user_id == user_id,
            UserHabit.created_at >= since,
        ),
        UserHabit.created_at,
        UserHabit.id,
        cap,
        criteria,
    )


def open_loops_created_rows_stmt(
    user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
) -> Select[tuple[OpenLoop]]:
    """Creation events have their own ordered pool, independent of later closure."""
    return _ordered(
        select(OpenLoop)
        .options(
            load_only(
                OpenLoop.id,
                OpenLoop.subject,
                OpenLoop.status,
                OpenLoop.closed_reason,
                OpenLoop.created_at,
                OpenLoop.updated_at,
                raiseload=True,
            )
        )
        .where(
            OpenLoop.user_id == user_id,
            OpenLoop.created_at >= since,
        ),
        OpenLoop.created_at,
        OpenLoop.id,
        cap,
        criteria,
    )


def open_loops_closed_rows_stmt(
    user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
) -> Select[tuple[OpenLoop]]:
    """A loop ends once; its final update is its closure instant."""
    return _ordered(
        select(OpenLoop)
        .options(
            load_only(
                OpenLoop.id,
                OpenLoop.subject,
                OpenLoop.status,
                OpenLoop.closed_reason,
                OpenLoop.created_at,
                OpenLoop.updated_at,
                raiseload=True,
            )
        )
        .where(
            OpenLoop.user_id == user_id,
            OpenLoop.updated_at >= since,
            OpenLoop.status.in_(_ENDED_LOOP_STATUSES),
        ),
        OpenLoop.updated_at,
        OpenLoop.id,
        cap,
        criteria,
    )


def scheduled_action_rows_stmt(
    user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
) -> Select[tuple[ScheduledAction]]:
    """One last-execution event per routine; this is not its run history."""
    return _ordered(
        select(ScheduledAction)
        .options(
            load_only(
                ScheduledAction.id,
                ScheduledAction.title,
                ScheduledAction.last_executed_at,
                raiseload=True,
            )
        )
        .where(
            ScheduledAction.user_id == user_id,
            ScheduledAction.last_executed_at.is_not(None),
            ScheduledAction.last_executed_at >= since,
        ),
        ScheduledAction.last_executed_at,
        ScheduledAction.id,
        cap,
        criteria,
    )


class ActivityReadRepository:
    """Cross-domain read model on a session owned by one source fetcher."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def heartbeat_notifications_since(
        self, user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
    ) -> tuple[list[HeartbeatNotification], int]:
        """Match the notification content this timeline renders."""
        return await read_display_rows(
            self.db,
            heartbeat_rows_stmt(user_id, since, cap, criteria),
            query=criteria.q if criteria else "",
            text_of=lambda row: row.content,
            cap=cap,
        )

    async def interest_notifications_since(
        self, user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
    ) -> tuple[list[InterestNotification], int]:
        """Match rendered content, not a hidden topic or prompt."""
        return await read_display_rows(
            self.db,
            interest_rows_stmt(user_id, since, cap, criteria),
            query=criteria.q if criteria else "",
            text_of=lambda row: row.content,
            cap=cap,
        )

    async def journal_entries_since(
        self, user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
    ) -> tuple[list[JournalEntry], int]:
        """Match the rendered entry title."""
        return await read_display_rows(
            self.db,
            journal_rows_stmt(user_id, since, cap, criteria),
            query=criteria.q if criteria else "",
            text_of=lambda row: row.title,
            cap=cap,
        )

    async def habits_since(
        self, user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
    ) -> tuple[list[UserHabit], int]:
        """Match the displayed detection key."""
        return await read_display_rows(
            self.db,
            habit_rows_stmt(user_id, since, cap, criteria),
            query=criteria.q if criteria else "",
            text_of=lambda row: row.key,
            cap=cap,
        )

    async def open_loops_created_since(
        self, user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
    ) -> tuple[list[OpenLoop], int]:
        """Read the complete creation count and its own ordered matching prefix."""
        return await read_display_rows(
            self.db,
            open_loops_created_rows_stmt(user_id, since, cap, criteria),
            query=criteria.q if criteria else "",
            text_of=lambda row: row.subject,
            cap=cap,
        )

    async def open_loops_closed_since(
        self, user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
    ) -> tuple[list[OpenLoop], int]:
        """Read the complete closure count and its own ordered matching prefix."""
        return await read_display_rows(
            self.db,
            open_loops_closed_rows_stmt(user_id, since, cap, criteria),
            query=criteria.q if criteria else "",
            text_of=lambda row: row.subject,
            cap=cap,
        )

    async def scheduled_action_runs_since(
        self, user_id: UUID, since: datetime, cap: int, criteria: ActivityCriteria | None = None
    ) -> tuple[list[ScheduledAction], int]:
        """Read routines' last execution, matching only their displayed title."""
        return await read_display_rows(
            self.db,
            scheduled_action_rows_stmt(user_id, since, cap, criteria),
            query=criteria.q if criteria else "",
            text_of=lambda row: row.title,
            cap=cap,
        )
