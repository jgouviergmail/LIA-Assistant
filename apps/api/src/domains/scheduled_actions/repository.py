"""
Scheduled Actions repository for database operations.

Includes anti-concurrence locking (FOR UPDATE SKIP LOCKED) for the scheduler,
stale execution recovery, and batch timezone recalculation.
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import Result, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.core.time_utils import now_utc
from src.domains.scheduled_actions.models import ScheduledAction, ScheduledActionStatus
from src.domains.users.models import User

logger = structlog.get_logger(__name__)


class ScheduledActionRepository(BaseRepository[ScheduledAction]):
    """Repository for scheduled action CRUD and scheduler operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, ScheduledAction)

    async def lock_creation_owner(self, user_id: UUID) -> None:
        """Hold one account reservation while counting and inserting its routines."""
        await self.db.execute(select(User.id).where(User.id == user_id).with_for_update())

    async def lock_owned(self, action_id: UUID, user_id: UUID) -> ScheduledAction | None:
        """Refresh and lock the exact owned row before reserving a manual run."""
        result: Result[tuple[ScheduledAction]] = await self.db.execute(
            select(ScheduledAction)
            .where(
                ScheduledAction.id == action_id,
                ScheduledAction.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_all_for_user(
        self,
        user_id: UUID,
        limit: int = 50,
        *,
        action_ids: Sequence[UUID] | None = None,
    ) -> list[ScheduledAction]:
        """Get all scheduled actions for a user, ordered by next trigger."""
        stmt = (
            select(ScheduledAction)
            .where(ScheduledAction.user_id == user_id)
            # NULLS LAST said out loud: PostgreSQL already does this for ASC,
            # but a finished series belongs at the end by CONTRACT, not by a
            # default another engine could spell differently.
            .order_by(ScheduledAction.next_trigger_at.asc().nullslast())
            .limit(limit)
        )
        if action_ids is not None:
            stmt = stmt.where(ScheduledAction.id.in_(action_ids))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def release_manual_execution(self, action_id: UUID, user_id: UUID, token: UUID) -> bool:
        """Cancel only this reservation, preserving the current configuration and clock."""
        result: Result[tuple[UUID]] = await self.db.execute(
            update(ScheduledAction)
            .where(
                ScheduledAction.id == action_id,
                ScheduledAction.user_id == user_id,
                ScheduledAction.status == ScheduledActionStatus.EXECUTING.value,
                ScheduledAction.execution_token == token,
            )
            .values(status=ScheduledActionStatus.ACTIVE.value, execution_token=None)
            .returning(ScheduledAction.id)
        )
        return result.scalar_one_or_none() is not None

    async def page_for_user(
        self, user_id: UUID, *, after_id: UUID | None, limit: int
    ) -> list[ScheduledAction]:
        """Owned rows in stable primary-key order, with one look-ahead row."""
        if not 1 <= limit <= 50:
            raise ValueError("Invalid routine page limit")
        stmt = (
            select(ScheduledAction)
            .where(ScheduledAction.user_id == user_id)
            .order_by(ScheduledAction.id.asc())
            .limit(limit + 1)
        )
        if after_id is not None:
            stmt = stmt.where(ScheduledAction.id > after_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def count_for_user(self, user_id: UUID) -> int:
        """Count scheduled actions for a user (for limit enforcement)."""
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(ScheduledAction)
            .where(ScheduledAction.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def close_finished(self) -> int:
        """Close the routines that have no future left (ADR-281, lot 5).

        A series ends three ways — a ``SeriesEnd`` date reached, an
        ``after_count`` exhausted, a single occurrence consumed — and all three
        land on the SAME state: ``next_trigger_at`` NULL, which the model
        already defines as « nothing follows ». Nothing closed such a routine,
        so it sat enabled and « active » for ever, indistinguishable from one
        the person had paused.

        Reading the end from ``next_trigger_at`` rather than from a column of
        its own is what keeps ONE authority on when a routine stops: the
        recurrence engine that arms it. An ``expires_at`` beside the series end
        would be a second answer to a question that has one — and only one of
        the two would be shown, edited and told in six languages.

        DISABLED, never deleted: the person must be able to see what they had
        posted. Idempotent by construction — the statement only matches rows
        still enabled and active, so the next tick finds nothing.

        Returns:
            How many routines were closed.
        """
        statement = (
            update(ScheduledAction)
            .where(
                ScheduledAction.is_enabled.is_(True),
                ScheduledAction.status == ScheduledActionStatus.ACTIVE.value,
                ScheduledAction.next_trigger_at.is_(None),
            )
            .values(
                is_enabled=False,
                status=ScheduledActionStatus.COMPLETED.value,
            )
            .returning(ScheduledAction.id)
        )
        return len((await self.db.execute(statement)).scalars().all())

    async def get_and_lock_due_actions(
        self,
        limit: int = 50,
    ) -> list[ScheduledAction]:
        """
        Get due actions AND lock them atomically for the scheduler.

        Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing:
        - Locks selected rows
        - Skips rows already locked by another transaction
        - Transitions status to EXECUTING

        Returns:
            List of actions transitioned to EXECUTING status.
        """
        current_time = now_utc()

        stmt = (
            select(ScheduledAction)
            .where(ScheduledAction.is_enabled.is_(True))
            .where(ScheduledAction.status == ScheduledActionStatus.ACTIVE.value)
            # A finished series carries a NULL trigger, and `NULL <= now()` is
            # UNKNOWN in SQL — so it is excluded here by construction rather
            # than by a filter someone must remember to write.
            .where(ScheduledAction.next_trigger_at <= current_time)
            .order_by(ScheduledAction.next_trigger_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        result = await self.db.execute(stmt)
        actions = list(result.scalars().all())

        # Immediately transition to EXECUTING
        for action in actions:
            action.status = ScheduledActionStatus.EXECUTING.value
            action.execution_token = uuid4()

        await self.db.flush()

        if actions:
            logger.info(
                "scheduled_actions_locked_for_execution",
                count=len(actions),
                action_ids=[str(a.id) for a in actions],
            )

        return actions

    async def recover_stale_executing(self, *, older_than: datetime) -> int:
        """
        Recover actions stuck in 'executing' status (crash recovery).

        A reservation untouched since ``older_than`` belongs to a dead tick: it
        is reset to 'active' so the scheduler can run the routine again. A live
        tick renews its reservation at each check, the last one right before
        the model runs (:meth:`renew_reservation`), so the caller's threshold —
        never below the worst case of a run — measures from the run's real start.

        Args:
            older_than: Reservations last touched before this instant are freed.

        Returns:
            Number of recovered actions.
        """
        stmt = (
            update(ScheduledAction)
            .where(ScheduledAction.status == ScheduledActionStatus.EXECUTING.value)
            .where(ScheduledAction.updated_at < older_than)
            .values(status=ScheduledActionStatus.ACTIVE.value, execution_token=None)
            .returning(ScheduledAction.id)
        )

        result = await self.db.execute(stmt)
        recovered_ids = list(result.scalars().all())

        if recovered_ids:
            logger.warning(
                "scheduled_actions_recovered_stale",
                count=len(recovered_ids),
                action_ids=[str(aid) for aid in recovered_ids],
                older_than=older_than.isoformat(),
            )

        return len(recovered_ids)

    async def renew_reservation(self, action_id: UUID, token: UUID) -> bool:
        """Renew the reservation ``token`` holds, and say whether it still holds it.

        One conditional statement: a tick whose reservation the recovery freed,
        and another tick took, renews nothing and must neither run nor settle.

        Args:
            action_id: The routine.
            token: The reservation the tick was handed.

        Returns:
            True when ``token`` still holds the routine (now renewed).
        """
        result: Result[tuple[UUID]] = await self.db.execute(
            update(ScheduledAction)
            .where(
                ScheduledAction.id == action_id,
                ScheduledAction.status == ScheduledActionStatus.EXECUTING.value,
                ScheduledAction.execution_token == token,
            )
            .values(updated_at=now_utc())
            .returning(ScheduledAction.id)
        )
        return result.scalar_one_or_none() is not None

    async def lock_reserved(self, action_id: UUID, token: UUID) -> ScheduledAction | None:
        """Refresh and lock the routine for the settle, while ``token`` holds it.

        The fence of the settle that follows a model run: the reservation may
        have expired meanwhile and been taken by another tick, whose state a
        late settle must not overwrite.

        Args:
            action_id: The routine.
            token: The reservation the tick was handed.

        Returns:
            The locked row, or None when another tick holds it now.
        """
        result: Result[tuple[ScheduledAction]] = await self.db.execute(
            select(ScheduledAction)
            .where(
                ScheduledAction.id == action_id,
                ScheduledAction.status == ScheduledActionStatus.EXECUTING.value,
                ScheduledAction.execution_token == token,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def reschedule(
        self,
        action: ScheduledAction,
        next_trigger_at: datetime | None,
        *,
        condition_state: dict | None = None,
    ) -> ScheduledAction:
        """Re-arm an action WITHOUT counting an execution (N-07).

        Used when a tick decides not to run the pipeline: condition not met,
        same fact already fired (dedup), or propose-first mode (the run then
        belongs to the chat, not to this scheduler). ``condition_state`` is a
        full NEW-dict replacement when provided (JSONB rule).
        """
        action.status = ScheduledActionStatus.ACTIVE.value
        action.execution_token = None
        action.next_trigger_at = next_trigger_at
        if condition_state is not None:
            action.condition_state = condition_state
        await self.db.flush()
        return action

    async def mark_execution_success(
        self,
        action: ScheduledAction,
        next_trigger_at: datetime | None,
        *,
        condition_state: dict | None = None,
    ) -> ScheduledAction:
        """Mark an action as successfully executed and schedule next trigger.

        ``condition_state`` (N-07): the dedup ledger written IN the same flush
        as the success — a full NEW-dict replacement (JSONB rule).
        """
        action.status = ScheduledActionStatus.ACTIVE.value
        action.execution_token = None
        action.last_executed_at = now_utc()
        action.execution_count += 1
        action.consecutive_failures = 0
        action.last_error = None
        action.next_trigger_at = next_trigger_at
        if condition_state is not None:
            action.condition_state = condition_state

        await self.db.flush()

        logger.info(
            "scheduled_action_execution_success",
            action_id=str(action.id),
            execution_count=action.execution_count,
            next_trigger_at=next_trigger_at.isoformat() if next_trigger_at else None,
        )

        return action

    async def mark_execution_failure(
        self,
        action: ScheduledAction,
        error: str,
        next_trigger_at: datetime | None,
        max_consecutive_failures: int = 5,
        *,
        condition_state: dict | None = None,
    ) -> ScheduledAction:
        """
        Mark an action as failed and schedule next trigger.

        If consecutive_failures >= max_consecutive_failures, auto-disable
        the action and set status to ERROR. ``condition_state`` (ADR-322): the
        ledger of a condition routine — its check happened, its new facts stay
        new — as a full NEW-dict replacement (JSONB rule).
        """
        action.consecutive_failures += 1
        action.execution_token = None
        action.last_error = error[:2000]  # Truncate error message
        action.next_trigger_at = next_trigger_at
        if condition_state is not None:
            action.condition_state = condition_state

        if action.consecutive_failures >= max_consecutive_failures:
            action.is_enabled = False
            action.status = ScheduledActionStatus.ERROR.value
            logger.warning(
                "scheduled_action_auto_disabled",
                action_id=str(action.id),
                consecutive_failures=action.consecutive_failures,
                last_error=error[:200],
            )
        else:
            action.status = ScheduledActionStatus.ACTIVE.value

        await self.db.flush()

        logger.warning(
            "scheduled_action_execution_failure",
            action_id=str(action.id),
            consecutive_failures=action.consecutive_failures,
            error=error[:200],
        )

        return action

    async def update_timezone_for_user(
        self,
        user_id: UUID,
        new_timezone: str,
        recalculated_triggers: dict[UUID, datetime | None],
    ) -> int:
        """
        Batch update timezone and next_trigger_at for the given user's actions,
        paused ones included (ADR-265).

        Args:
            user_id: User ID.
            new_timezone: New IANA timezone.
            recalculated_triggers: action_id -> new next_trigger_at (UTC), or
                None when the series is over.

        Returns:
            Number of updated actions.
        """
        count = 0
        for action_id, next_trigger in recalculated_triggers.items():
            stmt = (
                update(ScheduledAction)
                .where(ScheduledAction.id == action_id)
                .where(ScheduledAction.user_id == user_id)
                .values(
                    user_timezone=new_timezone,
                    next_trigger_at=next_trigger,
                )
            )
            await self.db.execute(stmt)
            count += 1

        await self.db.flush()

        if count:
            logger.info(
                "scheduled_actions_timezone_updated",
                user_id=str(user_id),
                new_timezone=new_timezone,
                updated_count=count,
            )

        return count
