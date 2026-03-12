"""
Scheduled Actions repository for database operations.

Includes anti-concurrence locking (FOR UPDATE SKIP LOCKED) for the scheduler,
stale execution recovery, and batch timezone recalculation.
"""

from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.core.time_utils import now_utc
from src.domains.scheduled_actions.models import ScheduledAction, ScheduledActionStatus

logger = structlog.get_logger(__name__)


class ScheduledActionRepository(BaseRepository[ScheduledAction]):
    """Repository for scheduled action CRUD and scheduler operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, ScheduledAction)

    async def get_all_for_user(
        self,
        user_id: UUID,
        limit: int = 50,
    ) -> list[ScheduledAction]:
        """Get all scheduled actions for a user, ordered by next trigger."""
        stmt = (
            select(ScheduledAction)
            .where(ScheduledAction.user_id == user_id)
            .order_by(ScheduledAction.next_trigger_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

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

        await self.db.flush()

        if actions:
            logger.info(
                "scheduled_actions_locked_for_execution",
                count=len(actions),
                action_ids=[str(a.id) for a in actions],
            )

        return actions

    async def recover_stale_executing(self, timeout_minutes: int = 10) -> int:
        """
        Recover actions stuck in 'executing' status (crash recovery).

        If an action has been in 'executing' for longer than the timeout,
        reset it to 'active' so the scheduler can retry.

        Returns:
            Number of recovered actions.
        """
        from datetime import timedelta

        cutoff = now_utc() - timedelta(minutes=timeout_minutes)

        stmt = (
            update(ScheduledAction)
            .where(ScheduledAction.status == ScheduledActionStatus.EXECUTING.value)
            .where(ScheduledAction.updated_at < cutoff)
            .values(status=ScheduledActionStatus.ACTIVE.value)
            .returning(ScheduledAction.id)
        )

        result = await self.db.execute(stmt)
        recovered_ids = list(result.scalars().all())

        if recovered_ids:
            logger.warning(
                "scheduled_actions_recovered_stale",
                count=len(recovered_ids),
                action_ids=[str(aid) for aid in recovered_ids],
                timeout_minutes=timeout_minutes,
            )

        return len(recovered_ids)

    async def mark_execution_success(
        self,
        action: ScheduledAction,
        next_trigger_at: datetime,
    ) -> ScheduledAction:
        """Mark an action as successfully executed and schedule next trigger."""
        action.status = ScheduledActionStatus.ACTIVE.value
        action.last_executed_at = now_utc()
        action.execution_count += 1
        action.consecutive_failures = 0
        action.last_error = None
        action.next_trigger_at = next_trigger_at

        await self.db.flush()

        logger.info(
            "scheduled_action_execution_success",
            action_id=str(action.id),
            execution_count=action.execution_count,
            next_trigger_at=next_trigger_at.isoformat(),
        )

        return action

    async def mark_execution_failure(
        self,
        action: ScheduledAction,
        error: str,
        next_trigger_at: datetime,
        max_consecutive_failures: int = 5,
    ) -> ScheduledAction:
        """
        Mark an action as failed and schedule next trigger.

        If consecutive_failures >= max_consecutive_failures, auto-disable
        the action and set status to ERROR.
        """
        action.consecutive_failures += 1
        action.last_error = error[:2000]  # Truncate error message
        action.next_trigger_at = next_trigger_at

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
        recalculated_triggers: dict[UUID, datetime],
    ) -> int:
        """
        Batch update timezone and next_trigger_at for all user's enabled actions.

        Args:
            user_id: User ID.
            new_timezone: New IANA timezone.
            recalculated_triggers: Mapping of action_id -> new next_trigger_at (UTC).

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
