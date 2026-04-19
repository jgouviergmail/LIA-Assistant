"""
Auth router with FastAPI endpoints for authentication.
"""

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import (
    raise_external_service_connection_error,
    raise_external_service_fetch_error,
    raise_invalid_input,
    raise_permission_denied,
)
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_active_session, get_current_session
from src.core.session_helpers import (
    clear_session_cookie,
    create_authenticated_session_with_cookie,
)
from src.domains.auth.dependencies import (
    rate_limit_login,
    rate_limit_password_reset,
    rate_limit_password_reset_request,
    rate_limit_register,
)
from src.domains.auth.models import User
from src.domains.auth.schemas import (
    AuthResponseBFF,
    DebugPanelPreferenceRequest,
    DebugPanelPreferenceResponse,
    DisplayModePreferenceRequest,
    DisplayModePreferenceResponse,
    ExecutionModePreferenceRequest,
    ExecutionModePreferenceResponse,
    LastLocationUpdateRequest,
    LastLocationUpdateResponse,
    LastLocationViewResponse,
    MemoryPreferenceRequest,
    MemoryPreferenceResponse,
    MessageResponse,
    OnboardingPreferenceRequest,
    OnboardingPreferenceResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    SubAgentsPreferenceRequest,
    SubAgentsPreferenceResponse,
    TokenRefreshRequest,
    TokensDisplayPreferenceRequest,
    TokensDisplayPreferenceResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    VoiceModePreferenceRequest,
    VoiceModePreferenceResponse,
    VoicePreferenceRequest,
    VoicePreferenceResponse,
    WeatherLocationPreferenceRequest,
    WeatherLocationPreferenceResponse,
)
from src.domains.auth.service import AuthService
from src.domains.auth.user_location_service import UserLocationService
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from src.infrastructure.observability.metrics import (
    auth_attempts_total,
    user_logins_total,
    user_registrations_total,
)
from src.infrastructure.observability.metrics_oauth import (
    oauth_callback_duration_seconds,
    oauth_callback_errors_total,
    oauth_callback_total,
    oauth_initiate_duration_seconds,
    oauth_initiate_total,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=AuthResponseBFF,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user (BFF Pattern)",
    description="Register a new user with email and password. Creates session and sets HTTP-only cookie. "
    "Sends verification email. BFF Pattern: No tokens exposed to frontend.",
)
async def register(
    data: UserRegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_register),
) -> AuthResponseBFF:
    """
    Register a new user with email and password using BFF Pattern.

    Flow:
    1. Validates email is not already registered
    2. Hashes password securely
    3. Creates user in database
    4. Sends verification email
    5. Creates session in Redis
    6. Sets HTTP-only session cookie
    7. Returns user info (no tokens)

    Security (BFF Pattern):
    - No JWT tokens in response body
    - Session stored server-side in Redis
    - HTTP-only cookie prevents XSS
    - SameSite=Lax prevents CSRF
    """
    service = AuthService(db)
    try:
        user_response = await service.register(data)

        # Create session with HTTP-only cookie (BFF Pattern)
        await create_authenticated_session_with_cookie(
            response=response,
            user_id=str(user_response.id),
            remember_me=data.remember_me,
            event_name="user_registered_bff",
            extra_context={"email": user_response.email},
        )

        # Track successful registration
        auth_attempts_total.labels(method="register", status="success").inc()
        user_registrations_total.labels(provider="password", status="success").inc()

        return AuthResponseBFF(
            user=user_response,
            message=APIMessages.registration_successful(),
        )
    except HTTPException:
        # Track failed registration
        auth_attempts_total.labels(method="register", status="error").inc()
        user_registrations_total.labels(provider="password", status="error").inc()
        raise


