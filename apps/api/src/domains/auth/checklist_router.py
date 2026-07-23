"""Starter checklist card state endpoint (UXR Lot 6, A10).

Own module (SLOC ratchet: ``auth/router.py`` is frozen at its audited size)
mounted beside the auth router. Item states are DETECTED live client-side —
only the dismissal/celebration timestamps are persisted, as a full NEW-dict
JSONB replacement (new-dict rule).
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.schemas import (
    OnboardingChecklistRequest,
    OnboardingChecklistResponse,
)
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.patch(
    "/me/onboarding-checklist",
    response_model=OnboardingChecklistResponse,
    summary="Update the starter checklist card state",
    description=(
        "Stamps dismissed_at / celebrated_at (ISO-UTC, server-side) on true "
        "transitions. The card never renders again once either is set "
        "(UXR Lot 6, A10)."
    ),
)
async def update_onboarding_checklist(
    data: OnboardingChecklistRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> OnboardingChecklistResponse:
    """Persist the checklist card's dismissal/celebration state.

    Args:
        data: True flags for the timestamps to stamp now (UTC).
        user: Current authenticated user.
        db: Database session.

    Returns:
        The stored state after the update.
    """
    now_iso = datetime.now(UTC).isoformat()
    current: dict[str, Any] = (
        user.onboarding_checklist if isinstance(user.onboarding_checklist, dict) else {}
    )
    # True TRANSITIONS only: an already-stamped timestamp is history — a
    # replayed PATCH (retry, second tab) must never overwrite it.
    updates: dict[str, Any] = {}
    if data.dismissed and "dismissed_at" not in current:
        updates["dismissed_at"] = now_iso
    if data.celebrated and "celebrated_at" not in current:
        updates["celebrated_at"] = now_iso
    if updates:
        user.onboarding_checklist = {**current, **updates}
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(
            "onboarding_checklist_updated",
            user_id=str(user.id),
            stamped=sorted(updates),
        )

    return OnboardingChecklistResponse(
        onboarding_checklist=(
            user.onboarding_checklist if isinstance(user.onboarding_checklist, dict) else {}
        ),
    )
