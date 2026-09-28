"""The personal radio's routes (ADR-324) — exactly what the web client names (``lib/radio/api.ts``).

Every route sits under the capability guard (the routes ARE the listening and
its settings) and answers for the CALLER only: a session, a segment or a site of
another account reads as absent. None holds a request session: the account is
read on a session of its own (``get_current_active_session_for_stream``) and
every store opens its own short one, because a start reads the listener's day
and a site preview reaches a stranger's server — nothing may pin a pooled
connection while they wait (ADR-304). Refusals carry a stable code in
``detail.code`` the web app translates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from src.core.config import settings
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.radio.articles import radio_article
from src.domains.radio.budget import listener_budget
from src.domains.radio.constants import BUDGET_WINDOW_SECONDS
from src.domains.radio.errors import (
    START_REFUSALS,
    raise_article_not_found,
    raise_segment_not_found,
    raise_session_not_found,
    raise_source_not_found,
    refuse,
)
from src.domains.radio.listener_settings import (
    add_listener_source,
    forget_heard,
    listener_preferences,
    listener_sources,
    look_for_feed,
    radio_options,
    save_preferences,
    update_listener_source,
)
from src.domains.radio.preferences import RadioPreferences
from src.domains.radio.repository import remove_source
from src.domains.radio.schemas import (
    RadioArticleResponse,
    RadioBudgetResponse,
    RadioCustomSourceResponse,
    RadioOptionsResponse,
    RadioPlayheadRequest,
    RadioSessionResponse,
    RadioSourcePreviewResponse,
    RadioSourceRequest,
    RadioSourcesResponse,
    RadioSourceUpdateRequest,
    RadioStartRequest,
)
from src.domains.radio.setup_builder import RadioStartRefused
from src.domains.radio.wiring import radio_service
from src.domains.users.models import User
from src.infrastructure.observability.metrics_radio import radio_session_starts_total

router = APIRouter(
    prefix="/radio",
    tags=["Radio"],
    dependencies=capability_dependencies(PlatformCapability.RADIO),
)

# Read once at import, like every settings-driven module constant: looking for a
# site's feed costs up to ~15 bounded requests to a stranger's server.
rate_limit_source_lookup = create_user_rate_limiter(
    "radio_source_lookup",
    max_calls=settings.radio_source_preview_rate_limit_calls,
    window_seconds=settings.radio_source_preview_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)

#: A segment's audio is the listener's alone, and never kept (no replay).
_AUDIO_HEADERS = {"Cache-Control": "no-store"}
#: A start that took its place (``radio_session_starts_total``; a refusal counts its code).
STARTED: Final = "started"


@router.post(
    "/sessions",
    response_model=RadioSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a radio session",
    description=(
        "Opens the account's one session (a previous one stops at its next tick) and "
        "answers at once with the startup estimate. Refusals: `radio_instance_full`, "
        "`radio_no_voice`, `radio_voice_unavailable` in `detail.code`, and "
        "`radio_budget_reached` (429) with the bound (`max_eur`) and when it lifts "
        "(`lifts_at`) when the listener's radio spent its rolling day's budget."
    ),
)
async def start_session(
    request: RadioStartRequest,
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioSessionResponse:
    """Start the listener's session."""
    try:
        answer = await (await radio_service()).start(user.id, request)
    except RadioStartRefused as refused:
        code = START_REFUSALS[refused.reason]
        radio_session_starts_total.labels(outcome=code).inc()
        refuse(code, **refused.detail)
    radio_session_starts_total.labels(outcome=STARTED).inc()
    return answer


