"""Provider sign-in endpoints: the browser flow and the native shell's handoff.

Split out of ``auth/router.py`` because it had outgrown its size cap, and
because these three routes form one subject: starting a provider flow, ending
it, and — when a native shell started it — handing the result across from the
system browser into the app's own WebView.

**The demonstrator guard is re-declared here on purpose.** It hung on the auth
router as a router-level dependency; moving these routes without carrying it
would have silently reopened provider sign-in on a public demonstrator, which
``forbid_federated_signin_in_demo`` exists to close. A test asserts it is
mounted.

The native handoff itself — why a custom scheme, why a verifier — is documented
in :mod:`src.domains.auth.native_handoff`.
"""

import uuid
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.demo_mode import forbid_federated_signin_in_demo
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_credentials, raise_invalid_input
from src.core.i18n_api_messages import APIMessages
from src.core.session_helpers import (
    create_authenticated_session_with_cookie,
    set_mfa_pending_cookie,
)
from src.domains.auth.dependencies import rate_limit_native_callback
from src.domains.auth.login_notification import notify_new_login_if_unknown
from src.domains.auth.native_handoff import (
    NATIVE_CHALLENGE_METADATA_KEY,
    build_native_redirect,
    consume_handoff,
    is_valid_challenge,
    issue_handoff,
    peek_native_challenge,
)
from src.domains.auth.schemas import (
    LoginResponseBFF,
    NativeCallbackRequest,
    UserResponse,
)
from src.domains.auth.service import AuthService
from src.domains.auth.totp_service import TOTPService
from src.domains.users.repository import UserRepository
from src.infrastructure.observability.metrics import auth_attempts_total, user_logins_total
from src.infrastructure.observability.metrics_oauth import (
    oauth_callback_duration_seconds,
    oauth_callback_errors_total,
    oauth_callback_total,
    oauth_initiate_duration_seconds,
    oauth_initiate_total,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    dependencies=[Depends(forbid_federated_signin_in_demo)],
)


@router.get(
    "/google/login",
    summary="Initiate Google OAuth",
    description="Initiate Google OAuth flow. Returns authorization URL to redirect user to.",
)
async def google_login(
    db: AsyncSession = Depends(get_db),
    native_challenge: str | None = Query(
        None,
        description=(
            "SHA-256 (base64url, unpadded) of a verifier held by a native "
            "shell. Supplied only by the mobile apps: it makes the callback "
            "return through a deep link instead of setting a browser session."
        ),
    ),
) -> dict:
    """Initiate Google OAuth login flow."""
    # Track OAuth initiation
    oauth_initiate_total.labels(provider="google", flow_type="authentication").inc()

    # Rejected here rather than at redemption: a malformed challenge can never
    # match a verifier, so accepting it would mint a code guaranteed to fail
    # minutes later, with nothing left to explain why.
    if native_challenge is not None and not is_valid_challenge(native_challenge):
        raise_invalid_input("native_challenge is not a well-formed base64url PKCE challenge")

    metadata = (
        {NATIVE_CHALLENGE_METADATA_KEY: native_challenge} if native_challenge is not None else None
    )

    with oauth_initiate_duration_seconds.labels(provider="google").time():
        service = AuthService(db)
        auth_url, state = await service.initiate_google_oauth(metadata=metadata)

    return {
        "authorization_url": auth_url,
        "state": state,
    }


#: OAuth 2.0 error codes a provider may legitimately return (RFC 6749 §4.1.2.1
#: plus the OpenID Connect and Google-specific ones LIA can actually receive).
#: Anything outside this set is attacker-controlled text: it must never reach a
#: Prometheus label — unbounded cardinality is a metric explosion a stranger can
#: trigger — nor be reflected into a redirect.
_KNOWN_PROVIDER_ERRORS = frozenset(
    {
        "access_denied",
        "admin_policy_enforced",
        "consent_required",
        "disallowed_useragent",
        "interaction_required",
        "invalid_client",
        "invalid_request",
        "invalid_scope",
        "login_required",
        "org_internal",
        "server_error",
        "temporarily_unavailable",
        "unauthorized_client",
        "unsupported_response_type",
    }
)

#: What an unrecognised provider error collapses to.
_UNKNOWN_PROVIDER_ERROR = "provider_error"


def _bounded_provider_error(error: str | None) -> str:
    """Reduce a provider error to a value safe to label, log and reflect.

    Args:
        error: Raw ``error`` query parameter, straight off the redirect.

    Returns:
        The code itself when it is one the specification defines, otherwise a
        single collapsing value.
    """
    if error is None:
        return "invalid_callback"
    return error if error in _KNOWN_PROVIDER_ERRORS else _UNKNOWN_PROVIDER_ERROR


