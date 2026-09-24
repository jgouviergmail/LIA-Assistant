"""The live mode routes (ADR-299), under the LIVE capability.

No execution route: a delegated request goes through ``POST /chat/stream``
from the browser, with the person's own cookie. What is here is the connector,
the preferences, the session record (a credential per connection) and its trace.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    LIVE_DELEGATION_TOOL_NAME,
    LIVE_DURATION_UNLIMITED,
    LIVE_IDLE_TIMEOUT_SECONDS_MAX,
    LIVE_IDLE_TIMEOUT_SECONDS_MIN,
    LIVE_SESSION_BUDGET_EUR_MAX,
    LIVE_SESSION_MAX_MINUTES_MAX,
    LIVE_SESSION_MAX_MINUTES_MIN,
    LIVE_TURN_TEXT_MAX_CHARS,
)
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.core.user_display import resolve_user_display_name
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.live.connector_service import LiveConnectorService
from src.domains.live.direct_mandate import browser_lines
from src.domains.live.mandate import bridge_lines, tone_lines
from src.domains.live.preferences import LivePreferences
from src.domains.live.schemas import (
    LiveConfigResponse,
    LiveConnectorActivateRequest,
    LiveConnectorResponse,
    LiveConnectorSettings,
    LiveConnectorsResponse,
    LiveCredentialResponse,
    LiveDiscoverRequest,
    LiveDurationBounds,
    LiveEndRequest,
    LiveEndResponse,
    LiveExtendResponse,
    LiveModelsResponse,
    LiveOfferRequest,
    LiveOfferResponse,
    LiveSessionStartRequest,
    LiveSessionStartResponse,
    LiveToolCallRequest,
    LiveToolCallResponse,
    LiveTurnRequest,
    LiveTurnResponse,
    LiveVoiceSampleRequest,
    LiveVoiceSampleResponse,
    LiveVoicesResponse,
)
from src.domains.live.service import LiveService
from src.domains.users.models import User

router = APIRouter(
    prefix="/live",
    tags=["Live"],
    # Administrable capability: a switched-off feature refuses at the door.
    dependencies=capability_dependencies(PlatformCapability.LIVE),
)


def _language(user: User) -> str:
    return user.language or settings.default_language


@router.get("/config", response_model=LiveConfigResponse, summary="The bounds the client honours")
async def live_config(_: User = Depends(get_current_active_session)) -> LiveConfigResponse:
    """Every bound the browser applies, published because it is enforced (ADR-184)."""
    return LiveConfigResponse(
        session_max_minutes=settings.live_session_max_minutes,
        session_max_bounds=LiveDurationBounds(
            min=LIVE_SESSION_MAX_MINUTES_MIN, max=LIVE_SESSION_MAX_MINUTES_MAX
        ),
        idle_timeout_bounds=LiveDurationBounds(
            min=LIVE_IDLE_TIMEOUT_SECONDS_MIN, max=LIVE_IDLE_TIMEOUT_SECONDS_MAX
        ),
        session_budget_eur_max=LIVE_SESSION_BUDGET_EUR_MAX,
        unlimited_value=LIVE_DURATION_UNLIMITED,
        extension_minutes=settings.live_extension_minutes,
        extension_prompt_seconds=settings.live_extension_prompt_seconds,
        connect_window_seconds=settings.live_connect_window_seconds,
        idle_timeout_seconds=settings.live_idle_timeout_seconds,
        hidden_grace_seconds=settings.live_hidden_grace_seconds,
        delegation_timeout_seconds=settings.live_delegation_timeout_seconds,
        delegation_result_max_tokens=settings.live_delegation_result_max_tokens,
        delegation_tool_name=LIVE_DELEGATION_TOOL_NAME,
        turn_text_max_chars=LIVE_TURN_TEXT_MAX_CHARS,
        delegation_lines=bridge_lines(),
        direct_lines=browser_lines(),
        tone_lines=tone_lines(),
    )


# -- connector -------------------------------------------------------------------


@router.post(
    "/models/discover",
    response_model=LiveModelsResponse,
    summary="The live models a key discovers, before the connector exists",
)
async def discover_models(
    payload: LiveDiscoverRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveModelsResponse:
    """The connector form's first step: the key is verified by this very listing."""
    return await LiveConnectorService(db).discover_models(
        payload.api_key, provider_id=payload.provider, language=_language(user)
    )


@router.get(
    "/voices/published",
    response_model=LiveVoicesResponse,
    summary="A provider's published voices, before the connector exists",
)
async def published_voices(
    provider: str = Query("gemini", max_length=32),
    _: User = Depends(get_current_active_session),
) -> LiveVoicesResponse:
    """The connector form's second step, with the list's provenance."""
    return await LiveConnectorService.published_voices(provider)


