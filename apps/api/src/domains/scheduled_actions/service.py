"""
Scheduled Actions service for business logic.

Handles CRUD operations, schedule recalculation, and timezone cascade updates.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import SCHEDULED_ACTIONS_MAX_PER_USER
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.core.recurrence import next_occurrence
from src.core.time_utils import now_utc
from src.domains.scheduled_actions.models import (
    ScheduledAction,
    ScheduledActionStatus,
    TriggerKind,
)
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.scheduled_actions.run_repository import ScheduledActionRunRepository
from src.domains.scheduled_actions.schemas import ScheduledActionCreate, ScheduledActionUpdate
from src.domains.scheduled_actions.week import ActionWeek, build_week, week_read_lower_bound

logger = structlog.get_logger(__name__)


class ScheduledActionService:
    """Service for scheduled action management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ScheduledActionRepository(db)
        self.run_repository = ScheduledActionRunRepository(db)

    async def get_with_ownership_check(
        self,
        action_id: UUID,
        user_id: UUID,
    ) -> ScheduledAction:
        """
        Get scheduled action with ownership verification.

        Raises:
            ResourceNotFoundError: If action doesn't exist or belongs to another user.
        """
        action = await self.repository.get_by_id(action_id)
        if not action or action.user_id != user_id:
            raise ResourceNotFoundError("scheduled_action", str(action_id))
        return action

    async def create(
        self,
        user_id: UUID,
        data: ScheduledActionCreate,
        user_timezone: str,
    ) -> ScheduledAction:
        """
        Create a new scheduled action.

        Enforces per-user limit, computes next_trigger_at from schedule + timezone.

        Raises:
            ValidationError: If user has reached the maximum limit.
        """
        # Enforce per-user limit
        count = await self.repository.count_for_user(user_id)
        if count >= SCHEDULED_ACTIONS_MAX_PER_USER:
            raise ValidationError(
                f"Maximum of {SCHEDULED_ACTIONS_MAX_PER_USER} scheduled actions per user"
            )

        # The first armed instant, from the engine that will re-arm it.
        next_trigger_at = next_occurrence(data.recurrence, user_timezone, after=now_utc())

        action = await self.repository.create(
            {
                "user_id": user_id,
                "title": data.title,
                "action_prompt": data.action_prompt,
                # A NEW dict, never a mutation: JSONB skips an in-place UPDATE.
                "recurrence": data.recurrence.model_dump(mode="json"),
                "user_timezone": user_timezone,
                # N-07: kind/condition/approval — schema-validated coherence.
                "trigger_kind": data.trigger_kind.value,
                "condition_config": (
                    data.condition_config.model_dump(exclude_none=True)
                    if data.condition_config
                    else None
                ),
                "requires_approval": data.requires_approval,
                "execution_mode": data.execution_mode,
                "next_trigger_at": next_trigger_at,
                "is_enabled": True,
                "status": ScheduledActionStatus.ACTIVE.value,
            }
        )

        logger.info(
            "scheduled_action_created",
            action_id=str(action.id),
            user_id=str(user_id),
            title=data.title,
            next_trigger_at=next_trigger_at.isoformat() if next_trigger_at else None,
        )

        return action

    async def update(
        self,
        action_id: UUID,
        user_id: UUID,
        data: ScheduledActionUpdate,
    ) -> ScheduledAction:
        """
        Update a scheduled action.

        Recalculates next_trigger_at if schedule fields change.

        Raises:
            ResourceNotFoundError: If action not found or wrong owner.
        """
        action = await self.get_with_ownership_check(action_id, user_id)

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return action

        # A changed recurrence re-arms the routine.
        schedule_changed = "recurrence" in update_data
        if schedule_changed:
            # `model_dump(exclude_unset=True)` already produced a plain dict;
            # re-serialise through the model so the stored shape is canonical
            # (dates as strings, tuples as lists) and is a NEW dict (JSONB).
            # The schema refuses an explicit null, so a present key always
            # carries a recurrence — no `if` left to get wrong here.
            assert data.recurrence is not None
            update_data["recurrence"] = data.recurrence.model_dump(mode="json")

        # N-07: kind/condition coherence against the RESULTING row (the update
        # schema cannot see the stored half of the pair).
        if "trigger_kind" in update_data:
            update_data["trigger_kind"] = update_data["trigger_kind"].value
        resulting_kind = update_data.get("trigger_kind", action.trigger_kind)
        resulting_config = update_data.get("condition_config", action.condition_config)
        if resulting_kind == TriggerKind.CONDITION.value and resulting_config is None:
            raise ValidationError("condition_config is required when trigger_kind is condition")
        if resulting_kind == TriggerKind.TIME.value and resulting_config is not None:
            # Switching back to time drops the condition + its dedup ledger.
            update_data["condition_config"] = None
            update_data["condition_state"] = None
        # A changed condition restarts its dedup ledger (a new fact space).
        # (`model_dump(exclude_unset=True)` already serialized it to a dict.)
        if update_data.get("condition_config") is not None:
            update_data["condition_state"] = None

        # Apply updates
        action = await self.repository.update(action, update_data)

        # Recalculate next_trigger_at if schedule changed
        if schedule_changed:
            next_trigger_at = next_occurrence(
                action.recurrence_spec, action.user_timezone, after=now_utc()
            )
            revived: dict[str, Any] = {"next_trigger_at": next_trigger_at}
            # Giving a CLOSED routine a future again puts it back to work
            # (ADR-281, lot 5). The executor closed it because its series had
            # nothing left; extend the series and that reason is gone, so the
            # same authority reopens it. Without this, someone pushing their
            # watch's end date back got a recomputed trigger on a row still
            # disabled — an edit that silently never runs.
            #
            # The rule is about WHO closed it: a PAUSE is the person's own
            # decision, and an edit is not a request to resume.
            if next_trigger_at is not None and action.status == (
                ScheduledActionStatus.COMPLETED.value
            ):
                revived["is_enabled"] = True
                revived["status"] = ScheduledActionStatus.ACTIVE.value
            action = await self.repository.update(action, revived)

            logger.info(
                "scheduled_action_trigger_recalculated",
                action_id=str(action_id),
                next_trigger_at=next_trigger_at.isoformat() if next_trigger_at else None,
                reason="schedule_update",
            )

        logger.info(
            "scheduled_action_updated",
            action_id=str(action_id),
            user_id=str(user_id),
            updated_fields=list(update_data.keys()),
        )

        return action

    async def delete(self, action_id: UUID, user_id: UUID) -> None:
        """
        Delete a scheduled action (hard delete).

        Raises:
            ResourceNotFoundError: If action not found or wrong owner.
        """
        action = await self.get_with_ownership_check(action_id, user_id)
        await self.repository.delete(action)

        logger.info(
            "scheduled_action_deleted",
            action_id=str(action_id),
            user_id=str(user_id),
        )

    async def toggle(self, action_id: UUID, user_id: UUID) -> ScheduledAction:
        """
        Toggle is_enabled for a scheduled action.

        When re-enabling, recalculates next_trigger_at and resets error state.

        Raises:
            ResourceNotFoundError: If action not found or wrong owner.
        """
        action = await self.get_with_ownership_check(action_id, user_id)

        new_enabled = not action.is_enabled
        update_data: dict = {"is_enabled": new_enabled}

        if new_enabled:
            # Re-enabling: recalculate next trigger and reset error state
            next_trigger_at = next_occurrence(
                action.recurrence_spec, action.user_timezone, after=now_utc()
            )
            update_data["next_trigger_at"] = next_trigger_at
            update_data["status"] = ScheduledActionStatus.ACTIVE.value
            update_data["consecutive_failures"] = 0
            update_data["last_error"] = None

        action = await self.repository.update(action, update_data)

        logger.info(
            "scheduled_action_toggled",
            action_id=str(action_id),
            user_id=str(user_id),
            is_enabled=new_enabled,
        )

        return action

    async def list_for_user(self, user_id: UUID) -> list[ScheduledAction]:
        """List all scheduled actions for a user."""
        return await self.repository.get_all_for_user(user_id)

    async def week_for_user(
        self, user_id: UUID, *, now: datetime | None = None
    ) -> list[ActionWeek]:
        """The current week of every routine of a user (ADR-265).

        Two reads — the routines, then the run rows since the earliest local
        Monday across their zones — folded by :func:`build_week`, which owns
        the rule and its tests.

        Args:
            user_id: Whose routines.
            now: Reference instant (UTC). Defaults to now.

        Returns:
            One entry per routine, paused ones included, in list order.
        """
        actions = await self.repository.get_all_for_user(user_id)
        since = week_read_lower_bound(actions, now=now)
        runs = await self.run_repository.list_since(user_id, since) if since else []
        return build_week(actions, runs, now=now)

    async def recalculate_all_for_user(
        self,
        user_id: UUID,
        new_timezone: str,
    ) -> int:
        """
        Recalculate EVERY action of a user after a timezone change.

        The user changed their timezone, so we keep the same local time
        (e.g. 19:30) but recalculate the UTC trigger with the new timezone.

        Paused routines are covered too (ADR-265). Skipping them left their
        ``user_timezone`` on the OLD zone, and both re-enabling (``toggle``)
        and editing (``update``) re-derive the trigger from that stored
        zone: a routine paused across a move woke up on the old clock, and
        the weekly timeline drew it on a different axis from its siblings.
        A paused routine's ``next_trigger_at`` is inert until it is
        re-enabled, so recomputing it costs nothing and keeps the row
        coherent.

        Returns:
            Number of updated actions.
        """
        actions = await self.repository.get_all_for_user(user_id)

        reference = now_utc()
        recalculated: dict[UUID, datetime | None] = {}
        for action in actions:
            # The spec is a LOCAL wall clock: moving zone keeps "08:00 where I
            # live" and only changes the instant it lands on.
            recalculated[action.id] = next_occurrence(
                action.recurrence_spec, new_timezone, after=reference
            )

        if not recalculated:
            return 0

        count = await self.repository.update_timezone_for_user(
            user_id=user_id,
            new_timezone=new_timezone,
            recalculated_triggers=recalculated,
        )

        logger.info(
            "scheduled_actions_timezone_recalculated",
            user_id=str(user_id),
            new_timezone=new_timezone,
            recalculated_count=count,
        )

        return count