def _classify_oauth_error(error: Exception) -> str:
    """Name the failure for metrics, from the message the provider chain raised.

    String matching is what the surrounding code has always done here; it is
    kept verbatim so the metric labels stay comparable across the change.

    Args:
        error: Exception raised while completing the flow.

    Returns:
        A short, bounded label for the ``error_type`` metric dimension.
    """
    message = str(error).lower()
    if "state" in message:
        return "state_mismatch"
    if "pkce" in message or "code_verifier" in message:
        return "pkce_failed"
    if "token" in message:
        return "token_exchange_failed"
    return "unknown"


def _oauth_failure_location(native_challenge: str | None, reason: str) -> str:
    """Where to send a user whose provider sign-in did not complete.

    Args:
        native_challenge: Present when a native shell started the flow.
        reason: Short machine-readable cause, surfaced to the client.

    Returns:
        A deep link for a native shell, or the frontend's OAuth error page —
        the one already built for this, which shows the message and returns to
        the sign-in form.
    """
    if native_challenge is not None:
        return build_native_redirect(error=reason)
    return f"{settings.frontend_url}/oauth-callback?{urlencode({'error': reason})}"


@router.get(
    "/google/callback",
    summary="Google OAuth callback (BFF Pattern)",
    description="Handle Google OAuth callback with authorization code. "
    "Ends in one of three redirects: the dashboard with a session cookie, the "
    "second-factor step when TOTP is active, or a deep link back into the "
    "native shell that started the flow.",
    include_in_schema=False,  # Hidden from docs (internal redirect)
)
async def google_callback(
    http_request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Handle Google OAuth callback with BFF Pattern.

    Google redirects the user's browser here after authentication, and this
    always answers with a redirect — never a body. Where it points depends on
    two things read before anything is spent: whether a native shell started
    the flow, and whether the account still owes a second factor.

    Flow (RFC 6749 + OAuth 2.1 + BFF Pattern):
    1. Peeks the state for the flow's own metadata, WITHOUT consuming it
    2. Refuses early when the provider returned an error or the callback is
       malformed — answering where the flow came from, so a native traveller
       is never stranded in a browser the app cannot reach
    3. Exchanges the code for Google access tokens (with PKCE), which spends
       the state
    4. Creates or updates the user in our database
    5. Then exactly one of:
       - native shell → a single-use handoff code on a deep link, and NO
         browser session: the app redeems it from its own WebView;
       - TOTP active → no session either, an httpOnly pending cookie and the
         second-factor form;
       - otherwise → the session cookie and the dashboard.

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
    # Resolved inside the try: a Redis outage while peeking must be counted and
    # answered like any other failure, not escape as an unmetered 500.
    native_challenge: str | None = None

    # Track OAuth callback with metrics
    try:
        # Read the flow's own metadata BEFORE the token exchange spends the
        # state — the same peek `_handle_oauth_connector_callback_stateless`
        # performs for the user id. Which surface started the flow decides
        # where it ends, including when it ends badly.
        if state:
            native_challenge = await peek_native_challenge(state)

        if error or not code or not state:
            # The provider refused, or the callback is malformed. Nothing to
            # exchange — and a 422 would leave the traveller staring at raw
            # JSON, or worse, stranded in a browser the app cannot reach.
            reason = _bounded_provider_error(error)
            oauth_callback_total.labels(provider="google", status="failed").inc()
            oauth_callback_errors_total.labels(provider="google", error_type=reason).inc()
            logger.info("google_oauth_callback_refused", reason=reason)
            return RedirectResponse(
                url=_oauth_failure_location(native_challenge, reason), status_code=302
            )

        with oauth_callback_duration_seconds.labels(provider="google").time():
            # Process OAuth callback
            service = AuthService(db)
            user_response = await service.handle_google_callback(code, state)

            # The second factor is owed here exactly as it is on the password
            # path. Until 2026-08-24 it was not asked for, so a TOTP-active
            # account could walk past it by signing in with Google.
            totp_service = TOTPService(db)
            mfa_pending = settings.mfa_enabled and await totp_service.has_confirmed_totp(
                user_response.id
            )

            if native_challenge is not None:
                # A native shell: the browser must NOT end up holding the
                # session. Hand back a code the app can redeem from its own
                # WebView, carrying whether a second factor is still owed.
                handoff_code = await issue_handoff(
                    user_id=str(user_response.id),
                    challenge=native_challenge,
                    mfa_pending=mfa_pending,
                )
                oauth_callback_total.labels(provider="google", status="success").inc()
                logger.info(
                    "oauth_callback_native_handoff_issued",
                    user_id=str(user_response.id),
                    mfa_pending=mfa_pending,
                )
                return RedirectResponse(
                    url=build_native_redirect(code=handoff_code), status_code=302
                )

            if mfa_pending:
                # A redirect cannot answer with JSON, so the pending token
                # travels in an httpOnly cookie rather than the query string.
                pending_token = await totp_service.create_pending_token(
                    user_response.id, remember_me=False
                )
                response = RedirectResponse(
                    url=f"{settings.frontend_url}/login?mfa=1", status_code=302
                )
                set_mfa_pending_cookie(
                    response, pending_token, max_age=settings.mfa_pending_ttl_seconds
                )
                oauth_callback_total.labels(provider="google", status="success").inc()
                auth_attempts_total.labels(method="oauth_google", status="mfa_pending").inc()
                logger.info("oauth_callback_mfa_pending", user_id=str(user_response.id))
                return response

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
                auth_methods=["oauth_google"],
                request=http_request,
            )

        # Track successful callback
        oauth_callback_total.labels(provider="google", status="success").inc()

        # A4: the OAuth redirect cannot carry an FCM attestation safely
        # (GET navigation) — always treated as an unknown device.
        oauth_user = await UserRepository(db).get_user_minimal_for_session(user_response.id)
        if oauth_user is not None:
            await notify_new_login_if_unknown(db, oauth_user, known=False)

        return response

    except Exception as e:
        # Track failed callback
        oauth_callback_total.labels(provider="google", status="failed").inc()

        error_type = _classify_oauth_error(e)
        oauth_callback_errors_total.labels(provider="google", error_type=error_type).inc()

        logger.error("google_oauth_callback_failed", error=str(e), error_type=error_type)

        # Answer where the flow came from. Re-raising used to leave a native
        # traveller in the system browser, looking at an API error, with no way
        # back into the app that sent them there.
        return RedirectResponse(
            url=_oauth_failure_location(native_challenge, error_type), status_code=302
        )