@router.post(
    "/sessions/{session_id}/playhead",
    response_model=RadioSessionResponse,
    summary="Report where the player is, and read the session",
)
async def report_playhead(
    session_id: UUID,
    request: RadioPlayheadRequest,
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioSessionResponse:
    """File the player's report; answer with the session's state."""
    answer = await (await radio_service()).report(user.id, session_id, request)
    if answer is None:
        raise_session_not_found(session_id)
    return answer


@router.post(
    "/sessions/{session_id}/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop a radio session",
)
async def stop_session(
    session_id: UUID,
    user: User = Depends(get_current_active_session_for_stream),
) -> None:
    """Stop the session (its loop reads it at its next tick)."""
    if not await (await radio_service()).stop(user.id, session_id):
        raise_session_not_found(session_id)


@router.get(
    "/sessions/{session_id}/segments/{seq}/audio",
    response_class=FileResponse,
    summary="A ready segment's audio",
)
async def segment_audio(
    session_id: UUID,
    seq: int,
    user: User = Depends(get_current_active_session_for_stream),
) -> FileResponse:
    """The segment's MP3, never cached."""
    path = await (await radio_service()).audio_path(user.id, session_id, seq)
    if path is None:
        raise_segment_not_found(session_id)
    return FileResponse(path, media_type="audio/mpeg", headers=_AUDIO_HEADERS)


@router.get(
    "/options",
    response_model=RadioOptionsResponse,
    summary="What the radio's settings may offer",
    description="Every list and bound a settings write accepts (ADR-184).",
)
async def get_options(
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioOptionsResponse:
    """The options for this listener (voices of their language)."""
    return await radio_options(user.language)


@router.get(
    "/budget",
    response_model=RadioBudgetResponse,
    summary="What the listener's radio spent over the rolling day",
    description=(
        "The bound (`limit_eur`, 0 = none), what the listener's radio — its sessions "
        "and article translations — spent over the last `window_hours` (`spent_eur`), "
        "and, while the bound is reached, when it lifts (`lifts_at`)."
    ),
)
async def get_budget(
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioBudgetResponse:
    """The listener's radio budget now (ADR-324 decision 37)."""
    budget = await listener_budget(user.id, now=datetime.now(UTC))
    return RadioBudgetResponse(
        limit_eur=budget.limit_eur,
        # The ledger keeps six decimals; a sum of floats would publish noise past them.
        spent_eur=round(budget.spent_eur, 6),
        window_hours=BUDGET_WINDOW_SECONDS // 3600,
        lifts_at=budget.lifts_at,
    )


@router.get(
    "/articles/{article_id}",
    response_model=RadioArticleResponse,
    summary="A story's article, in the listener's language",
    description=(
        "The article of a transcript source (`article_id`): its full text when the "
        "newsroom could read it, else the outlet's summary — translated into the "
        "listener's language when its feed speaks another, billed to them once per "
        "story and language (`cost_eur`). 404 for a story that is not theirs to read."
    ),
)
async def get_article(
    article_id: UUID,
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioArticleResponse:
    """A story's article for the radio page."""
    article = await radio_article(user.id, article_id, user.language)
    if article is None:
        raise_article_not_found(article_id)
    return article


@router.get("/preferences", response_model=RadioPreferences, summary="The listener's settings")
async def get_preferences(
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioPreferences:
    """The listener's settings (the defaults when they never saved any), every voice offered."""
    return await listener_preferences(user.id, user.language)


@router.put(
    "/preferences",
    response_model=RadioPreferences,
    summary="Replace the listener's settings",
    description=(
        "Refusals: `radio_timer_too_long` (with `max_minutes`), `radio_voice_unknown`, "
        "`radio_personality_unknown` in `detail.code`."
    ),
)
async def put_preferences(
    preferences: RadioPreferences,
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioPreferences:
    """Check and store the listener's settings."""
    return await save_preferences(user.id, user.language, preferences)


@router.get(
    "/sources",
    response_model=RadioSourcesResponse,
    summary="Every source of the listener's newsroom, and what it holds for them",
    description=(
        "The base sources (ticked or not) and the listener's own sites (running or paused), "
        "each with the stories it published within `window_hours` and how many of them the "
        "listener never heard; the totals count what the station can air."
    ),
)
async def get_sources(
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioSourcesResponse:
    """The listener's newsroom, counted (ADR-324 decision 38)."""
    return await listener_sources(user.id, now=datetime.now(UTC))


@router.patch(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rename or pause one of the listener's sites",
    description="404 when the site is not the caller's (a base source is unticked instead).",
)
async def patch_source(
    source_id: UUID,
    request: RadioSourceUpdateRequest,
    user: User = Depends(get_current_active_session_for_stream),
) -> None:
    """Rename or pause the site."""
    await update_listener_source(user.id, source_id, request)


@router.delete(
    "/heard",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget what the listener heard",
    description=(
        "Every story and every fact of their day may air again; a session already on air "
        "keeps its own memory until it ends."
    ),
)
async def delete_heard(
    user: User = Depends(get_current_active_session_for_stream),
) -> None:
    """Forget what the listener heard (ADR-324 decision 38)."""
    await forget_heard(user.id)


@router.post(
    "/sources/preview",
    response_model=RadioSourcePreviewResponse,
    summary="Look for a site's feed, before adding it",
    dependencies=[Depends(rate_limit_source_lookup)],
)
async def preview_source(
    request: RadioSourceRequest,
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioSourcePreviewResponse:
    """What looking for the site's feed found (an outcome, never an error)."""
    del user  # authenticated and rate-limited per account; the lookup is the same for all
    return RadioSourcePreviewResponse.of(await look_for_feed(request.address))


@router.post(
    "/sources",
    response_model=RadioCustomSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a site to the listener's newsroom",
    description=(
        "Looks for the feed again and stores what was found. Refusals: "
        "`radio_source_refused` (with `outcome`), `radio_source_limit` (with "
        "`max_sources`) in `detail.code`."
    ),
    dependencies=[Depends(rate_limit_source_lookup)],
)
async def post_source(
    request: RadioSourceRequest,
    user: User = Depends(get_current_active_session_for_stream),
) -> RadioCustomSourceResponse:
    """Add the site; adding it again returns it unchanged."""
    source = await add_listener_source(user.id, request.address)
    return RadioCustomSourceResponse(
        id=source.id,
        feed_url=source.feed_url,
        title=source.title,
        language=source.language,
        paused=source.paused,
        failing=source.failing,
    )


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a site (its stories go with it)",
)
async def delete_source(
    source_id: UUID,
    user: User = Depends(get_current_active_session_for_stream),
) -> None:
    """Remove the listener's site."""
    if not await remove_source(user.id, source_id):
        raise_source_not_found(source_id)


__all__ = ["router"]
