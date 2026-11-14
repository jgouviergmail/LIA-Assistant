"""What the person sees of how LIA writes for them, and forgetting it (ADR-383).

The switch is an account preference of the reviewed vocabulary the assistant's own
preference tool writes too (``AssistantPreferencePatch``): one door, two hands. These
routes read what was learned, switch the style and forget it — for the authenticated
account only.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.preference_commands import (
    AssistantPreferencePatch,
    update_assistant_preferences,
)
from src.domains.auth.schemas import WritingStylePreferenceRequest
from src.domains.users.models import User
from src.domains.writing_style.schemas import WritingStyleResponse
from src.domains.writing_style.service import WritingStyleService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/writing-style", tags=["Writing style"])


@router.get(
    "",
    response_model=WritingStyleResponse,
    summary="Read the writing style LIA learned",
    description="How the person writes, as learned from their sent mail, with their switch.",
)
async def read_writing_style(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> WritingStyleResponse:
    """What the settings show.

    Args:
        user: The authenticated account.
        db: Session.

    Returns:
        The switch, and what was learned with when, if anything.
    """
    return await WritingStyleService(db).read(user.id)


@router.patch(
    "",
    response_model=WritingStyleResponse,
    summary="Switch the writing style on or off",
    description=(
        "Off, nothing is read, learned or used; what was already learned is kept until "
        "the person forgets it (ADR-280)."
    ),
)
async def switch_writing_style(
    data: WritingStylePreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> WritingStyleResponse:
    """Save the switch as the shared preference, and answer the state it leaves.

    Args:
        data: The requested state.
        user: The authenticated account.
        db: Session.

    Returns:
        The switch saved, and what was learned with when, if anything.
    """
    await update_assistant_preferences(
        db, user.id, AssistantPreferencePatch(writing_style_enabled=data.writing_style_enabled)
    )
    logger.info("writing_style_switched", user_id=str(user.id), enabled=data.writing_style_enabled)
    return await WritingStyleService(db).read(user.id)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget the writing style LIA learned",
    description=(
        "Removes what was learned. With the switch on, the next e-mail LIA writes for the "
        "person learns it again from their sent mail."
    ),
)
async def forget_writing_style(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Forget what was learned (idempotent: nothing learned answers the same).

    Args:
        user: The authenticated account.
        db: Session.
    """
    await WritingStyleService(db).forget(user.id)
