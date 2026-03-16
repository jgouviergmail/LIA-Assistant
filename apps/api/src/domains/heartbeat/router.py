"""
Heartbeat Autonome router — proactive notification settings and history.

Endpoints:
- GET /heartbeat/settings: Get heartbeat settings + available sources
- PATCH /heartbeat/settings: Update heartbeat settings
- GET /heartbeat/history: Get notification history (paginated)
- PATCH /heartbeat/notifications/{id}/feedback: Submit notification feedback
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES, ConnectorType
from src.domains.connectors.repository import ConnectorRepository
from src.domains.heartbeat.repository import HeartbeatNotificationRepository
from src.domains.heartbeat.schemas import (
    HeartbeatFeedbackRequest,
    HeartbeatHistoryResponse,
    HeartbeatNotificationResponse,
    HeartbeatSettingsResponse,
    HeartbeatSettingsUpdate,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/heartbeat", tags=["Heartbeat"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _compute_available_sources(
    user: User,
    db: AsyncSession,
) -> list[str]:
    """Compute which data sources are connected for this user.

    Returns a list of source names for the UI to display availability indicators.
    """
    sources: list[str] = []

    repo = ConnectorRepository(db)

    # Calendar: any active calendar connector (Google Calendar, Apple Calendar, future Microsoft...)
    for ct in CONNECTOR_FUNCTIONAL_CATEGORIES.get("calendar", frozenset()):
        connector = await repo.get_by_user_and_type(user.id, ct)
        if connector and connector.status.value == "active":
            sources.append("calendar")
            break

    # Tasks: any active tasks connector (Google Tasks, Microsoft To Do)
    for ct in CONNECTOR_FUNCTIONAL_CATEGORIES.get("tasks", frozenset()):
        connector = await repo.get_by_user_and_type(user.id, ct)
        if connector and connector.status.value == "active":
            sources.append("tasks")
            break

    # Emails: any active email connector (Gmail, Apple Email, Microsoft Outlook)
    for ct in CONNECTOR_FUNCTIONAL_CATEGORIES.get("email", frozenset()):
        connector = await repo.get_by_user_and_type(user.id, ct)
        if connector and connector.status.value == "active":
            sources.append("emails")
            break

    # Weather: OpenWeatherMap connector active + home location configured
    weather_connector = await repo.get_by_user_and_type(user.id, ConnectorType.OPENWEATHERMAP)
    if (
        weather_connector
        and weather_connector.status.value == "active"
        and user.home_location_encrypted
    ):
        sources.append("weather")

    # Interests: at least one active interest
    if user.interests_enabled:
        from src.domains.interests.repository import InterestRepository

        interest_repo = InterestRepository(db)
        active_interests = await interest_repo.get_active_for_user(user.id)
        if active_interests:
            sources.append("interests")

    # Memories: memory_enabled
    if user.memory_enabled:
        sources.append("memories")

    return sources


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/settings",
    response_model=HeartbeatSettingsResponse,
    summary="Get heartbeat settings",
    description="Get current user's heartbeat notification settings and available sources.",
)
async def get_heartbeat_settings(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HeartbeatSettingsResponse:
    """Get user's heartbeat notification settings."""
    available_sources = await _compute_available_sources(user, db)

    return HeartbeatSettingsResponse(
        heartbeat_enabled=user.heartbeat_enabled,
        heartbeat_min_per_day=user.heartbeat_min_per_day,
        heartbeat_max_per_day=user.heartbeat_max_per_day,
        heartbeat_push_enabled=user.heartbeat_push_enabled,
        heartbeat_notify_start_hour=user.heartbeat_notify_start_hour,
        heartbeat_notify_end_hour=user.heartbeat_notify_end_hour,
        available_sources=available_sources,
    )


@router.patch(
    "/settings",
    response_model=HeartbeatSettingsResponse,
    summary="Update heartbeat settings",
    description="Update user's heartbeat notification settings (partial update).",
)
async def update_heartbeat_settings(
    data: HeartbeatSettingsUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HeartbeatSettingsResponse:
    """Update user's heartbeat notification settings."""
    try:
        update_data = data.model_dump(exclude_unset=True)

        # Validate min <= max consistency
        min_val = update_data.get("heartbeat_min_per_day", user.heartbeat_min_per_day)
        max_val = update_data.get("heartbeat_max_per_day", user.heartbeat_max_per_day)
        if min_val > max_val:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="heartbeat_min_per_day must be <= heartbeat_max_per_day",
            )

        if update_data:
            for field_name, value in update_data.items():
                setattr(user, field_name, value)

            await db.commit()
            await db.refresh(user)

            logger.info(
                "heartbeat_settings_updated",
                user_id=str(user.id),
                updated_fields=list(update_data.keys()),
            )

        available_sources = await _compute_available_sources(user, db)

        return HeartbeatSettingsResponse(
            heartbeat_enabled=user.heartbeat_enabled,
            heartbeat_min_per_day=user.heartbeat_min_per_day,
            heartbeat_max_per_day=user.heartbeat_max_per_day,
            heartbeat_push_enabled=user.heartbeat_push_enabled,
            heartbeat_notify_start_hour=user.heartbeat_notify_start_hour,
            heartbeat_notify_end_hour=user.heartbeat_notify_end_hour,
            available_sources=available_sources,
        )

    except Exception as e:
        await db.rollback()
        logger.error(
            "heartbeat_settings_update_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update heartbeat settings",
        ) from e


# ---------------------------------------------------------------------------
# History endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/history",
    response_model=HeartbeatHistoryResponse,
    summary="Get notification history",
    description="Get paginated history of heartbeat notifications.",
)
async def get_heartbeat_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HeartbeatHistoryResponse:
    """Get paginated heartbeat notification history."""
    repo = HeartbeatNotificationRepository(db)
    notifications, total = await repo.get_history(user_id=user.id, limit=limit, offset=offset)

    return HeartbeatHistoryResponse(
        notifications=[HeartbeatNotificationResponse.from_model(n) for n in notifications],
        total=total,
    )


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------


@router.patch(
    "/notifications/{notification_id}/feedback",
    status_code=status.HTTP_200_OK,
    summary="Submit notification feedback",
    description="Submit feedback (thumbs_up/thumbs_down) on a heartbeat notification.",
)
async def submit_heartbeat_feedback(
    notification_id: UUID,
    data: HeartbeatFeedbackRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Submit feedback on a heartbeat notification."""
    repo = HeartbeatNotificationRepository(db)
    updated = await repo.update_feedback(
        notification_id=notification_id,
        user_id=user.id,
        feedback=data.feedback,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    await db.commit()

    logger.info(
        "heartbeat_feedback_submitted",
        user_id=str(user.id),
        notification_id=str(notification_id),
        feedback=data.feedback,
    )

    return {"message": "Feedback submitted successfully"}
