"""TOTP second-factor endpoints (security program D1, Lot 2).

Mounted only when ``MFA_ENABLED`` is true (see ``api/v1/routes.py``).
Management endpoints are rate-limited per authenticated user; the anonymous
second login step is strictly IP-rate-limited (code brute force).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    RATE_LIMIT_MFA_VERIFY_PER_MINUTE,
    RATE_LIMIT_TOTP_MANAGE_PER_MINUTE,
)
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_credentials
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
from src.domains.auth.login_notification import notify_new_login_if_unknown
from src.domains.auth.schemas import (
    AuthResponseBFF,
    MFAVerifyRequest,
    TOTPBackupCodesResponse,
    TOTPConfirmRequest,
    TOTPEnrollResponse,
    TOTPStatusResponse,
    UserResponse,
)
from src.domains.auth.totp_service import TOTPService
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.infrastructure.observability.metrics import auth_attempts_total, user_logins_total

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

rate_limit_mfa_verify = create_auth_rate_limiter(
    action="mfa_verify",
    max_calls=RATE_LIMIT_MFA_VERIFY_PER_MINUTE,
)
rate_limit_totp_manage = create_user_rate_limiter(
    action="totp_manage",
    max_calls=RATE_LIMIT_TOTP_MANAGE_PER_MINUTE,
)


@router.post(
    "/totp/enroll",
    response_model=TOTPEnrollResponse,
    summary="Start TOTP enrollment",
    description="Generate a fresh TOTP secret. Secret and QR are revealed exactly once; "
    "confirm with a first code to activate.",
)
async def totp_enroll(
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_totp_manage),
) -> TOTPEnrollResponse:
    """Start a TOTP enrollment draft for the authenticated user."""
    service = TOTPService(db)
    secret, uri, qr_data_uri = await service.enroll(user)
    return TOTPEnrollResponse(secret=secret, otpauth_uri=uri, qr_data_uri=qr_data_uri)


@router.post(
    "/totp/confirm",
    response_model=TOTPBackupCodesResponse,
    summary="Confirm TOTP enrollment",
    description="Prove authenticator possession with a first valid code. Returns the "
    "10 single-use backup codes — shown exactly once.",
)
async def totp_confirm(
    data: TOTPConfirmRequest,
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_totp_manage),
) -> TOTPBackupCodesResponse:
    """Activate TOTP and reveal the backup codes once."""
    service = TOTPService(db)
    codes = await service.confirm(user, data.code)
    return TOTPBackupCodesResponse(
        backup_codes=codes,
        message=APIMessages.backup_codes_generated(),
    )


@router.get(
    "/totp/status",
    response_model=TOTPStatusResponse,
    summary="TOTP status",
    description="Whether TOTP is active for the current user, and how many backup codes remain.",
)
async def totp_status(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TOTPStatusResponse:
    """Report the user's TOTP state."""
    service = TOTPService(db)
    totp_state = await service.get_status(user)
    return TOTPStatusResponse(
        active=totp_state.active,
        confirmed_at=totp_state.confirmed_at,
        backup_codes_remaining=totp_state.backup_codes_remaining,
    )


@router.delete(
    "/totp",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable TOTP",
    description="Disable TOTP and invalidate every backup code.",
)
async def totp_disable(
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_totp_manage),
) -> None:
    """Disable the second factor for the authenticated user."""
    service = TOTPService(db)
    await service.disable(user)


@router.post(
    "/totp/backup-codes/regenerate",
    response_model=TOTPBackupCodesResponse,
    summary="Regenerate backup codes",
    description="Invalidate every backup code and issue a fresh set — shown exactly once.",
)
async def totp_regenerate_backup_codes(
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_totp_manage),
) -> TOTPBackupCodesResponse:
    """Issue a fresh backup code set (old set invalidated)."""
    service = TOTPService(db)
    codes = await service.regenerate_backup_codes(user)
    return TOTPBackupCodesResponse(
        backup_codes=codes,
        message=APIMessages.backup_codes_generated(),
    )


@router.post(
    "/mfa/verify",
    response_model=AuthResponseBFF,
    summary="Complete a two-step login (BFF Pattern)",
    description="Second login step: present the pending token from /auth/login plus a "
    "TOTP or backup code. Creates the session (HTTP-only cookie).",
)
async def mfa_verify(
    data: MFAVerifyRequest,
    response: Response,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_mfa_verify),
) -> AuthResponseBFF:
    """Verify the second factor and create the BFF session."""
    service = TOTPService(db)

    pending = await service.consume_pending_token(data.mfa_token)
    if pending is None:
        auth_attempts_total.labels(method="mfa_verify", status="error").inc()
        raise_invalid_credentials()

    pending_user_id = uuid.UUID(pending.user_id)
    try:
        await service.verify_for_login(pending_user_id, data.code)
    except Exception:
        auth_attempts_total.labels(method="mfa_verify", status="error").inc()
        user_logins_total.labels(provider="password_totp", status="error").inc()
        raise

    user = await UserRepository(db).get_user_minimal_for_session(pending_user_id)
    if user is None or not user.is_active:
        auth_attempts_total.labels(method="mfa_verify", status="error").inc()
        raise_invalid_credentials()

    await create_authenticated_session_with_cookie(
        response=response,
        user_id=pending.user_id,
        remember_me=pending.remember_me,
        event_name="user_logged_in_totp",
        extra_context={"email": user.email},
        auth_methods=["password", "totp"],
        request=http_request,
        fcm_token_id=pending.fcm_token_id,
    )

    auth_attempts_total.labels(method="mfa_verify", status="success").inc()
    user_logins_total.labels(provider="password_totp", status="success").inc()

    # A4: the attestation outcome was computed at step one.
    await notify_new_login_if_unknown(db, user, pending.known_device)

    return AuthResponseBFF(
        user=UserResponse.model_validate(user),
        message=APIMessages.login_successful(),
    )
