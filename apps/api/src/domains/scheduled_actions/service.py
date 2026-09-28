"""
Scheduled Actions service for business logic.

Handles CRUD operations, schedule recalculation, and timezone cascade updates.
When a routine next runs is asked of ONE place, ``trigger.TriggerPlan``: a
schedule for a time routine, the system's checks for a condition routine
(ADR-322).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import SCHEDULED_ACTIONS_MAX_PER_USER
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.core.recurrence import RecurrenceSpec
from src.core.time_utils import now_utc
from src.domains.scheduled_actions.models import (
    ScheduledAction,
    ScheduledActionStatus,
    TriggerKind,
)
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.scheduled_actions.run_repository import ScheduledActionRunRepository
from src.domains.scheduled_actions.schemas import (
    ScheduledActionCreate,
    ScheduledActionUpdate,
    trigger_mode_refusal,
)
from src.domains.scheduled_actions.trigger import (
    CONDITION_UNTIL_KEY,
    TriggerPlan,
    condition_until,
)
from src.domains.scheduled_actions.week import ActionWeek, build_week, week_read_lower_bound

logger = structlog.get_logger(__name__)


def _refuse_a_past_last_day(condition_config: Mapping[str, Any] | None, timezone: str) -> None:
    """A watch cannot be set to end on a day that is already over.

    Checked only where the person SETS the day (creation, an edited
    condition): renaming a watch that finished long ago must still work.

    Args:
        condition_config: The condition as it will be stored.
        timezone: The routine's zone — « today » is the routine's today.

    Raises:
        ValidationError: When the last watched day is before today.
    """
    until = condition_until(condition_config)
    if until is not None and until < now_utc().astimezone(ZoneInfo(timezone)).date():
        raise ValidationError("until cannot be a day that is already over")


def _fact_space(condition_config: Mapping[str, Any] | None) -> dict[str, Any]:
    """What a condition watches FOR — its config without its last day.

    Moving the last day watches the same facts a little longer; anything else
    watches different facts, and the ledger of the old ones means nothing.
    """
    return {k: v for k, v in (condition_config or {}).items() if k != CONDITION_UNTIL_KEY}


@dataclass(frozen=True, slots=True)
class _TriggerEdit:
    """What an update does to a routine's clock."""

    values: dict[str, Any]
    """The column values to write, the other mode's fields dropped."""
    plan: TriggerPlan
    """The resulting routine's plan."""
    rearm: bool
    """Whether anything its clock reads changed."""


def _trigger_edit(
    action: ScheduledAction, data: ScheduledActionUpdate, values: dict[str, Any]
) -> _TriggerEdit:
    """Apply an update to the routine's clock, against the RESULTING row.

    The update schema cannot see the stored half of the pair, so the mode rule
    (``trigger_mode_refusal``) is checked here on what the row will be. Switching
    mode drops what the OTHER mode stored — never what the payload sent: a
    condition sent with a recurrence is refused, not silently trimmed.

    Args:
        action: The stored routine.
        data: The validated update.
        values: ``data.model_dump(exclude_unset=True)`` — rewritten here.

    Returns:
        The values to write, the resulting plan, and whether to re-arm.

    Raises:
        ValidationError: When the resulting row would not have exactly one clock,
            or a new last day is already over.
    """
    rearm = not _CLOCK_FIELDS.isdisjoint(values)
    values = _serialised(data, values)
    kind, recurrence, config = _resulting_clock(action, values)
    refusal = trigger_mode_refusal(
        kind, has_recurrence=recurrence is not None, has_condition=config is not None
    )
    if refusal:
        raise ValidationError(refusal)
    if "condition_config" in values:
        _refuse_a_past_last_day(config, action.user_timezone)

    for key, value in (("recurrence", recurrence), ("condition_config", config)):
        if key in values or value != getattr(action, key):
            values[key] = value
    if action.condition_state is not None and _fact_space(config) != _fact_space(
        action.condition_config
    ):
        # Another fact space, or none: what was seen of the old one means nothing.
        values["condition_state"] = None
    plan = TriggerPlan(
        action_id=action.id,
        trigger_kind=kind,
        recurrence=RecurrenceSpec.model_validate(recurrence) if recurrence is not None else None,
        condition_config=config,
        timezone=action.user_timezone,
    )
    return _TriggerEdit(values=values, plan=plan, rearm=rearm)


#: What a routine's clock reads: an update touching any of them re-arms it.
_CLOCK_FIELDS: frozenset[str] = frozenset({"trigger_kind", "recurrence", "condition_config"})


