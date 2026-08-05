"""Habits router — consultation, correction, deletion, blocking (ADR-214).

The control surface ships BEFORE any proactive consumption: everything the
detector learns is visible here, explained (thresholds published — ADR-184),
and reversible (pause / block / delete / delete-all).

References:
    - Pattern: domains/interests/router.py (settings + rows + feedback)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import ResourceNotFoundError
from src.core.session_dependencies import get_current_active_session
from src.core.time_utils import resolve_user_timezone
from src.domains.habits.candidates import (
    list_recurrence_candidates,
    observed_days_for_signature,
)
from src.domains.habits.models import HabitKind, ProfileVerdict, UserHabitProfile
from src.domains.habits.rhythm import RhythmProfile
from src.domains.habits.schemas import (
    HabitExplanationResponse,
    HabitResponse,
    HabitsCandidateSchema,
    HabitsDeleteAllResponse,
    HabitsOverviewResponse,
    HabitsProfileClassSchema,
    HabitsProfileSchema,
    HabitsRecomputeResponse,
    HabitsSettingsUpdate,
    HabitStatusUpdate,
    HabitWindowSchema,
)
from src.domains.habits.service import HabitsService
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/habits", tags=["Habits"])


def _profile_to_schema(profile: UserHabitProfile | None) -> HabitsProfileSchema:
    """Stored profile row → API schema (pre-first-run shape when None)."""
    required = {
        "weekday": settings.habits_min_neff_weekday,
        "weekend": settings.habits_min_neff_weekend,
    }
    if profile is None:
        return HabitsProfileSchema(
            computed_at=None,
            weekday=HabitsProfileClassSchema(
                verdict=ProfileVerdict.INSUFFICIENT,
                windows=[],
                n_eff=0.0,
                required_n_eff=required["weekday"],
            ),
            weekend=HabitsProfileClassSchema(
                verdict=ProfileVerdict.INSUFFICIENT,
                windows=[],
                n_eff=0.0,
                required_n_eff=required["weekend"],
            ),
            active_days_fraction=0.0,
            sparse=False,
        )
    parsed = RhythmProfile.from_payload(profile.payload)

    def _class(name: str) -> HabitsProfileClassSchema:
        rhythm = getattr(parsed, name)
        return HabitsProfileClassSchema(
            verdict=ProfileVerdict(rhythm.verdict),
            windows=[
                HabitWindowSchema(start_hour=w.start_hour, end_hour=w.end_hour, presence=w.presence)
                for w in rhythm.windows
            ],
            n_eff=rhythm.n_eff,
            required_n_eff=required[name],
            bin_presence=list(rhythm.bin_presence),
        )

    return HabitsProfileSchema(
        computed_at=profile.computed_at,
        weekday=_class("weekday"),
        weekend=_class("weekend"),
        active_days_fraction=parsed.active_days_fraction,
        sparse=parsed.sparse,
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
    # Every existing row (any status) is excluded from candidates: a BLOCKED
    # tombstone must never resurface as "under observation".
    candidates, candidates_more = await list_recurrence_candidates(
        current_user.id,
        local_today=datetime.now(resolve_user_timezone(current_user)).date(),
        exclude_keys={h.key for h in habits},
        settings=settings,
        limit=settings.habits_candidates_display_max,
    )
    return HabitsOverviewResponse(
        habits_enabled=current_user.habits_enabled,
        profile=_profile_to_schema(profile),
        habits=[HabitResponse.model_validate(h) for h in habits],
        candidates=[
            HabitsCandidateSchema(
                key=c.key, observed_days=c.observed_days, required_days=c.required_days
            )
            for c in candidates
        ],
        candidates_more=candidates_more,
    )


@router.post(
    "/recompute",
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
    service = HabitsService(db)
    outcome = await service.recompute_user_profile(current_user, force=True)
    await db.commit()
    profile = await service.repository.get_profile(current_user.id)
    logger.info(
        "habits_manual_recompute",
        user_id=str(current_user.id),
        outcome=outcome,
    )
    return HabitsRecomputeResponse(outcome=outcome, profile=_profile_to_schema(profile))


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
    current_user.habits_enabled = update.habits_enabled
    db.add(current_user)
    await db.commit()
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
    service = HabitsService(db)
    habit = await service.repository.get_owned(habit_id, current_user.id)
    if habit is None:
        raise ResourceNotFoundError("habit", str(habit_id))
    observed: list[str] = []
    if habit.kind == HabitKind.RECURRING_REQUEST.value:
        # Honest provenance: the ledger's real occurrence dates — the exact
        # basis of the lock (window habits carry the heatmap instead).
        observed = await observed_days_for_signature(current_user.id, habit.key)
    return HabitExplanationResponse(**service.build_explanation(habit), observed_days=observed)


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
    service = HabitsService(db)
    habit = await service.repository.get_owned(habit_id, current_user.id)
    if habit is None:
        raise ResourceNotFoundError("habit", str(habit_id))
    await service.repository.set_status(habit, update.status)
    await db.commit()
    await db.refresh(habit)
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
    service = HabitsService(db)
    habit = await service.repository.get_owned(habit_id, current_user.id)
    if habit is None:
        raise ResourceNotFoundError("habit", str(habit_id))
    await service.repository.delete_habit(habit)
    await db.commit()
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
    service = HabitsService(db)
    deleted = await service.repository.delete_all(current_user.id)
    await service.repository.delete_profile(current_user.id)
    # The rollup is learning material retained beyond message deletion —
    # "forget everything" must remove it too, or a recompute would resurrect
    # the profile instantly from data the user just asked to forget.
    await service.repository.delete_activity_rollup(current_user.id)
    await db.commit()
    logger.info("habits_deleted_all", user_id=str(current_user.id), deleted=deleted)
    return HabitsDeleteAllResponse(deleted_habits=deleted, profile_deleted=True)
