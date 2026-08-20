"""Briefing domain router — Today dashboard endpoints.

Two non-blocking GET endpoints + one refresh:

- GET  /briefing/cards     : 9-card bundle (no LLM, fast)
- GET  /briefing/synthesis : LLM greeting + synthesis (reads cards from cache)
- POST /briefing/refresh   : force-refresh selected sections, returns full payload

The frontend calls /cards and /synthesis in parallel — the dashboard grid
renders as soon as /cards returns, while the greeting + synthesis arrive a
moment later without blocking the page.

Note: the BriefingService does NOT receive the request-scoped DB session.
Each fetcher acquires its own session via ``get_db_context()`` to safely
run in parallel (SQLAlchemy AsyncSession is not concurrent-safe).
"""

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import raise_internal_error, raise_invalid_input
from src.core.session_dependencies import get_current_active_session
from src.domains.briefing.preferences import (
    BriefingPreferences,
    sanitize_briefing_preferences,
)
from src.domains.briefing.schemas import (
    BriefingResponse,
    CardsResponse,
    RefreshRequest,
    SynthesisResponse,
)
from src.domains.briefing.service import BriefingService
from src.domains.users.models import User
from src.domains.voice.text_readout import synthesize_user_text

router = APIRouter(prefix="/briefing", tags=["briefing"])

# Stable error code — the frontend refuses to offer refresh on hidden cards;
# this guards direct API calls (UXR Lot 5, B4).
ERROR_CODE_SECTION_HIDDEN = "section_hidden"


def _reject_hidden_sections(current_user: User, sections: list[str]) -> None:
    """400 when a refresh targets a user-hidden section (UXR B4, shared by
    /refresh and /refresh-cards). Hidden means "never fetched", by design."""
    hidden = set(sanitize_briefing_preferences(current_user.briefing_preferences).hidden)
    blocked = sorted(hidden & set(sections))
    if blocked:
        raise_invalid_input(
            f"{ERROR_CODE_SECTION_HIDDEN}: {', '.join(blocked)}",
            sections=blocked,
        )


@router.get(
    "/cards",
    response_model=CardsResponse,
    summary="Get the 9-card bundle for the Today dashboard (no LLM, fast)",
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
    "/refresh-cards",
    response_model=CardsResponse,
    summary="Force-refresh selected sections WITHOUT regenerating the LLM texts",
)
async def refresh_briefing_cards(
    payload: RefreshRequest,
    current_user: User = Depends(get_current_active_session),
) -> CardsResponse:
    """Cards-only force-refresh (D-04).

    The per-card retry button calls this: before D-04 it went through
    POST /refresh, so retrying ONE failed connector card silently paid two
    LLM calls (greeting + synthesis). Same hidden-section guard as /refresh.
    """
    _reject_hidden_sections(current_user, list(payload.sections))
    cards = await BriefingService(current_user).build_cards(force_refresh=set(payload.sections))
    return CardsResponse(cards=cards)


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
    Refreshing a user-hidden section is a 400 (stable code
    ``section_hidden``) — hidden means "never fetched", by design.
    """
    _reject_hidden_sections(current_user, list(payload.sections))
    return await BriefingService(current_user).build_today(force_refresh=set(payload.sections))


@router.get(
    "/preferences",
    response_model=BriefingPreferences,
    summary="Get the briefing grid preferences (visibility + order)",
)
async def get_briefing_preferences(
    current_user: User = Depends(get_current_active_session),
) -> BriefingPreferences:
    """Sanitized view of the stored preferences (UXR Lot 5, B4).

    NULL column → all sections visible in canonical order; unknown stored
    names are filtered and the order is completed canonically.
    """
    return sanitize_briefing_preferences(current_user.briefing_preferences)


@router.put(
    "/preferences",
    response_model=BriefingPreferences,
    summary="Replace the briefing grid preferences (visibility + order)",
)
async def put_briefing_preferences(
    payload: BriefingPreferences,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> BriefingPreferences:
    """Full replace of the grid preferences (UXR Lot 5, B4).

    Validation is strict (unknown/duplicate names → 422). The write is a
    plain NEW-dict assignment — the JSONB new-dict rule.
    """
    current_user.briefing_preferences = {
        "hidden": list(payload.hidden),
        "order": list(payload.order),
    }
    db.add(current_user)
    await db.commit()
    return sanitize_briefing_preferences(current_user.briefing_preferences)


class SynthesisAudioRequest(BaseModel):
    """The synthesis text the frontend is displaying, sent back for TTS."""

    text: str = Field(description="The rendered synthesis text to read aloud.")
    lia_gender: Literal["male", "female"] | None = Field(
        default=None,
        description="Avatar gender preference (drives TTS voice selection, as in chat).",
    )

    @field_validator("text")
    @classmethod
    def _bounded_non_blank(cls, value: str) -> str:
        """Reject blank input and enforce the settings-driven cost bound."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        if len(stripped) > settings.briefing_audio_max_chars:
            raise ValueError(
                f"text exceeds briefing_audio_max_chars ({settings.briefing_audio_max_chars})"
            )
        return stripped


@router.post(
    "/synthesis/audio",
    summary="Read the displayed briefing synthesis aloud (TTS, no LLM)",
)
async def synthesis_audio(
    payload: SynthesisAudioRequest,
    current_user: User = Depends(get_current_active_session),
) -> Response:
    """Synthesize the displayed synthesis and return the MP3 bytes.

    A2 (evolution program): reading is free of generation — the text is
    the one the user is looking at, bounded by settings, sanitized, and
    cost-tracked like every paid voice path (all owned by the voice
    domain's ``synthesize_user_text``). The audio is buffered (a briefing
    synthesis is a short paragraph) so failures surface as real HTTP
    errors instead of a broken stream.
    """
    try:
        audio = await synthesize_user_text(
            user_id=current_user.id,
            user_language=current_user.language or settings.default_language,
            text=payload.text,
            lia_gender=payload.lia_gender,
            max_sentences=settings.briefing_audio_max_sentences,
            run_prefix="briefing_audio",
        )
    except Exception as exc:  # noqa: BLE001 - mapped to the API error contract
        raise_internal_error(f"briefing_audio_tts_failed: {type(exc).__name__}")
    return Response(content=audio, media_type="audio/mpeg")
