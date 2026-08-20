"""Activity timeline router (Lot 1-A1).

One read-only endpoint. Included in ``api/v1/routes.py`` behind the
``activity_timeline_enabled`` flag. The service binds to the
AUTHENTICATED user — no user id ever comes from the request.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.core.config import settings
from src.core.session_dependencies import get_current_active_session
from src.domains.activity.schemas import ActivityTimelineResponse
from src.domains.activity.service import ActivityService
from src.domains.users.models import User

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get(
    "/timeline",
    response_model=ActivityTimelineResponse,
    summary="Paginated timeline of what LIA did proactively for the user",
)
async def get_activity_timeline(
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
    limit: int | None = Query(
        default=None, ge=1, le=100, description="Page size (default from settings)"
    ),
    current_user: User = Depends(get_current_active_session),
) -> ActivityTimelineResponse:
    """Merged, newest-first page of proactive events with exact totals.

    Pure local SQL aggregation (no LLM, no connector): fast enough to be
    uncached. Partial source failures are reported in ``failed_kinds``.
    """
    return await ActivityService(current_user.id).build_timeline(
        offset=offset,
        limit=limit if limit is not None else settings.activity_timeline_page_size,
    )