@router.post(
    "/login",
    response_model=AuthResponseBFF,
    summary="Login user (BFF Pattern)",
    description="Login with email and password. Creates session and sets HTTP-only cookie. "
    "BFF Pattern: No tokens exposed to frontend.",
)
async def login(
    data: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_login),
    lia_session: str | None = Cookie(default=None),
) -> AuthResponseBFF:
    """
    Login user with email and password using BFF Pattern.

    Flow:
    1. Validates email exists
    2. Verifies password hash
    3. Creates session in Redis
    4. Sets HTTP-only session cookie
    5. Returns user info (no tokens)

    Security (BFF Pattern):
    - No JWT tokens in response body
    - Session stored server-side in Redis
    - HTTP-only cookie prevents XSS
    - SameSite=Lax prevents CSRF
    """
    service = AuthService(db)
    try:
        user_response = await service.login(data)

        # Create session with HTTP-only cookie (BFF Pattern)
        # Session rotation: old_session_id invalidated in PROD to prevent session fixation
        await create_authenticated_session_with_cookie(
            response=response,
            user_id=str(user_response.id),
            remember_me=data.remember_me,
            event_name="user_logged_in_bff",
            extra_context={"email": user_response.email},
            old_session_id=lia_session,
        )

        # Track successful login
        auth_attempts_total.labels(method="login", status="success").inc()
        user_logins_total.labels(provider="password", status="success").inc()

        return AuthResponseBFF(
            user=user_response,
            message=APIMessages.login_successful(),
        )
    except HTTPException:
        # Track failed login
        auth_attempts_total.labels(method="login", status="error").inc()
        user_logins_total.labels(provider="password", status="error").inc()
        raise


@router.post(
    "/refresh",
    status_code=410,
    response_model=None,
    summary="[REMOVED] Refresh token endpoint",
    description="This endpoint has been permanently removed with BFF Pattern migration. "
    "Sessions are automatically refreshed server-side.",
    deprecated=True,
    responses={
        410: {
            "description": "Endpoint permanently removed",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "error": "endpoint_permanently_removed",
                            "message": "Token refresh is no longer needed with BFF Pattern. "
                            "Sessions are automatically refreshed on authenticated requests.",
                            "migration_guide": "/docs#bff-authentication",
                            "alternative": "Use session-based authentication via /auth/login",
                            "deprecated_since": "v0.2.0",
                            "removed_in": "v0.3.0",
                        }
                    }
                }
            },
        }
    },
)
async def refresh_token(
    data: TokenRefreshRequest,
) -> None:
    """
    [REMOVED] Refresh access token endpoint.

    **This endpoint has been permanently removed.**

    ## Migration Path

    With the BFF (Backend-For-Frontend) Pattern, token refresh is no longer needed:

    1. **Sessions auto-refresh**: Every authenticated request automatically extends
       the session TTL server-side.
    2. **HTTP-only cookies**: Authentication state is managed via secure cookies,
       not client-side tokens.
    3. **No token management**: Frontend doesn't need to handle token refresh logic.

    ## What to do instead

    - Use `/auth/login` for initial authentication
    - Sessions remain valid as long as the user is active
    - No manual refresh required

    ## Why was this removed?

    - **Security**: HTTP-only cookies prevent XSS token theft
    - **Simplicity**: Eliminates client-side token refresh complexity
    - **Modern standard**: BFF pattern is industry best practice for SPAs

    For detailed migration guide, see: /docs#bff-authentication

    Raises:
        HTTPException: Always raises 410 Gone with migration details
    """
    raise HTTPException(
        status_code=410,
        detail={
            "error": "endpoint_permanently_removed",
            "message": "Token refresh is no longer needed with BFF Pattern. "
            "Sessions are automatically refreshed on authenticated requests.",
            "migration_guide": "/docs#bff-authentication",
            "alternative": "Use session-based authentication via /auth/login",
            "deprecated_since": "v0.2.0",
            "removed_in": "v0.3.0",
            "learn_more": "https://datatracker.ietf.org/doc/html/rfc7235#section-3.1",
        },
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout user (BFF Pattern)",
    description="Logout user by deleting session and clearing HTTP-only cookie.",
)
async def logout(
    response: Response,
    user: User = Depends(get_current_active_session),
    lia_session: str = Cookie(),
) -> MessageResponse:
    """
    Logout user by deleting session using BFF Pattern.

    Flow:
    1. Gets current session from HTTP-only cookie
    2. Deletes session from Redis
    3. Clears session cookie
    4. Returns success message

    Security (BFF Pattern):
    - Invalidates server-side session
    - Clears HTTP-only cookie
    - No tokens to revoke (stateless cleanup)
    """
    # Delete session from Redis
    redis = await get_redis_session()
    session_store = SessionStore(redis)
    await session_store.delete_session(lia_session)

    # Clear session cookie
    clear_session_cookie(response)

    logger.info(
        "user_logged_out_bff",
        user_id=str(user.id),
        session_id=lia_session,
        email=user.email,
    )

    return MessageResponse(message=APIMessages.logout_successful())


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    summary="Logout from all devices (BFF Pattern)",
    description="Logout user from all devices by deleting all sessions and clearing cookie.",
)
async def logout_all_devices(
    response: Response,
    user: User = Depends(get_current_active_session),
) -> MessageResponse:
    """
    Logout user from all devices using BFF Pattern.

    Flow:
    1. Gets current session from HTTP-only cookie
    2. Deletes ALL user sessions from Redis
    3. Clears session cookie
    4. Returns success message

    Security (BFF Pattern):
    - Invalidates all server-side sessions for this user
    - Clears HTTP-only cookie
    - Forces re-authentication on all devices
    """
    # Delete all user sessions from Redis
    redis = await get_redis_session()
    session_store = SessionStore(redis)
    await session_store.delete_all_user_sessions(str(user.id))

    # Clear session cookie
    clear_session_cookie(response)

    logger.info(
        "user_logged_out_all_devices_bff",
        user_id=str(user.id),
        email=user.email,
    )

    return MessageResponse(message=APIMessages.logout_all_successful())


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user (Session)",
    description="Get current authenticated user information from session cookie. "
    "BFF Pattern: Authenticates via HTTP-only cookie instead of JWT bearer token. "
    "Returns user info even if account is inactive (is_active=false).",
)
async def get_me(
    user: User = Depends(get_current_session),
) -> UserResponse:
    """
    Get current authenticated user from session.

    BFF Pattern: Uses HTTP-only session cookie for authentication.
    This endpoint works for both OAuth and email/password authenticated users.

    Note:
        Uses get_current_session (not get_current_active_session) to return
        user info even for inactive accounts. This allows the frontend to
        display the appropriate message on /account-inactive page.

        Returns user directly without additional DB query (user already fetched
        by get_current_session dependency).

    Args:
        user: Current user from HTTP-only cookie (already fetched from DB)

    Returns:
        UserResponse with current user information (including inactive users)
    """
    return UserResponse.model_validate(user)