def _serialised(data: ScheduledActionUpdate, values: dict[str, Any]) -> dict[str, Any]:
    """The update's values in the columns' own types, as NEW objects (JSONB rule)."""
    values = dict(values)
    if "trigger_kind" in values:
        values["trigger_kind"] = values["trigger_kind"].value
    if data.recurrence is not None:
        # Re-serialised through the model: canonical (dates as strings).
        values["recurrence"] = data.recurrence.model_dump(mode="json")
    if "condition_config" in values:
        values["condition_config"] = (
            data.condition_config.stored() if data.condition_config is not None else None
        )
    return values


def _resulting_clock(
    action: ScheduledAction, values: Mapping[str, Any]
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """The mode, schedule and condition the row will have.

    Switching mode drops what the OTHER mode stored — never what the payload
    sent, so a payload carrying both clocks still reaches the refusal.

    Returns:
        ``(trigger_kind, recurrence, condition_config)`` after the update.
    """
    kind = str(values.get("trigger_kind", action.trigger_kind))
    recurrence = values.get("recurrence", action.recurrence)
    config = values.get("condition_config", action.condition_config)
    if kind == TriggerKind.CONDITION.value and "recurrence" not in values:
        recurrence = None
    if kind == TriggerKind.TIME.value and "condition_config" not in values:
        config = None
    return kind, recurrence, config


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

        Enforces per-user limit, computes next_trigger_at from the routine's
        clock: its schedule, or its first check (ADR-322). The id is minted
        here because a condition routine's checks are phased by it.

        Raises:
            ValidationError: If user has reached the maximum limit, or a watch
                is set to end on a day already over.
        """
        # Enforce per-user limit
        count = await self.repository.count_for_user(user_id)
        if count >= SCHEDULED_ACTIONS_MAX_PER_USER:
            raise ValidationError(
                f"Maximum of {SCHEDULED_ACTIONS_MAX_PER_USER} scheduled actions per user"
            )

        condition_config = data.condition_config.stored() if data.condition_config else None
        _refuse_a_past_last_day(condition_config, user_timezone)
        action_id = uuid4()
        # The first armed instant, from the plan the executor re-arms with.
        next_trigger_at = TriggerPlan(
            action_id=action_id,
            trigger_kind=data.trigger_kind.value,
            recurrence=data.recurrence,
            condition_config=condition_config,
            timezone=user_timezone,
        ).first(now_utc())

        action = await self.repository.create(
            {
                "id": action_id,
                "user_id": user_id,
                "title": data.title,
                "action_prompt": data.action_prompt,
                # A NEW dict, never a mutation: JSONB skips an in-place UPDATE.
                "recurrence": (
                    data.recurrence.model_dump(mode="json") if data.recurrence else None
                ),
                "user_timezone": user_timezone,
                # N-07: kind/condition/approval — schema-validated coherence.
                "trigger_kind": data.trigger_kind.value,
                "condition_config": condition_config,
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
            trigger_kind=data.trigger_kind.value,
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

        Re-arms the routine when anything its clock reads changes — its
        schedule, its mode, or its condition (ADR-322).

        Raises:
            ResourceNotFoundError: If action not found or wrong owner.
            ValidationError: If the resulting routine would not have exactly
                one clock, or a watch's new last day is already over.
        """
        action = await self.get_with_ownership_check(action_id, user_id)

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return action

        edit = _trigger_edit(action, data, update_data)
        action = await self.repository.update(action, edit.values)

        if edit.rearm:
            next_trigger_at = edit.plan.first(now_utc())
            revived: dict[str, Any] = {"next_trigger_at": next_trigger_at}
            # Giving a CLOSED routine a future again puts it back to work
            # (ADR-281, lot 5). The executor closed it because its series had
            # nothing left; extend the series — or a watch's last day — and
            # that reason is gone, so the same authority reopens it. Without
            # this, someone pushing their watch's end date back got a
            # recomputed trigger on a row still disabled — an edit that
            # silently never runs.
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
            updated_fields=list(edit.values.keys()),
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
            update_data["next_trigger_at"] = TriggerPlan.of(action).first(now_utc())
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
        (e.g. 19:30) but recalculate the UTC trigger with the new timezone —
        and a watch's last day is read in the new zone too (ADR-322).

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
        # The spec is a LOCAL wall clock: moving zone keeps "08:00 where I
        # live" and only changes the instant it lands on.
        recalculated: dict[UUID, datetime | None] = {
            action.id: TriggerPlan.of(action, timezone=new_timezone).first(reference)
            for action in actions
        }

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
