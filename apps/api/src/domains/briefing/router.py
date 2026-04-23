"""Briefing domain router — Today dashboard endpoints.

Two non-blocking GET endpoints + one refresh:

- GET  /briefing/cards     : 6-card bundle (no LLM, fast)
- GET  /briefing/synthesis : LLM greeting + synthesis (reads cards from cache)
- POST /briefing/refresh   : force-refresh selected sections, returns full payload

The frontend calls /cards and /synthesis in parallel — the dashboard grid
renders as soon as /cards returns, while the greeting + synthesis arrive a
moment later without blocking the page.

Note: the BriefingService does NOT receive the request-scoped DB session.
Each fetcher acquires its own session via ``get_db_context()`` to safely
run in parallel (SQLAlchemy AsyncSession is not concurrent-safe).
"""

from fastapi import APIRouter, Depends

from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.briefing.schemas import (
    BriefingResponse,
    CardsResponse,
    RefreshRequest,
    SynthesisResponse,
)
from src.domains.briefing.service import BriefingService

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get(
    "/cards",
    response_model=CardsResponse,
    summary="Get the 6-card bundle for the Today dashboard (no LLM, fast)",
)
async def get_briefing_cards(
    current_user: User = Depends(get_current_active_session),
) -> CardsResponse:
    """Returns the 6 dashboard cards. Uses Redis cache when fresh.

    No LLM involved — this is the fast endpoint. Frontend calls this in
    parallel with /briefing/synthesis to render the page progressively.
    """
    cards = await BriefingService(current_user).build_cards()
    return CardsResponse(cards=cards)


@router.get(
    "/synthesis",
    response_model=SynthesisResponse,
    summary="Get the LLM-generated greeting + synthesis (reads cards from cache)",
)
async def get_briefing_synthesis(
    current_user: User = Depends(get_current_active_session),
) -> SynthesisResponse:
    """Returns the LLM greeting + synthesis. Reads cards from Redis cache.

    Slow endpoint (~1-3 s LLM-bound). Frontend calls it in parallel with
    /briefing/cards so the page is not blocked by the LLM latency.
    Greeting always populated (fallback if LLM down).
    """
    return await BriefingService(current_user).build_text()


@router.post(
    "/refresh",
    response_model=BriefingResponse,
    summary="Force-refresh selected sections and regenerate greeting + synthesis",
)
async def refresh_today_briefing(
    payload: RefreshRequest,
    current_user: User = Depends(get_current_active_session),
) -> BriefingResponse:
    """Force-refresh of the selected sections (or 'all').

    Re-fetches the requested sections (bypassing cache) AND regenerates the
    greeting + synthesis. Returns the complete payload in one call so the
    frontend can swap everything at once after a user-triggered refresh.
    """
    return await BriefingService(current_user).build_today(force_refresh=set(payload.sections))
