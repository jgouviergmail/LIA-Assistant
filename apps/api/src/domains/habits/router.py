"""Habits router — consultation, correction, deletion, blocking (ADR-214).

The control surface ships BEFORE any proactive consumption: everything the
detector learns is visible here, explained (thresholds published — ADR-184),
and reversible (pause / block / delete / delete-all).

References:
    - Pattern: domains/interests/router.py (settings + rows + feedback)
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import HABITS_PRESENCE_RATE_LIMIT_PER_MINUTE
from src.core.dependencies import get_db
from src.core.exceptions import raise_rate_limit_exceeded
from src.core.session_dependencies import get_current_active_session
from src.core.time_utils import resolve_user_timezone
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.habits.candidates import (
    list_recurrence_candidates,
)
from src.domains.habits.forgetting import forget_habit_data
from src.domains.habits.management_commands import change_managed_habit
from src.domains.habits.management_explanation import read_managed_habit_explanation
from src.domains.habits.overview_projection import (
    build_overview_response,
)
from src.domains.habits.preference_commands import update_habit_settings
from src.domains.habits.presence import record_presence
from src.domains.habits.recompute_commands import recompute_managed_habits
from src.domains.habits.schemas import (
    HabitExplanationResponse,
    HabitResponse,
    HabitsDeleteAllResponse,
    HabitsOverviewResponse,
    HabitsRecomputeResponse,
    HabitsSettingsUpdate,
    HabitStatusUpdate,
)
from src.domains.habits.service import HabitsService
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

logger = get_logger(__name__)

router = APIRouter(
    prefix="/habits",
    tags=["Habits"],
    # The deployment ceiling already decides whether this router is mounted
    # at all. The operator's switch guards the two routes that ACT
    # (``/recompute``, ``/presence``) and the acts themselves
    # (``habits/capability.py``); the record — reading, correcting, deleting
    # what was learned — stays open (ADR-280 amendment, 2026-09-11).
)


@router.get(
    "",
    response_model=HabitsOverviewResponse,
    summary="Learned habits overview",
    description="User preference, rhythm profile and discrete habits.",
)
async def get_habits_overview(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HabitsOverviewResponse:
    """The settings-surface payload for the current user."""
    service = HabitsService(db)
    profile, habits = await service.get_overview(current_user.id)
    local_today = datetime.now(resolve_user_timezone(current_user)).date()
    streak = await service.get_streaks(current_user.id, today=local_today)
    # Every existing row (any status) is excluded from candidates: a BLOCKED
    # tombstone must never resurface as "under observation".
    candidates, candidates_more = await list_recurrence_candidates(
        current_user.id,
        local_today=local_today,
        exclude_keys={h.key for h in habits},
        settings=settings,
        limit=settings.habits_candidates_display_max,
    )
    return build_overview_response(
        current_user,
        profile,
        streak,
        [HabitResponse.model_validate(h) for h in habits],
        candidates,
        candidates_more,
    )


@router.post(
    "/recompute",
    dependencies=capability_dependencies(PlatformCapability.HABITS),
    response_model=HabitsRecomputeResponse,
    summary="Recompute the rhythm profile now",
    description="Runs the nightly unit of work immediately. The aggregation is "
    "retroactive by construction (sliding window over existing messages), so a "
    "fresh activation — or a reset — sees its profile without waiting a night.",
)
async def recompute_habits_now(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HabitsRecomputeResponse:
    """Manual trigger of the per-user recompute (same code path as the job,
    delta-skip bypassed: an explicit user action must never silently no-op)."""
    result = await recompute_managed_habits(db, current_user.id)
    logger.info(
        "habits_manual_recompute",
        user_id=str(current_user.id),
        outcome=result.outcome,
    )
    return result


@router.post(
    "/presence",
    dependencies=capability_dependencies(PlatformCapability.HABITS),
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Reading presence ping",
    description="The client says the user has LIA in front of them (on mount, on "
    "visibilitychange→visible, on focus — never from a background poll). Banks at "
    "most one activity hour per local hour; a sent notification never counts.",
)
async def record_reading_presence(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Bank a reading-presence hour for the current user (idempotent)."""
    # Per-user ceiling on a cheap, client-throttled call — Redis down means
    # the limiter fails open (the endpoint is idempotent by construction).
    allowed = True
    with suppress(Exception):
        limiter = await get_rate_limiter()
        allowed = await limiter.acquire(
            key=f"user:{current_user.id}:presence",
            max_calls=HABITS_PRESENCE_RATE_LIMIT_PER_MINUTE,
            window_seconds=60,
        )
    if not allowed:
        raise_rate_limit_exceeded(
            limit=HABITS_PRESENCE_RATE_LIMIT_PER_MINUTE, window_seconds=60, retry_after=60
        )
    outcome = await record_presence(db, current_user, kind="visibility")
    await db.commit()
    logger.debug("habits_presence_ping", user_id=str(current_user.id), outcome=outcome)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/settings",
    response_model=HabitsSettingsUpdate,
    summary="Update habits preference",
)
async def update_habits_settings(
    update: HabitsSettingsUpdate,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HabitsSettingsUpdate:
    """Toggle habit learning for the current user."""
    await update_habit_settings(db, current_user.id, update)
    logger.info(
        "habits_preference_updated",
        user_id=str(current_user.id),
        habits_enabled=update.habits_enabled,
    )
    return update


@router.get(
    "/{habit_id}/explanation",
    response_model=HabitExplanationResponse,
    summary="Why LIA claims this habit",
    description="Detector inputs and the exact thresholds applied — never a score.",
)
async def get_habit_explanation(
    habit_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HabitExplanationResponse:
    """Published explanation for one habit (interests doctrine)."""
    return await read_managed_habit_explanation(db, current_user.id, habit_id)


@router.post(
    "/{habit_id}/status",
    response_model=HabitResponse,
    summary="Pause, resume or block a habit",
)
async def set_habit_status(
    habit_id: UUID,
    update: HabitStatusUpdate,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HabitResponse:
    """Set the user-controlled status; 'blocked' prevents relearning."""
    habit = await change_managed_habit(db, current_user.id, habit_id, update)
    assert habit is not None
    logger.info(
        "habit_status_updated",
        user_id=str(current_user.id),
        habit_id=str(habit_id),
        status=update.status,
    )
    return HabitResponse.model_validate(habit)


@router.delete(
    "/{habit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one habit",
)
async def delete_habit(
    habit_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete one learned habit (it may be relearned unless blocked first)."""
    await change_managed_habit(db, current_user.id, habit_id, None)
    logger.info("habit_deleted", user_id=str(current_user.id), habit_id=str(habit_id))


@router.delete(
    "",
    response_model=HabitsDeleteAllResponse,
    summary="Forget every learned habit",
    description="Deletes all habit rows AND the rhythm profile.",
)
async def delete_all_habits(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HabitsDeleteAllResponse:
    """Full reset of everything the habits subsystem learned."""
    result = await forget_habit_data(db, current_user.id)
    logger.info(
        "habits_deleted_all",
        user_id=str(current_user.id),
        deleted=result.deleted_habits,
        advisory_cleanup_confirmed=result.advisory_cleanup_confirmed,
    )
    return result
