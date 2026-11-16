"""The execution-mode preference: pipeline, react or auto (ADR-070, ADR-390).

Own module (SLOC ratchet: ``auth/router.py`` is frozen at its audited size) mounted
beside the auth router. Both doors answer what « auto » does on THIS instance
(``auto_resolution``): a choice the instance cannot honour is said where it is
offered, never left to look like a decision.
"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_EXECUTION_MODE, ExecutionMode
from src.core.dependencies import get_db
from src.core.execution_mode import is_execution_mode_choice
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.preference_commands import (
    AssistantPreferencePatch,
    update_assistant_preferences,
)
from src.domains.auth.schemas import (
    ExecutionModePreferenceRequest,
    ExecutionModePreferenceResponse,
)
from src.domains.llm_config.execution_mode_readiness import auto_resolution
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _stored_choice(user: User) -> ExecutionMode:
    """The person's choice; a value no choice names reads as the default."""
    stored = user.execution_mode
    return stored if is_execution_mode_choice(stored) else DEFAULT_EXECUTION_MODE


@router.get(
    "/me/execution-mode-preference",
    response_model=ExecutionModePreferenceResponse,
    summary="Get execution mode preference",
    description="The person's execution mode, and what « auto » does on this instance.",
)
async def get_execution_mode_preference(
    user: User = Depends(get_current_active_session),
) -> ExecutionModePreferenceResponse:
    """Read the execution mode preference.

    Args:
        user: Current authenticated user.

    Returns:
        The choice, and what « auto » does here.
    """
    return ExecutionModePreferenceResponse(
        execution_mode=_stored_choice(user),
        auto_resolution=await auto_resolution(),
        message="",
    )


@router.patch(
    "/me/execution-mode-preference",
    response_model=ExecutionModePreferenceResponse,
    summary="Update execution mode preference",
    description="Choose pipeline (planner), react (ReAct loop) or auto (engine chosen per turn).",
)
async def update_execution_mode_preference(
    data: ExecutionModePreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ExecutionModePreferenceResponse:
    """Update the execution mode preference.

    This controls how actionable queries are processed:
    - pipeline: Planner generates a plan, tools execute directly (fast, economical)
    - react: ReAct agent reasons iteratively with tools (autonomous, adaptive)
    - auto: the router picks one of the two per turn (ADR-390)

    Args:
        data: Execution mode preference: pipeline, react or auto.
        user: Current authenticated user.
        db: Database session.

    Returns:
        The stored choice, and what « auto » does here.
    """
    user = await update_assistant_preferences(
        db, user.id, AssistantPreferencePatch(execution_mode=data.execution_mode)
    )
    logger.info(
        "user_execution_mode_preference_updated",
        user_id=str(user.id),
        execution_mode=data.execution_mode,
    )
    return ExecutionModePreferenceResponse(
        execution_mode=_stored_choice(user),
        auto_resolution=await auto_resolution(),
        message=f"Execution mode switched to {data.execution_mode}",
    )
