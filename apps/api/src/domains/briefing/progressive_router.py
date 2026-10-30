"""Progressive dashboard routes (spec 2026-10-21 §5.8, D2) — additive; the old routes stay.

- ``GET  /briefing/cards/initial``           : what shows at once, the slow sections pending, the act
- ``GET  /briefing/sections/{name}?act=``    : exactly one section of the act
- ``POST /briefing/text``                    : the greeting and synthesis of the act's settled sections
- ``POST /briefing/sections/{name}/refresh`` : one section, forced

Every answer is private and never stored by a cache (``PrivateApplicationInputRoute``
sets ``no-store``). Authentication reads the
account on a session of its own, closed before the route runs: a section read
waits on a slow provider, and the request session would sit ``idle in
transaction`` for all of it (ADR-304).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, Query

from src.core.exceptions import ResourceConflictError, raise_invalid_input
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.briefing.constants import SECTION_NAMES
from src.domains.briefing.progressive import (
    BriefingContextChanged,
    act_section,
    act_text,
    initial_cards,
    refresh_section,
)
from src.domains.briefing.router import ERROR_CODE_SECTION_HIDDEN
from src.domains.briefing.schemas import (
    BriefingInitialResponse,
    BriefingTextRequest,
    BriefingTextResponse,
    CardSection,
)
from src.domains.briefing.service import BriefingService
from src.domains.users.models import User

router = APIRouter(prefix="/briefing", tags=["briefing"], route_class=PrivateApplicationInputRoute)

#: The act expired or its context changed: the client starts a new initial load.
ERROR_CODE_CONTEXT_CHANGED = "briefing_context_changed"
#: The path names no section of the dashboard.
ERROR_CODE_UNKNOWN_SECTION = "unknown_section"

#: An act token is a short signed string; anything longer is not one.
_ACT_MAX_LENGTH = 512


def _context_changed() -> NoReturn:
    raise ResourceConflictError("briefing_act", detail={"code": ERROR_CODE_CONTEXT_CHANGED})


def _visible_section(service: BriefingService, name: str) -> str:
    """The section a path names, refused when unknown or hidden (hidden is « never read »)."""
    if name not in SECTION_NAMES:
        raise_invalid_input(f"{ERROR_CODE_UNKNOWN_SECTION}: {name}", section=name)
    if name in service.hidden_sections:
        raise_invalid_input(f"{ERROR_CODE_SECTION_HIDDEN}: {name}", sections=[name])
    return name


@router.get(
    "/cards/initial",
    response_model=BriefingInitialResponse,
    summary="The dashboard sections that need no slow source; the others pending",
)
async def get_initial_cards(
    current_user: User = Depends(get_current_active_session_for_stream),
) -> BriefingInitialResponse:
    """Hidden, local and cached sections at once; a cache miss is ``pending``, never fetched here."""
    return await initial_cards(BriefingService(current_user), now=datetime.now(UTC))


@router.get(
    "/sections/{name}",
    response_model=CardSection,
    summary="Exactly one section of a dashboard act",
)
async def get_act_section(
    name: str,
    act: str = Query(..., min_length=1, max_length=_ACT_MAX_LENGTH),
    current_user: User = Depends(get_current_active_session_for_stream),
) -> CardSection:
    """One section, read once across the workers; filed under the act."""
    service = BriefingService(current_user)
    try:
        return await act_section(
            service, _visible_section(service, name), act=act, now=datetime.now(UTC)
        )
    except BriefingContextChanged:
        _context_changed()


@router.post(
    "/text",
    response_model=BriefingTextResponse,
    summary="The greeting and synthesis of an act's settled sections",
)
async def post_act_text(
    payload: BriefingTextRequest,
    current_user: User = Depends(get_current_active_session_for_stream),
) -> BriefingTextResponse:
    """Reads caches only; generated once per distinct input; ``uncertain`` is never relaunched."""
    try:
        return await act_text(
            BriefingService(current_user),
            act=payload.act,
            force=payload.force,
            now=datetime.now(UTC),
        )
    except BriefingContextChanged:
        _context_changed()


@router.post(
    "/sections/{name}/refresh",
    response_model=CardSection,
    summary="Re-read one section now, without regenerating the text",
)
async def post_section_refresh(
    name: str,
    current_user: User = Depends(get_current_active_session_for_stream),
) -> CardSection:
    """The section bypasses its cache; the text follows at its next request."""
    service = BriefingService(current_user)
    return await refresh_section(service, _visible_section(service, name))


__all__ = ["ERROR_CODE_CONTEXT_CHANGED", "ERROR_CODE_UNKNOWN_SECTION", "router"]