@router.patch(
    "/me/memory-preference",
    response_model=MemoryPreferenceResponse,
    summary="Update memory preference",
    description="Enable or disable long-term memory for the current user. "
    "When disabled, no new memories are extracted and existing memories are not used.",
)
async def update_memory_preference(
    data: MemoryPreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MemoryPreferenceResponse:
    """
    Update user's long-term memory preference.

    This controls whether:
    - New memories are extracted from conversations (memory_extractor)
    - Existing memories are injected into conversation context (memory_injection)

    Args:
        data: Memory preference request with enabled/disabled state
        user: Current authenticated user
        db: Database session

    Returns:
        MemoryPreferenceResponse with updated state and confirmation
    """
    # Update user's memory preference
    user.memory_enabled = data.memory_enabled
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_memory_preference_updated",
        user_id=str(user.id),
        memory_enabled=data.memory_enabled,
    )

    return MemoryPreferenceResponse(
        memory_enabled=user.memory_enabled,
        message=APIMessages.memory_preference_updated(enabled=data.memory_enabled),
    )


@router.patch(
    "/me/execution-mode-preference",
    response_model=ExecutionModePreferenceResponse,
    summary="Update execution mode preference",
    description="Switch between pipeline (classic planner) and react (ReAct agent loop) execution modes.",
)
async def update_execution_mode_preference(
    data: ExecutionModePreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ExecutionModePreferenceResponse:
    """
    Update user's execution mode preference.

    This controls how actionable queries are processed:
    - pipeline: Planner generates a plan, tools execute directly (fast, economical)
    - react: ReAct agent reasons iteratively with tools (autonomous, adaptive)

    Args:
        data: Execution mode preference with pipeline or react value.
        user: Current authenticated user.
        db: Database session.

    Returns:
        ExecutionModePreferenceResponse with updated state and confirmation.
    """
    user.execution_mode = data.execution_mode
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_execution_mode_preference_updated",
        user_id=str(user.id),
        execution_mode=data.execution_mode,
    )

    mode_label = "ReAct" if data.execution_mode == "react" else "Pipeline"
    return ExecutionModePreferenceResponse(
        execution_mode=user.execution_mode,
        message=f"Execution mode switched to {mode_label}",
    )