@router.post(
    "/voices/sample",
    response_model=LiveVoiceSampleResponse,
    summary="Hear a voice before choosing it, on the person's key",
)
async def sample_voice(
    payload: LiveVoiceSampleRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveVoiceSampleResponse:
    """One sentence in the voice; the form's key before the connector exists, the stored one after."""
    return await LiveConnectorService(db).sample_voice(user, payload, language=_language(user))


@router.post(
    "/connector/activate",
    response_model=LiveConnectorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Verify the key, check the model and voice, store the connector",
)
async def activate_connector(
    payload: LiveConnectorActivateRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveConnectorResponse:
    """One door for the activation: key, voice on the list, model the provider opens."""
    return await LiveConnectorService(db).activate_connector(
        user, payload, language=_language(user)
    )


@router.get(
    "/connectors",
    response_model=LiveConnectorsResponse,
    summary="Every active live connector, and the one the sessions open on",
)
async def get_connectors(
    user: User = Depends(get_current_active_session), db: AsyncSession = Depends(get_db)
) -> LiveConnectorsResponse:
    """An empty list when the account has none: « is there one? » is a question
    the header asks on every load, and an absence is an answer, not a failure —
    starting a session without one is what answers 409 ``connector_missing``.
    """
    return await LiveConnectorService(db).connectors_response(user)


@router.put(
    "/connectors/{provider}",
    response_model=LiveConnectorResponse,
    summary="Change model, voice, thinking level — and make this provider the one sessions open on",
)
async def put_connector(
    provider: str,
    payload: LiveConnectorSettings,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveConnectorResponse:
    """The provider judges the model again; the voice is checked against its list."""
    return await LiveConnectorService(db).update_connector_settings(
        user, provider, payload, language=_language(user)
    )


@router.get(
    "/models", response_model=LiveModelsResponse, summary="Live-capable models of the person's key"
)
async def list_models(
    user: User = Depends(get_current_active_session), db: AsyncSession = Depends(get_db)
) -> LiveModelsResponse:
    """What the person's key discovers today."""
    return await LiveConnectorService(db).list_models(user, language=_language(user))


@router.get("/voices", response_model=LiveVoicesResponse, summary="Voices, with their provenance")
async def list_voices(
    provider: str | None = Query(None, max_length=32),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveVoicesResponse:
    """The voices of one of the person's providers (the chosen one by default)."""
    return await LiveConnectorService(db).list_voices(
        user, provider_id=provider, language=_language(user)
    )


# -- preferences -----------------------------------------------------------------


@router.get(
    "/preferences",
    response_model=LivePreferences,
    summary="The person's live conversation reflexes",
)
async def get_preferences(user: User = Depends(get_current_active_session)) -> LivePreferences:
    """Tolerant of what the column holds."""
    return LiveConnectorService.preferences(user)


@router.put(
    "/preferences", response_model=LivePreferences, summary="Replace the live conversation reflexes"
)
async def put_preferences(
    payload: LivePreferences,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LivePreferences:
    """Strict on the way in (a word off the ladder is 422)."""
    return await LiveConnectorService(db).update_preferences(user, payload)


# -- session ---------------------------------------------------------------------


@router.post(
    "/sessions",
    response_model=LiveSessionStartResponse,
    summary="Open a session: its first credential",
)
async def start_session(
    payload: LiveSessionStartRequest | None = None,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveSessionStartResponse:
    """Refuses in order: no connector, rate limit, a session already open, a full instance.

    The body names the MODE (ADR-300 wave 4); an absent body is a delegated session.
    """
    return await LiveService(db).start(
        user,
        language=_language(user),
        timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        display_name=resolve_user_display_name(user.full_name, user.email),
        mode=(payload or LiveSessionStartRequest()).mode,
        audio_transport=(payload or LiveSessionStartRequest()).audio_transport,
    )


@router.post(
    "/sessions/{session_id}/tools",
    response_model=LiveToolCallResponse,
    summary="Run one read-only lookup the voice asked for on a DIRECT live session",
)
async def run_session_tool(
    session_id: str,
    payload: LiveToolCallRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveToolCallResponse:
    """The phone's tool door on the person's own session (ADR-300 wave 4).

    Every refusal is a sentence the voice says; a lookup that ran is filed on
    the ``live_session`` surface under the session's run id.
    """
    return await LiveService(db).run_tool(
        user,
        session_id,
        payload,
        language=_language(user),
        timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        display_name=resolve_user_display_name(user.full_name, user.email),
    )


@router.post(
    "/sessions/{session_id}/credential",
    response_model=LiveCredentialResponse,
    summary="A fresh credential to reconnect the same session",
)
async def renew_credential(
    session_id: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveCredentialResponse:
    """One credential opens one connection (measured); a reconnection mints again."""
    return await LiveService(db).renew_credential(user, session_id, language=_language(user))


@router.post(
    "/sessions/{session_id}/offer",
    response_model=LiveOfferResponse,
    summary="Exchange the browser's SDP offer on the person's key (offer connections)",
)
async def exchange_offer(
    session_id: str,
    payload: LiveOfferRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveOfferResponse:
    """One credential, one exchange: the nonce is consumed before the provider is asked."""
    return await LiveService(db).exchange_offer(user, session_id, payload, language=_language(user))


@router.post(
    "/sessions/{session_id}/extend",
    response_model=LiveExtendResponse,
    summary="Prolong the session by the published extension, on the person's explicit word",
)
async def extend_session(
    session_id: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveExtendResponse:
    """The cap moves from its current value; a fresh credential rides back for the reconnection."""
    return await LiveService(db).extend(user, session_id, language=_language(user))


@router.post(
    "/sessions/{session_id}/turns",
    response_model=LiveTurnResponse,
    summary="Archive a voice-only exchange",
)
async def archive_turn(
    session_id: str,
    payload: LiveTurnRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveTurnResponse:
    """Both roles, visible, at once — the thread reports in real time."""
    return await LiveService(db).archive_turn(user, session_id, payload, language=_language(user))


@router.post(
    "/sessions/{session_id}/end",
    response_model=LiveEndResponse,
    summary="Close the session's books",
)
async def end_session(
    session_id: str,
    payload: LiveEndRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LiveEndResponse:
    """The card, LIA's cost, the decision row, the freed slot, the learning pass."""
    return await LiveService(db).end(user, session_id, payload, language=_language(user))


__all__ = ["router"]
