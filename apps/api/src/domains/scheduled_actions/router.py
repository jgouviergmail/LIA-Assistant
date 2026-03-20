"""
Scheduled Actions router with FastAPI endpoints.

Provides CRUD operations, toggle enable/disable, and immediate test execution.
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.scheduled_actions.models import (
    ScheduledAction as ScheduledActionModel,
)
from src.domains.scheduled_actions.models import (
    ScheduledActionStatus,
)
from src.domains.scheduled_actions.schemas import (
    ScheduledActionCreate,
    ScheduledActionListResponse,
    ScheduledActionResponse,
    ScheduledActionUpdate,
)
from src.domains.scheduled_actions.service import ScheduledActionService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/scheduled-actions", tags=["Scheduled Actions"])


def _action_to_response(action: ScheduledActionModel) -> ScheduledActionResponse:
    """Convert ScheduledAction model to response schema."""
    return ScheduledActionResponse.model_validate(action)


# =============================================================================
# List
# =============================================================================


@router.get(
    "",
    response_model=ScheduledActionListResponse,
    summary="List scheduled actions",
    description="Get all scheduled actions for the current user.",
)
async def list_scheduled_actions(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ScheduledActionListResponse:
    """List all scheduled actions for the current user."""
    service = ScheduledActionService(db)
    actions = await service.list_for_user(user.id)

    logger.info(
        "scheduled_actions_listed",
        user_id=str(user.id),
        total=len(actions),
    )

    return ScheduledActionListResponse(
        scheduled_actions=[_action_to_response(a) for a in actions],
        total=len(actions),
    )


# =============================================================================
# Create
# =============================================================================


@router.post(
    "",
    response_model=ScheduledActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create scheduled action",
    description="Create a new scheduled action for the current user.",
)
async def create_scheduled_action(
    data: ScheduledActionCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ScheduledActionResponse:
    """Create a new scheduled action."""
    service = ScheduledActionService(db)
    action = await service.create(
        user_id=user.id,
        data=data,
        user_timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
    )
    await db.commit()
    await db.refresh(action)

    logger.info(
        "scheduled_action_created",
        user_id=str(user.id),
        action_id=str(action.id),
        title=data.title,
    )

    return _action_to_response(action)


# =============================================================================
# Update
# =============================================================================


@router.patch(
    "/{action_id}",
    response_model=ScheduledActionResponse,
    summary="Update scheduled action",
    description="Update an existing scheduled action.",
)
async def update_scheduled_action(
    action_id: UUID,
    data: ScheduledActionUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ScheduledActionResponse:
    """Update an existing scheduled action."""
    service = ScheduledActionService(db)
    action = await service.update(action_id, user.id, data)
    await db.commit()
    await db.refresh(action)

    logger.info(
        "scheduled_action_updated",
        user_id=str(user.id),
        action_id=str(action_id),
    )

    return _action_to_response(action)


# =============================================================================
# Delete
# =============================================================================


@router.delete(
    "/{action_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete scheduled action",
    description="Delete a scheduled action.",
)
async def delete_scheduled_action(
    action_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a scheduled action."""
    service = ScheduledActionService(db)
    await service.delete(action_id, user.id)
    await db.commit()

    logger.info(
        "scheduled_action_deleted",
        user_id=str(user.id),
        action_id=str(action_id),
    )


# =============================================================================
# Toggle
# =============================================================================


@router.patch(
    "/{action_id}/toggle",
    response_model=ScheduledActionResponse,
    summary="Toggle scheduled action",
    description="Toggle enable/disable for a scheduled action.",
)
async def toggle_scheduled_action(
    action_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ScheduledActionResponse:
    """Toggle enable/disable for a scheduled action."""
    service = ScheduledActionService(db)
    action = await service.toggle(action_id, user.id)
    await db.commit()
    await db.refresh(action)

    logger.info(
        "scheduled_action_toggled",
        user_id=str(user.id),
        action_id=str(action_id),
        is_enabled=action.is_enabled,
    )

    return _action_to_response(action)


# =============================================================================
# Execute (test now)
# =============================================================================


@router.post(
    "/{action_id}/execute",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute scheduled action now",
    description="Trigger immediate execution of a scheduled action (fire-and-forget).",
)
async def execute_scheduled_action(
    action_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Trigger immediate execution of a scheduled action.

    The execution runs asynchronously (fire-and-forget).
    The result will appear in the user's conversation and as a notification.
    """
    service = ScheduledActionService(db)
    action = await service.get_with_ownership_check(action_id, user.id)

    # Guard: reject if already executing (scheduler or another manual trigger)
    if action.status == ScheduledActionStatus.EXECUTING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Action is already executing",
        )

    # Reserve status='executing' BEFORE fire-and-forget to prevent scheduler
    # from picking up the same action concurrently (it queries WHERE status='active').
    # If the background task crashes, recover_stale_executing resets it.
    action.status = ScheduledActionStatus.EXECUTING.value
    await db.commit()

    # Fire-and-forget execution via background task
    # Import here to avoid circular imports
    from src.infrastructure.scheduler.scheduled_action_executor import (
        execute_single_action,
    )

    asyncio.create_task(
        execute_single_action(action_id=action.id, user_id=user.id),
        name=f"scheduled_action_execute_{action.id}",
    )

    logger.info(
        "scheduled_action_manual_execute",
        user_id=str(user.id),
        action_id=str(action_id),
    )

    return {"status": "executing"}