@router.patch(
    "/me/weather-location-preference",
    response_model=WeatherLocationPreferenceResponse,
    summary="Update weather last-known location opt-in",
    description=(
        "Toggle persistence of the browser geolocation for proactive weather "
        "notifications. Disabling wipes any stored location."
    ),
)
async def update_weather_location_preference(
    data: WeatherLocationPreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> WeatherLocationPreferenceResponse:
    """Update the weather last-known location opt-in flag.

    When ``enabled`` is False, the persisted last-known location is wiped
    immediately so no stale coordinates linger after opt-out.

    Args:
        data: Toggle payload (``enabled``).
        user: Current authenticated user.
        db: Database session.

    Returns:
        Current opt-in state with a localized confirmation message.
    """
    user.weather_use_last_known_location = data.enabled
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if not data.enabled:
        await UserLocationService(db).wipe_last_known_location(user)

    logger.info(
        "user_weather_location_preference_updated",
        user_id=str(user.id),
        enabled=data.enabled,
    )

    return WeatherLocationPreferenceResponse(
        enabled=user.weather_use_last_known_location,
        message=APIMessages.weather_location_preference_updated(enabled=data.enabled),
    )


@router.put(
    "/me/last-location",
    response_model=LastLocationUpdateResponse,
    summary="Push a browser geolocation sample",
    description=(
        "Persist the current browser geolocation for proactive weather alerts. "
        "Requires opt-in (weather_use_last_known_location = True). Throttled "
        "server-side to one write per user per 30 minutes."
    ),
)
async def put_last_location(
    data: LastLocationUpdateRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LastLocationUpdateResponse:
    """Persist a geolocation sample for the authenticated user.

    Returns 403 when the user has not opted in. Returns 200 with
    ``throttled=True`` when the call is rejected due to the throttle
    window — this is informational, not an error.

    Args:
        data: New geolocation sample.
        user: Current authenticated user.
        db: Database session.

    Returns:
        Update result (``updated``, ``throttled``).

    Raises:
        HTTPException: 403 Forbidden if the user has not opted in.
    """
    result = await UserLocationService(db).update_last_known_location(
        user, lat=data.lat, lon=data.lon, accuracy=data.accuracy
    )
    if result.forbidden:
        raise_permission_denied(
            action="store",
            resource_type="last_known_location",
            user_id=user.id,
            details="weather_use_last_known_location is disabled for this user",
        )
    return LastLocationUpdateResponse(updated=result.updated, throttled=result.throttled)


@router.get(
    "/me/last-location",
    response_model=LastLocationViewResponse,
    summary="View the currently stored last-known location",
    description=(
        "Transparency endpoint (RGPD): returns the decrypted last-known "
        "location stored for the current user, or an empty payload if none."
    ),
)
async def get_last_location(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> LastLocationViewResponse:
    """Return the user's stored last-known location for transparency.

    Args:
        user: Current authenticated user.
        db: Database session.

    Returns:
        ``LastLocationViewResponse`` with ``stored=False`` if nothing is
        persisted, otherwise the decrypted view including a ``stale`` flag.
    """
    stored = await UserLocationService(db).get_last_known_location(user)
    if stored is None:
        return LastLocationViewResponse(stored=False)
    return LastLocationViewResponse(
        stored=True,
        lat=stored.lat,
        lon=stored.lon,
        accuracy=stored.accuracy,
        updated_at=stored.updated_at,
        stale=stored.stale,
    )


@router.patch(
    "/me/voice-preference",
    response_model=VoicePreferenceResponse,
    summary="Update voice preference",
    description="Enable or disable voice comments (TTS) for the current user. "
    "When enabled, the assistant generates short voice comments during responses.",
)
async def update_voice_preference(
    data: VoicePreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> VoicePreferenceResponse:
    """
    Update user's voice comments (TTS) preference.

    This controls whether:
    - The assistant generates short voice comments during streaming responses
    - Audio is synthesized via Edge TTS (Microsoft neural voices) and streamed to the client

    Args:
        data: Voice preference request with enabled/disabled state
        user: Current authenticated user
        db: Database session

    Returns:
        VoicePreferenceResponse with updated state and confirmation
    """
    # Update user's voice preference
    user.voice_enabled = data.voice_enabled
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_voice_preference_updated",
        user_id=str(user.id),
        voice_enabled=data.voice_enabled,
    )

    return VoicePreferenceResponse(
        voice_enabled=user.voice_enabled,
        message=APIMessages.voice_preference_updated(enabled=data.voice_enabled),
    )


@router.get(
    "/me/voice-mode-preference",
    response_model=VoiceModePreferenceResponse,
    summary="Get voice mode preference",
    description="Get the current user's voice mode preference (wake word + STT input).",
)
async def get_voice_mode_preference(
    user: User = Depends(get_current_active_session),
) -> VoiceModePreferenceResponse:
    """
    Get user's voice mode preference.

    Returns:
        VoiceModePreferenceResponse with current state
    """
    return VoiceModePreferenceResponse(
        voice_mode_enabled=user.voice_mode_enabled,
        message="",
    )


@router.patch(
    "/me/voice-mode-preference",
    response_model=VoiceModePreferenceResponse,
    summary="Update voice mode preference",
    description="Enable or disable voice mode (wake word detection + STT input) for the current user. "
    "When enabled, the user can activate voice input by saying the wake word or tapping.",
)
async def update_voice_mode_preference(
    data: VoiceModePreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> VoiceModePreferenceResponse:
    """
    Update user's voice mode preference.

    This controls whether:
    - Voice mode badge is active in chat header
    - Wake word detection (Sherpa-onnx KWS) is enabled
    - STT input via WebSocket is available

    Args:
        data: Voice mode preference request with enabled/disabled state
        user: Current authenticated user
        db: Database session

    Returns:
        VoiceModePreferenceResponse with updated state and confirmation
    """
    # Update user's voice mode preference
    user.voice_mode_enabled = data.voice_mode_enabled
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_voice_mode_preference_updated",
        user_id=str(user.id),
        voice_mode_enabled=data.voice_mode_enabled,
    )

    return VoiceModePreferenceResponse(
        voice_mode_enabled=user.voice_mode_enabled,
        message=APIMessages.voice_mode_preference_updated(enabled=data.voice_mode_enabled),
    )


@router.patch(
    "/me/tokens-display-preference",
    response_model=TokensDisplayPreferenceResponse,
    summary="Update tokens display preference",
    description="Enable or disable token usage and costs display for the current user. "
    "When enabled, token counts and costs are shown under assistant messages on desktop.",
)
async def update_tokens_display_preference(
    data: TokensDisplayPreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TokensDisplayPreferenceResponse:
    """
    Update user's tokens display preference.

    This controls whether:
    - Token counts (input, output, cached) are displayed under assistant messages
    - Cost in EUR is displayed for each message and conversation total

    Args:
        data: Tokens display preference request with enabled/disabled state
        user: Current authenticated user
        db: Database session

    Returns:
        TokensDisplayPreferenceResponse with updated state and confirmation
    """
    # Update user's tokens display preference
    user.tokens_display_enabled = data.tokens_display_enabled
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_tokens_display_preference_updated",
        user_id=str(user.id),
        tokens_display_enabled=data.tokens_display_enabled,
    )

    return TokensDisplayPreferenceResponse(
        tokens_display_enabled=user.tokens_display_enabled,
        message=APIMessages.tokens_display_preference_updated(enabled=data.tokens_display_enabled),
    )


@router.patch(
    "/me/onboarding-preference",
    response_model=OnboardingPreferenceResponse,
    summary="Update onboarding preference",
    description="Mark the onboarding tutorial as completed/dismissed for the current user. "
    "Once marked as completed, the tutorial will no longer be displayed on login.",
)
async def update_onboarding_preference(
    data: OnboardingPreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> OnboardingPreferenceResponse:
    """
    Update user's onboarding tutorial completion preference.

    This controls whether the onboarding tutorial is displayed after login.
    Once the user completes or dismisses the tutorial, this endpoint is called
    to mark it as completed, preventing future displays.

    Args:
        data: Onboarding preference request with completed state
        user: Current authenticated user
        db: Database session

    Returns:
        OnboardingPreferenceResponse with updated state and confirmation
    """
    # Update user's onboarding completed preference
    user.onboarding_completed = data.onboarding_completed
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_onboarding_preference_updated",
        user_id=str(user.id),
        onboarding_completed=data.onboarding_completed,
    )

    return OnboardingPreferenceResponse(
        onboarding_completed=user.onboarding_completed,
        message=APIMessages.onboarding_preference_updated(),
    )


@router.patch(
    "/me/debug-panel-preference",
    response_model=DebugPanelPreferenceResponse,
    summary="Update debug panel preference",
    description="Enable or disable the debug panel for the current user. "
    "Requires the admin to have enabled user-level debug panel access.",
)
async def update_debug_panel_preference(
    data: DebugPanelPreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DebugPanelPreferenceResponse:
    """
    Update user's debug panel preference.

    This controls whether the debug panel is visible for this user.
    The effective visibility also depends on the admin system setting
    debug_panel_user_access_enabled being True.

    Args:
        data: Debug panel preference request with enabled/disabled state
        user: Current authenticated user
        db: Database session

    Returns:
        DebugPanelPreferenceResponse with updated state and confirmation
    """
    # Update user's debug panel preference
    user.debug_panel_enabled = data.debug_panel_enabled
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_debug_panel_preference_updated",
        user_id=str(user.id),
        debug_panel_enabled=data.debug_panel_enabled,
    )

    return DebugPanelPreferenceResponse(
        debug_panel_enabled=user.debug_panel_enabled,
        message=APIMessages.debug_panel_preference_updated(enabled=data.debug_panel_enabled),
    )


@router.patch(
    "/me/sub-agents-preference",
    response_model=SubAgentsPreferenceResponse,
    summary="Update sub-agents delegation preference",
    description="Enable or disable delegation to specialized sub-agents for the current user.",
)
async def update_sub_agents_preference(
    data: SubAgentsPreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SubAgentsPreferenceResponse:
    """Update user's sub-agents delegation preference.

    Controls whether the principal assistant can delegate tasks
    to specialized sub-agents (research, analysis, writing, etc.).

    Args:
        data: Sub-agents preference request with enabled/disabled state.
        user: Current authenticated user.
        db: Database session.

    Returns:
        SubAgentsPreferenceResponse with updated state and confirmation.
    """
    user.sub_agents_enabled = data.sub_agents_enabled
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_sub_agents_preference_updated",
        user_id=str(user.id),
        sub_agents_enabled=data.sub_agents_enabled,
    )

    return SubAgentsPreferenceResponse(
        sub_agents_enabled=user.sub_agents_enabled,
        message=APIMessages.sub_agents_preference_updated(enabled=data.sub_agents_enabled),
    )


@router.patch(
    "/me/display-mode-preference",
    response_model=DisplayModePreferenceResponse,
    summary="Update response display mode",
    description="Set the response display mode: 'cards' (structured HTML cards), "
    "'html' (rich HTML formatting), or 'markdown' (plain text).",
)
async def update_display_mode_preference(
    data: DisplayModePreferenceRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DisplayModePreferenceResponse:
    """Update user's response display mode.

    Controls how assistant responses are rendered:
    - cards: Structured HTML data cards (contacts, events, emails, etc.)
    - html: Rich HTML formatting with styled prose
    - markdown: Plain markdown text

    Args:
        data: Display mode preference request with mode value.
        user: Current authenticated user.
        db: Database session.

    Returns:
        DisplayModePreferenceResponse with updated mode and confirmation.
    """
    from src.core.constants import RESPONSE_DISPLAY_MODE_CHOICES

    if data.response_display_mode not in RESPONSE_DISPLAY_MODE_CHOICES:
        from src.core.exceptions import raise_invalid_input

        raise_invalid_input(
            f"Invalid display mode: {data.response_display_mode}. "
            f"Must be one of: {', '.join(RESPONSE_DISPLAY_MODE_CHOICES)}"
        )

    user.response_display_mode = data.response_display_mode
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_display_mode_preference_updated",
        user_id=str(user.id),
        response_display_mode=data.response_display_mode,
    )

    return DisplayModePreferenceResponse(
        response_display_mode=user.response_display_mode,
        message=APIMessages.display_mode_preference_updated(mode=data.response_display_mode),
    )


@router.post(
    "/verify-email",
    response_model=UserResponse,
    summary="Verify email",
    description="Verify user email with verification token from email.",
)
async def verify_email(
    token: str = Query(..., description="Email verification token"),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Verify user email with verification token."""
    service = AuthService(db)
    return await service.verify_email(token)


@router.post(
    "/request-password-reset",
    response_model=MessageResponse,
    summary="Request password reset",
    description="Request password reset email. Always returns success to prevent email enumeration.",
)
async def request_password_reset(
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_password_reset_request),
) -> MessageResponse:
    """Request password reset email."""
    service = AuthService(db)
    await service.request_password_reset(data.email)

    return MessageResponse(message=APIMessages.password_reset_sent())


@router.post(
    "/reset-password",
    response_model=UserResponse,
    summary="Reset password",
    description="Reset password with reset token from email.",
)
async def reset_password(
    data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_password_reset),
) -> UserResponse:
    """Reset password with reset token."""
    service = AuthService(db)
    return await service.reset_password(data.token, data.new_password)


# Google OAuth endpoints


@router.get(
    "/google/login",
    summary="Initiate Google OAuth",
    description="Initiate Google OAuth flow. Returns authorization URL to redirect user to.",
)
async def google_login(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Initiate Google OAuth login flow."""
    # Track OAuth initiation
    oauth_initiate_total.labels(provider="google", flow_type="authentication").inc()

    with oauth_initiate_duration_seconds.labels(provider="google").time():
        service = AuthService(db)
        auth_url, state = await service.initiate_google_oauth()

    return {
        "authorization_url": auth_url,
        "state": state,
    }


@router.get(
    "/google/callback",
    summary="Google OAuth callback (BFF Pattern)",
    description="Handle Google OAuth callback with authorization code. "
    "Receives code and state as query parameters from Google redirect. "
    "Creates session and redirects to frontend with HTTP-only cookie.",
    include_in_schema=False,  # Hidden from docs (internal redirect)
)
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Handle Google OAuth callback with BFF Pattern.

    Google redirects the user's browser here after authentication.

    Flow (RFC 6749 + OAuth 2.1 + BFF Pattern):
    1. Validates the state token (CSRF protection)
    2. Exchanges the code for Google access tokens (with PKCE)
    3. Retrieves user info from Google
    4. Creates or updates the user in our database
    5. Creates a session in Redis
    6. Sets HTTP-only session cookie
    7. Redirects browser to frontend dashboard

    Security benefits:
    - JWT tokens never exposed to browser (prevents XSS attacks)
    - HTTP-only cookies prevent JavaScript access
    - SameSite=Lax prevents CSRF
    - Tokens stored server-side in Redis

    Conforms to:
    - RFC 6749 (OAuth 2.0)
    - OAuth 2.1 Security Best Practices
    - BFF (Backend for Frontend) Pattern
    """
    from fastapi.responses import RedirectResponse

    # Track OAuth callback with metrics
    try:
        with oauth_callback_duration_seconds.labels(provider="google").time():
            # Process OAuth callback
            service = AuthService(db)
            user_response = await service.handle_google_callback(code, state)

            # Create redirect response to frontend
            redirect_url = f"{settings.frontend_url}/dashboard"
            response = RedirectResponse(url=redirect_url, status_code=302)

            # Create session with HTTP-only cookie (BFF Pattern)
            # OAuth default: 7 days session (remember_me=False)
            await create_authenticated_session_with_cookie(
                response=response,
                user_id=str(user_response.id),
                remember_me=False,
                event_name="oauth_callback_success_bff",
                extra_context={"email": user_response.email, "redirect_to": redirect_url},
            )

        # Track successful callback
        oauth_callback_total.labels(provider="google", status="success").inc()

        return response

    except Exception as e:
        # Track failed callback
        oauth_callback_total.labels(provider="google", status="failed").inc()

        # Determine error type for detailed metrics
        error_type = "unknown"
        if "state" in str(e).lower():
            error_type = "state_mismatch"
            oauth_callback_errors_total.labels(provider="google", error_type="state_mismatch").inc()
        elif "pkce" in str(e).lower() or "code_verifier" in str(e).lower():
            error_type = "pkce_failed"
            oauth_callback_errors_total.labels(provider="google", error_type="pkce_failed").inc()
        elif "token" in str(e).lower():
            error_type = "token_exchange_failed"
            oauth_callback_errors_total.labels(
                provider="google", error_type="token_exchange_failed"
            ).inc()
        else:
            oauth_callback_errors_total.labels(provider="google", error_type="unknown").inc()

        logger.error("google_oauth_callback_failed", error=str(e), error_type=error_type)

        # Re-raise to let FastAPI handle it
        raise


# ========== PROFILE IMAGE PROXY ==========
# Proxy for Google profile images to work with COEP: require-corp

# Allowed Google image domains (prevent SSRF)
ALLOWED_IMAGE_DOMAINS: frozenset[str] = frozenset(
    {
        "lh3.googleusercontent.com",
        "lh4.googleusercontent.com",
        "lh5.googleusercontent.com",
        "lh6.googleusercontent.com",
    }
)


@router.get(
    "/profile-image-proxy",
    summary="Proxy Google profile image",
    description="Proxy endpoint for Google profile images to work with COEP: require-corp. "
    "Only allows images from Google's user content domains (lh3/4/5/6.googleusercontent.com).",
    responses={
        200: {"content": {"image/*": {}}, "description": "Profile image"},
        400: {"description": "Invalid or disallowed URL"},
        502: {"description": "Failed to fetch image from source"},
    },
)
async def proxy_profile_image(
    url: str = Query(..., description="Google profile image URL to proxy"),
    current_user: User = Depends(get_current_active_session),
) -> StreamingResponse:
    """
    Proxy Google profile images for COEP compatibility.

    Google's lh3.googleusercontent.com doesn't send CORS headers,
    which breaks images when using COEP: require-corp.
    This proxy fetches the image server-side and returns it with proper headers.

    Security:
    - Only allows URLs from Google's user content domains
    - Requires authentication (prevents abuse)

    Args:
        url: Full URL to the Google profile image
        current_user: Current authenticated user (for rate limiting/auth)

    Returns:
        StreamingResponse with the image data
    """
    from urllib.parse import urlparse

    import httpx

    user_id = current_user.id

    # Parse and validate URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise_invalid_input("Invalid URL format", url=url[:100] if url else None)

    # Security: Only allow Google image domains
    if parsed.hostname not in ALLOWED_IMAGE_DOMAINS:
        logger.warning(
            "profile_image_proxy_blocked_domain",
            user_id=str(user_id),
            domain=parsed.hostname,
        )
        raise_invalid_input(
            "Domain not allowed. Only Google profile images are supported.",
            domain=parsed.hostname,
        )

    # Security: Only allow HTTPS
    if parsed.scheme != "https":
        raise_invalid_input("Only HTTPS URLs are allowed", scheme=parsed.scheme)

    # Fetch the image
    logger.info(
        "profile_image_proxy_request",
        user_id=str(user_id),
        url=url[:100] if len(url) > 100 else url,
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                follow_redirects=True,
                timeout=settings.http_timeout_external_api,
                headers={
                    "User-Agent": "LIA/1.0",
                },
            )

            # Security: validate final URL after redirects (SSRF prevention)
            final_hostname = urlparse(str(response.url)).hostname
            if final_hostname not in ALLOWED_IMAGE_DOMAINS:
                logger.warning(
                    "profile_image_proxy_redirect_blocked",
                    user_id=str(user_id),
                    original_url=url[:100],
                    final_hostname=final_hostname,
                )
                raise_invalid_input(
                    "Redirect to disallowed domain",
                    domain=final_hostname,
                )

            if response.status_code != 200:
                logger.warning(
                    "profile_image_proxy_fetch_failed",
                    user_id=str(user_id),
                    url=url[:100],
                    status_code=response.status_code,
                )
                raise_external_service_fetch_error(
                    "google_profile_image", "image", response.status_code
                )

            # Get content type from response
            content_type = response.headers.get("content-type", "image/jpeg")

            logger.info(
                "profile_image_proxy_success",
                user_id=str(user_id),
                content_length=len(response.content),
            )

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cross-Origin-Resource-Policy": "cross-origin",
                    "Cache-Control": "private, max-age=86400",
                },
            )

    except httpx.TimeoutException:
        logger.warning(
            "profile_image_proxy_timeout",
            user_id=str(user_id),
            url=url[:100],
        )
        raise_external_service_connection_error("google_profile_image")
    except httpx.RequestError as e:
        logger.warning(
            "profile_image_proxy_request_error",
            user_id=str(user_id),
            url=url[:100],
            error=str(e),
        )
        raise_external_service_connection_error("google_profile_image")
