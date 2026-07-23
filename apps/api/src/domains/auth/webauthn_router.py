"""WebAuthn passkey endpoints (security program D1, Lot 1).

Mounted only when ``MFA_ENABLED`` is true (see ``api/v1/routes.py``).
Anonymous ceremony endpoints are IP-rate-limited; enrollment/management
endpoints are rate-limited per authenticated user.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    RATE_LIMIT_WEBAUTHN_AUTH_PER_MINUTE,
    RATE_LIMIT_WEBAUTHN_ENROLL_PER_MINUTE,
)
from src.core.dependencies import get_db
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import (
    get_current_active_session,
    require_recent_step_up,
)
from src.core.session_helpers import create_authenticated_session_with_cookie
from src.domains.auth.dependencies import (
    create_auth_rate_limiter,
    create_user_rate_limiter,
)
from src.domains.auth.schemas import (
    AuthResponseBFF,
    UserResponse,
    WebAuthnAuthenticateVerifyRequest,
    WebAuthnAuthOptionsResponse,
    WebAuthnCredentialResponse,
    WebAuthnOptionsResponse,
    WebAuthnRegisterVerifyRequest,
    WebAuthnRenameRequest,
)
from src.domains.auth.webauthn_service import WebAuthnService
from src.domains.users.models import User
from src.infrastructure.observability.metrics import auth_attempts_total, user_logins_total

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth/webauthn", tags=["Authentication"])

rate_limit_webauthn_auth = create_auth_rate_limiter(
    action="webauthn_auth",
    max_calls=RATE_LIMIT_WEBAUTHN_AUTH_PER_MINUTE,
)
rate_limit_webauthn_enroll = create_user_rate_limiter(
    action="webauthn_enroll",
    max_calls=RATE_LIMIT_WEBAUTHN_ENROLL_PER_MINUTE,
)


@router.post(
    "/register/options",
    response_model=WebAuthnOptionsResponse,
    summary="Start passkey enrollment",
    description="Issue WebAuthn registration options (discoverable credential, "
    "user verification required). Challenge is single-use, short-lived.",
)
async def register_options(
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_webauthn_enroll),
) -> WebAuthnOptionsResponse:
    """Issue registration ceremony options for the authenticated user."""
    service = WebAuthnService(db)
    options_json = await service.generate_registration_options(user)
    return WebAuthnOptionsResponse(options=options_json)


@router.post(
    "/register/verify",
    response_model=WebAuthnCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Complete passkey enrollment",
    description="Verify the registration ceremony result and persist the passkey.",
)
async def register_verify(
    data: WebAuthnRegisterVerifyRequest,
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_webauthn_enroll),
) -> WebAuthnCredentialResponse:
    """Verify and persist a new passkey for the authenticated user."""
    service = WebAuthnService(db)
    row = await service.verify_registration(user, data.credential, data.label)
    return WebAuthnCredentialResponse.model_validate(row)


@router.get(
    "/credentials",
    response_model=list[WebAuthnCredentialResponse],
    summary="List registered passkeys",
    description="List the authenticated user's passkeys (no key material exposed).",
)
async def list_credentials(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[WebAuthnCredentialResponse]:
    """List the user's registered passkeys."""
    service = WebAuthnService(db)
    rows = await service.list_credentials(user)
    return [WebAuthnCredentialResponse.model_validate(row) for row in rows]


@router.patch(
    "/credentials/{row_id}",
    response_model=WebAuthnCredentialResponse,
    summary="Rename a passkey",
    description="Update the display label of an owned passkey.",
)
async def rename_credential(
    row_id: UUID,
    data: WebAuthnRenameRequest,
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_webauthn_enroll),
) -> WebAuthnCredentialResponse:
    """Rename an owned passkey (404 hides existence of others' credentials)."""
    service = WebAuthnService(db)
    row = await service.rename_credential(user, row_id, data.label)
    return WebAuthnCredentialResponse.model_validate(row)


@router.delete(
    "/credentials/{row_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a passkey",
    description="Delete an owned passkey. The authenticator-side entry must be "
    "removed by the user on the device itself.",
)
async def delete_credential(
    row_id: UUID,
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_webauthn_enroll),
) -> None:
    """Revoke an owned passkey (404 hides existence of others' credentials)."""
    service = WebAuthnService(db)
    await service.delete_credential(user, row_id)


@router.post(
    "/authenticate/options",
    response_model=WebAuthnAuthOptionsResponse,
    summary="Start passkey login",
    description="Issue anonymous WebAuthn authentication options (discoverable "
    "credentials — no account information leaks).",
)
async def authenticate_options(
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_webauthn_auth),
) -> WebAuthnAuthOptionsResponse:
    """Issue an anonymous authentication ceremony challenge."""
    service = WebAuthnService(db)
    challenge_id, options_json = await service.generate_authentication_options()
    return WebAuthnAuthOptionsResponse(challenge_id=challenge_id, options=options_json)


@router.post(
    "/authenticate/verify",
    response_model=AuthResponseBFF,
    summary="Complete passkey login (BFF Pattern)",
    description="Verify the authentication ceremony and create the session "
    "(HTTP-only cookie, no tokens exposed).",
)
async def authenticate_verify(
    data: WebAuthnAuthenticateVerifyRequest,
    response: Response,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_webauthn_auth),
) -> AuthResponseBFF:
    """Complete a passkey login and set the BFF session cookie."""
    service = WebAuthnService(db)
    try:
        user = await service.verify_authentication(data.challenge_id, data.credential)
    except Exception:
        auth_attempts_total.labels(method="webauthn", status="error").inc()
        user_logins_total.labels(provider="passkey", status="error").inc()
        raise

    await create_authenticated_session_with_cookie(
        response=response,
        user_id=str(user.id),
        remember_me=False,
        event_name="user_logged_in_webauthn",
        extra_context={"email": user.email},
        auth_methods=["passkey"],
        request=http_request,
    )

    auth_attempts_total.labels(method="webauthn", status="success").inc()
    user_logins_total.labels(provider="passkey", status="success").inc()

    return AuthResponseBFF(
        user=UserResponse.model_validate(user),
        message=APIMessages.login_successful(),
    )
