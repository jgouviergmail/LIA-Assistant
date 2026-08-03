"""Interest notification history — the audit surface of the interests panel.

Its own module rather than another endpoint in ``router.py``: that file sits
under the 600 logical-SLOC ceiling and adding this route pushed it to 618. The
doctrine is to extract a cohesive module, never to bump the cap — and "what was
actually sent" is a different concern from "which interests exist and how they
are tuned", which is what the main router is about.

Mounted alongside the main interests router under the same prefix, so the path
the client calls is unchanged.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.interests.repository import InterestNotificationRepository
from src.domains.interests.schemas import (
    InterestNotificationHistoryItem,
    InterestNotificationHistoryResponse,
)
from src.domains.users.models import User

router = APIRouter(prefix="/interests", tags=["Interests"])


@router.get(
    "/notifications/history",
    response_model=InterestNotificationHistoryResponse,
    summary="Get interest notification history",
    description=(
        "Paginated history of interest notifications, newest first. Mirrors "
        "the heartbeat history: the panel that tunes what may interrupt the "
        "reader must also show what actually did."
    ),
)
async def get_interest_notification_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> InterestNotificationHistoryResponse:
    """One page of this user's interest notifications.

    Args:
        limit: Page size.
        offset: Page offset.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The page and the EXACT total behind it (ADR-185) — the panel states
        the cap rather than applying it in silence.
    """
    notifications, total = await InterestNotificationRepository(db).get_history(
        user_id=user.id, limit=limit, offset=offset
    )
    return InterestNotificationHistoryResponse(
        notifications=[
            InterestNotificationHistoryItem(
                id=notification.id,
                created_at=notification.created_at,
                content=notification.content,
                source=notification.source,
                # The interest is nullable (it may have been deleted since) and
                # so is the relationship: an absent topic is a fact about the
                # account, never a reason to drop the notification from the
                # history the reader is auditing.
                topic=getattr(notification.interest, "topic", None),
                user_feedback=notification.user_feedback,
            )
            for notification in notifications
        ],
        total=total,
    )
