"""Open Loops router — minimal v1 surface (P5, ADR-139).

Two endpoints: list the user's loops (optional status filter) and close one.
The full management UI ships with the briefing section (program Lot 4);
until then this surface exists for API consumers and debugging.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_not_found_or_unauthorized
from src.core.session_dependencies import get_current_active_session
from src.domains.open_loops.models import OpenLoopStatus
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.open_loops.schemas import OpenLoopListResponse, OpenLoopResponse
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/open-loops", tags=["Open Loops"])


@router.get(
    "",
    response_model=OpenLoopListResponse,
    summary="List open loops",
    description="List the current user's tracked commitments, optionally filtered by status.",
)
async def list_open_loops(
    status: OpenLoopStatus | None = Query(
        default=None, description="Optional status filter (open | closed | expired)"
    ),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> OpenLoopListResponse:
    """List the current user's loops, newest first."""
    repo = OpenLoopRepository(db)
    loops = await repo.list_for_user(user.id, status=status.value if status else None)
    items = [OpenLoopResponse.model_validate(loop) for loop in loops]
    return OpenLoopListResponse(items=items, total=len(items))


@router.post(
    "/{loop_id}/close",
    response_model=OpenLoopResponse,
    summary="Close an open loop",
    description="Mark a tracked commitment as resolved.",
)
async def close_open_loop(
    loop_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> OpenLoopResponse:
    """Atomically close one of the current user's OPEN loops.

    404 for a missing, foreign, or already-closed loop (private resource →
    hide existence, same policy as the sibling domains).
    """
    repo = OpenLoopRepository(db)
    claimed = await repo.close_loop(loop_id, user.id, reason="api")
    if not claimed:
        raise_not_found_or_unauthorized("open_loop", loop_id)
    await db.commit()

    loop = await repo.get_by_id(loop_id)
    if loop is None:  # pragma: no cover — closed row cannot vanish mid-request
        raise_not_found_or_unauthorized("open_loop", loop_id)
    return OpenLoopResponse.model_validate(loop)