@router.post(
    "/native/callback",
    response_model=LoginResponseBFF,
    summary="Redeem a native session-handoff code (BFF Pattern)",
    description=(
        "Second half of a native shell's provider sign-in. The system browser "
        "completed the OAuth flow and the operating system handed the app a "
        "deep link; the WebView presents that code together with the verifier "
        "it kept, and receives the session cookie in its own jar."
    ),
)
async def native_callback(
    data: NativeCallbackRequest,
    response: Response,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_native_callback),
) -> LoginResponseBFF:
    """Turn a handoff code into a session, or into the second factor still owed.

    The route is deliberately named ``…/auth/native/callback``:
    ``is_federated_signin_path`` classifies by SHAPE, so this path inherits the
    public demonstrator's refusal of provider sign-in without anyone having to
    remember to add it to a list.

    Args:
        data: The deep link's code and the WebView's verifier.
        response: Carries the session or pending cookie back to the WebView.
        http_request: Client metadata for the session record.
        db: Database session.
        _rate_limit: Per-IP throttle — a bearer code deserves no free retries.

    Returns:
        The signed-in user, or ``mfa_required`` when a second factor is owed.

    Raises:
        HTTPException: 401 when the code is unknown, expired, already spent,
            presented with the wrong verifier, or names an account that can no
            longer sign in. Every one of those answers the same thing.
    """
    handoff = await consume_handoff(data.code, data.verifier)
    if handoff is None:
        auth_attempts_total.labels(method="native_callback", status="error").inc()
        raise_invalid_credentials()

    # The payload is ours, so this cannot fail in practice — but a corrupted
    # Redis value must answer 401 like every other unusable code, never surface
    # as an unhandled exception on an authentication endpoint.
    try:
        user_id = uuid.UUID(handoff.user_id)
    except ValueError:
        logger.warning("native_callback_corrupt_payload")
        auth_attempts_total.labels(method="native_callback", status="error").inc()
        raise_invalid_credentials()

    user = await UserRepository(db).get_user_minimal_for_session(user_id)
    if user is None or not user.is_active:
        auth_attempts_total.labels(method="native_callback", status="error").inc()
        raise_invalid_credentials()

    if handoff.mfa_pending:
        # The WebView is the caller, so the pending cookie lands in the jar
        # that will present it to /auth/mfa/verify — which the browser's jar
        # could never have done.
        pending_token = await TOTPService(db).create_pending_token(user.id, remember_me=False)
        set_mfa_pending_cookie(response, pending_token, max_age=settings.mfa_pending_ttl_seconds)
        auth_attempts_total.labels(method="native_callback", status="mfa_pending").inc()
        logger.info("native_callback_mfa_pending", user_id=str(user.id))
        return LoginResponseBFF(
            mfa_required=True,
            message=APIMessages.mfa_code_required(),
        )

    await create_authenticated_session_with_cookie(
        response=response,
        user_id=str(user.id),
        remember_me=False,
        event_name="native_callback_success_bff",
        extra_context={"email": user.email},
        auth_methods=["oauth_google", "native_app"],
        request=http_request,
    )

    auth_attempts_total.labels(method="native_callback", status="success").inc()
    user_logins_total.labels(provider="google_native", status="success").inc()

    # A4: like the browser redirect it continues, the flow carries no device
    # attestation — the code came back through the operating system.
    await notify_new_login_if_unknown(db, user, known=False)

    return LoginResponseBFF(
        user=UserResponse.model_validate(user),
        message=APIMessages.login_successful(),
    )
