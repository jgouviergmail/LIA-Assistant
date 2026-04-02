"""
FastAPI router for the Psyche domain.

Provides REST endpoints for psyche state, expression profile, settings,
reset, and history. All endpoints require authentication.

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.psyche.engine import PsycheEngine
from src.domains.psyche.schemas import (
    PsycheExpressionResponse,
    PsycheHistoryEntry,
    PsycheResetRequest,
    PsycheResetResponse,
    PsycheSettingsResponse,
    PsycheSettingsUpdate,
    PsycheStateResponse,
    PsycheSummaryResponse,
)
from src.domains.psyche.service import PsycheService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/psyche", tags=["Psyche"])


# =============================================================================
# State
# =============================================================================


@router.get("/state", response_model=PsycheStateResponse)
async def get_psyche_state(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PsycheStateResponse:
    """Get current psyche state for the authenticated user.

    Returns the full dynamic state including mood, emotions, relationship,
    traits, self-efficacy, and computed mood label/color.
    """
    service = PsycheService(db)
    state = await service.get_or_create_state(current_user.id)
    await db.commit()

    # Compute mood label and color
    profile = PsycheEngine.compile_expression_profile(
        mood_p=state.mood_pleasure,
        mood_a=state.mood_arousal,
        mood_d=state.mood_dominance,
        emotions=state.active_emotions or [],
        stage=state.relationship_stage,
        warmth=state.relationship_warmth_active,
        drive_curiosity=state.drive_curiosity,
        drive_engagement=state.drive_engagement,
    )

    response = PsycheStateResponse.model_validate(state)
    response.mood_label = profile.mood_label
    response.mood_color = PsycheEngine.mood_to_color(profile.mood_label)
    return response


# =============================================================================
# Summary (LLM-generated)
# =============================================================================


@router.get("/summary", response_model=PsycheSummaryResponse)
async def get_psyche_summary(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PsycheSummaryResponse:
    """Generate a natural language summary of the current psyche state.

    Calls a lightweight LLM (psyche_summary type) to produce 2-3 sentences
    describing the mood, dominant emotion, and relationship stage in the
    user's language. Requires authentication. May take 2-5 seconds due to
    LLM invocation; falls back to a template summary on failure.
    """
    service = PsycheService(db)
    summary_text = await service.generate_summary(
        user_id=current_user.id,
        user_language=current_user.language or "fr",
    )
    await db.commit()
    return PsycheSummaryResponse(summary=summary_text)


# =============================================================================
# Expression Profile
# =============================================================================


@router.get("/expression", response_model=PsycheExpressionResponse)
async def get_expression_profile(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PsycheExpressionResponse:
    """Get current compiled expression profile.

    Returns the computed behavioral directives (mood label, intensity,
    top emotions, warmth, drives) used for prompt injection.
    """
    service = PsycheService(db)
    state = await service.get_or_create_state(current_user.id)
    await db.commit()

    profile = PsycheEngine.compile_expression_profile(
        mood_p=state.mood_pleasure,
        mood_a=state.mood_arousal,
        mood_d=state.mood_dominance,
        emotions=state.active_emotions or [],
        stage=state.relationship_stage,
        warmth=state.relationship_warmth_active,
        drive_curiosity=state.drive_curiosity,
        drive_engagement=state.drive_engagement,
    )

    return PsycheExpressionResponse(
        mood_label=profile.mood_label,
        mood_intensity=profile.mood_intensity,
        active_emotions=[
            {"name": name, "intensity": intensity} for name, intensity in profile.active_emotions
        ],
        relationship_stage=profile.relationship_stage,
        warmth_label=profile.warmth_label,
        drive_curiosity=profile.drive_curiosity,
        drive_engagement=profile.drive_engagement,
    )


# =============================================================================
# Settings
# =============================================================================


@router.get("/settings", response_model=PsycheSettingsResponse)
async def get_psyche_settings(
    current_user: User = Depends(get_current_active_session),
) -> PsycheSettingsResponse:
    """Get user psyche preferences."""
    return PsycheSettingsResponse(
        psyche_enabled=current_user.psyche_enabled,
        psyche_display_avatar=current_user.psyche_display_avatar,
        psyche_sensitivity=current_user.psyche_sensitivity,
        psyche_stability=current_user.psyche_stability,
    )


@router.patch("/settings", response_model=PsycheSettingsResponse)
async def update_psyche_settings(
    update: PsycheSettingsUpdate,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PsycheSettingsResponse:
    """Update user psyche preferences."""
    update_data = update.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(current_user, field_name, value)

    await db.flush()
    await db.commit()

    logger.info(
        "psyche_settings_updated",
        user_id=str(current_user.id),
        updated_fields=list(update_data.keys()),
    )

    return PsycheSettingsResponse(
        psyche_enabled=current_user.psyche_enabled,
        psyche_display_avatar=current_user.psyche_display_avatar,
        psyche_sensitivity=current_user.psyche_sensitivity,
        psyche_stability=current_user.psyche_stability,
    )


# =============================================================================
# Reset
# =============================================================================


@router.post("/reset", response_model=PsycheResetResponse)
async def reset_psyche_state(
    request: PsycheResetRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PsycheResetResponse:
    """Reset psyche state at specified level.

    - soft: Reset mood and emotions only. Relationship and traits preserved.
    - full: Reset everything except Big Five traits (which are per-personality).
    - purge: Delete entire psyche state (GDPR).
    """
    service = PsycheService(db)
    await service.reset_state(current_user.id, request.level)
    await db.commit()

    logger.info(
        "psyche_state_reset_by_user",
        user_id=str(current_user.id),
        level=request.level,
    )

    return PsycheResetResponse(status="reset", level=request.level)


# =============================================================================
# History
# =============================================================================


@router.get("/history", response_model=list[PsycheHistoryEntry])
async def get_psyche_history(
    limit: int = Query(100, ge=1, le=500, description="Max entries to return."),
    hours: int | None = Query(
        None, ge=1, le=2160, description="Filter to last N hours (max 90 days)."
    ),
    snapshot_type: str | None = Query(None, description="Filter by snapshot type."),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[PsycheHistoryEntry]:
    """Get psyche evolution history for graphical dashboard.

    Returns historical snapshots ordered by creation date (newest first).
    Use `hours` to filter by time range (24=last day, 168=last week, etc.).
    """
    service = PsycheService(db)
    entries = await service.get_history(
        user_id=current_user.id,
        limit=limit,
        snapshot_type=snapshot_type,
        hours=hours,
    )

    return [PsycheHistoryEntry.model_validate(entry) for entry in entries]
