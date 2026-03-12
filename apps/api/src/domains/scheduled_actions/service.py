"""
Scheduled Actions service for business logic.

Handles CRUD operations, schedule recalculation, and timezone cascade updates.
"""

from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import SCHEDULED_ACTIONS_MAX_PER_USER
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.domains.scheduled_actions.models import ScheduledAction, ScheduledActionStatus
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.scheduled_actions.schedule_helpers import compute_next_trigger_utc
from src.domains.scheduled_actions.schemas import ScheduledActionCreate, ScheduledActionUpdate

logger = structlog.get_logger(__name__)


class ScheduledActionService:
    """Service for scheduled action management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ScheduledActionRepository(db)

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

        # Compute next trigger time in UTC
        next_trigger_at = compute_next_trigger_utc(
            days_of_week=data.days_of_week,
            hour=data.trigger_hour,
            minute=data.trigger_minute,
            user_timezone=user_timezone,
        )

        action = await self.repository.create(
            {
                "user_id": user_id,
                "title": data.title,
                "action_prompt": data.action_prompt,
                "days_of_week": sorted(data.days_of_week),
                "trigger_hour": data.trigger_hour,
                "trigger_minute": data.trigger_minute,
                "user_timezone": user_timezone,
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
            next_trigger_at=next_trigger_at.isoformat(),
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

        # Determine if schedule changed (requires next_trigger_at recalculation)
        schedule_fields = {"days_of_week", "trigger_hour", "trigger_minute"}
        schedule_changed = bool(schedule_fields & set(update_data.keys()))

        # Sort days_of_week if provided
        if "days_of_week" in update_data:
            update_data["days_of_week"] = sorted(update_data["days_of_week"])

        # Apply updates
        action = await self.repository.update(action, update_data)

        # Recalculate next_trigger_at if schedule changed
        if schedule_changed:
            next_trigger_at = compute_next_trigger_utc(
                days_of_week=action.days_of_week,
                hour=action.trigger_hour,
                minute=action.trigger_minute,
                user_timezone=action.user_timezone,
            )
            action = await self.repository.update(action, {"next_trigger_at": next_trigger_at})

            logger.info(
                "scheduled_action_trigger_recalculated",
                action_id=str(action_id),
                next_trigger_at=next_trigger_at.isoformat(),
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
            next_trigger_at = compute_next_trigger_utc(
                days_of_week=action.days_of_week,
                hour=action.trigger_hour,
                minute=action.trigger_minute,
                user_timezone=action.user_timezone,
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

    async def recalculate_all_for_user(
        self,
        user_id: UUID,
        new_timezone: str,
    ) -> int:
        """
        Recalculate all enabled actions for a user after timezone change.

        The user changed their timezone, so we keep the same local time
        (e.g. 19:30) but recalculate the UTC trigger with the new timezone.

        Returns:
            Number of updated actions.
        """
        actions = await self.repository.get_all_for_user(user_id)

        recalculated: dict[UUID, datetime] = {}
        for action in actions:
            if not action.is_enabled:
                continue
            next_trigger = compute_next_trigger_utc(
                days_of_week=action.days_of_week,
                hour=action.trigger_hour,
                minute=action.trigger_minute,
                user_timezone=new_timezone,
            )
            recalculated[action.id] = next_trigger

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
