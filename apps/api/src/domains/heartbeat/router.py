"""
Heartbeat Autonome router — proactive notification settings and history.

Endpoints:
- GET /heartbeat/settings: Get heartbeat settings + available sources
- PATCH /heartbeat/settings: Update heartbeat settings
- GET /heartbeat/history: Get notification history (paginated)
- PATCH /heartbeat/notifications/{id}/feedback: Submit notification feedback
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import (
    raise_internal_error,
    raise_notification_not_found,
    raise_unprocessable_entity,
)
from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_active_session
from src.domains.heartbeat.repository import HeartbeatNotificationRepository
from src.domains.heartbeat.schemas import (
    HeartbeatFeedbackRequest,
    HeartbeatHistoryResponse,
    HeartbeatNotificationResponse,
    HeartbeatSettingsResponse,
    HeartbeatSettingsUpdate,
)
from src.domains.heartbeat.source_availability import compute_available_sources
from src.domains.heartbeat.source_policy import (
    HEARTBEAT_SOURCE_DEPENDENCIES,
    HEARTBEAT_SOURCE_ORDER,
    disabled_sources_for,
    sanitize_disabled_sources,
)
from src.domains.moments.preferences import (
    MOMENT_KIND_ORDER,
    disabled_kinds_for,
    sanitize_disabled_kinds,
    unmet_kind_dependencies,
)
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/heartbeat",
    tags=["Heartbeat"],
    # The deployment ceiling decides whether this router is mounted at all.
    # The operator's switch guards the ACTS — the three sweeps read it at
    # call time — never this router: settings, history, offers and feedback
    # are the record the person keeps reading and changing whatever the
    # switch says (ADR-280 amendment, 2026-09-11; measured on docker dev, the
    # router still answered 403 with the switch off).
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------


def _settings_response(user: User, available_sources: list[str]) -> HeartbeatSettingsResponse:
    """Assemble the settings payload — the ONE place that shape is decided.

    Both routes returned a byte-identical literal, so every field added since
    had to be written twice; a third vocabulary (the moment kinds) would have
    made that three chances for the read and the write to disagree about the
    same panel.

    Args:
        user: The account row, after any update was applied.
        available_sources: Connector categories this account actually has.

    Returns:
        The payload, carrying what is enforced so whoever produces a value can
        read the bound (ADR-184).
    """
    return HeartbeatSettingsResponse(
        heartbeat_enabled=user.heartbeat_enabled,
        heartbeat_min_per_day=user.heartbeat_min_per_day,
        heartbeat_max_per_day=user.heartbeat_max_per_day,
        heartbeat_push_enabled=user.heartbeat_push_enabled,
        heartbeat_notify_start_hour=user.heartbeat_notify_start_hour,
        heartbeat_notify_end_hour=user.heartbeat_notify_end_hour,
        available_sources=available_sources,
        disabled_sources=sorted(disabled_sources_for(user)),
        all_sources=list(HEARTBEAT_SOURCE_ORDER),
        source_dependencies={k: list(v) for k, v in HEARTBEAT_SOURCE_DEPENDENCIES.items()},
        moment_kinds_disabled=sorted(disabled_kinds_for(user)),
        all_moment_kinds=list(MOMENT_KIND_ORDER),
        moment_kind_dependencies={
            kind: list(requires)
            for kind, requires in unmet_kind_dependencies(
                available=frozenset(available_sources)
            ).items()
        },
    )


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
    available_sources = await compute_available_sources(user, db)

    return _settings_response(user, available_sources)


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
            raise_unprocessable_entity(
                APIMessages.heartbeat_min_max_invalid(normalize_language(user.language))
            )

        # Refusals are validated BEFORE anything is written: an unknown key
        # silently dropped would be a preference the reader believes they set.
        # Canonical (sorted, de-duplicated) so two equivalent requests leave
        # one row state, and a NEW list — never a mutation of the stored one
        # (JSONB in-place changes are skipped by SQLAlchemy).
        if update_data.get("heartbeat_disabled_sources") is not None:
            try:
                update_data["heartbeat_disabled_sources"] = sanitize_disabled_sources(
                    update_data["heartbeat_disabled_sources"]
                )
            except ValueError as exc:
                raise_unprocessable_entity(str(exc))

        # Same doctrine, second vocabulary: a NEW list, canonical, and unknown
        # kinds DROPPED rather than refused — a renamed kind must not block a
        # save, nor stay stored where no switch could ever lift it again.
        if update_data.get("moment_kinds_disabled") is not None:
            update_data["moment_kinds_disabled"] = sanitize_disabled_kinds(
                update_data["moment_kinds_disabled"]
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

        available_sources = await compute_available_sources(user, db)

        return _settings_response(user, available_sources)

    except HTTPException:
        # Let API errors (e.g. the 422 min>max guard) reach the client as-is
        # instead of degrading them to a generic 500 (contract fix, ADR-124).
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            "heartbeat_settings_update_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise_internal_error("Failed to update heartbeat settings")


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


@router.get(
    "/offers",
    response_model=HeartbeatHistoryResponse,
    summary="Open missed-routine offers (proposals inbox)",
    description=(
        "Undecided habit offers (Lot 5-C2): notifications carrying a "
        "habit_offer_id and no feedback yet, inside the recency window. "
        "Deciding one rides PATCH /notifications/{id}/feedback (ADR-214)."
    ),
)
async def get_open_offers(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HeartbeatHistoryResponse:
    """List the user's open missed-routine offers, newest first."""
    since = datetime.now(UTC) - timedelta(days=settings.heartbeat_offers_window_days)
    repo = HeartbeatNotificationRepository(db)
    notifications, total = await repo.get_open_offers(
        user_id=user.id, since=since, limit=limit, offset=offset
    )
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
        raise_notification_not_found(notification_id)

    # Hide the buttons on the archived card across reloads and devices, exactly
    # as the interest route does — otherwise the same notification can be rated
    # again on every page load.
    from src.domains.conversations.repository import ConversationRepository

    messages_updated = await ConversationRepository(db).mark_proactive_feedback_submitted(
        user_id=user.id,
        target_id=notification_id,
        feedback_value=data.feedback,
    )

    # ADR-214 — close the habit feedback loop: a verdict on a notification
    # that carried a missed-routine offer is a verdict on the habit itself.
    row = await repo.get_by_id(notification_id)
    if row is not None and row.habit_offer_id is not None:
        from src.domains.habits.repository import HabitsRepository

        await HabitsRepository(db).record_feedback(
            row.habit_offer_id, user.id, positive=(data.feedback == "thumbs_up")
        )

    # ADR-214 amendment (2026-09-03): a thumb is an explicit human act — a
    # presence hour for the rhythm detector (the notification itself never is).
    from src.domains.habits.presence import record_presence

    await record_presence(db, user, kind="feedback")

    await db.commit()

    logger.info(
        "heartbeat_feedback_submitted",
        user_id=str(user.id),
        notification_id=str(notification_id),
        feedback=data.feedback,
        messages_updated=messages_updated,
    )

    return {"message": "Feedback submitted successfully"}
