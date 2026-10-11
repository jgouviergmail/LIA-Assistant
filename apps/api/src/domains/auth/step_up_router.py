"""Step-up re-authentication + password disabling (security program D1, Lot 3).

Mounted UNCONDITIONALLY: password re-verification must work even when
``MFA_ENABLED`` is false (Lot 5 exports require step-up regardless). The
passkey/TOTP verification paths simply fail with 400 when the account has
no such factor. Password disabling (arbitration A8) requires ≥ 2 active
passkeys and a fresh step-up.
"""

from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Cookie, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import RATE_LIMIT_STEP_UP_PER_MINUTE
from src.core.dependencies import get_db
from src.core.exceptions import (
    raise_invalid_credentials,
    raise_invalid_input,
    raise_step_up_required,
)
from src.core.security import verify_password
from src.core.session_dependencies import (
    get_current_active_session,
    get_session_store,
    require_recent_step_up,
)
from src.core.session_freshness import step_up_valid_until
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.auth.schemas import (
    StepUpPasswordRequest,
    StepUpStatusResponse,
    StepUpTotpRequest,
    StepUpVerifiedResponse,
    StepUpWebAuthnVerifyRequest,
    WebAuthnOptionsResponse,
)
from src.domains.auth.totp_service import TOTPService
from src.domains.auth.webauthn_service import WebAuthnService
from src.domains.users.models import User
from src.infrastructure.cache.session_store import SessionStore

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

rate_limit_step_up = create_user_rate_limiter(
    action="step_up",
    max_calls=RATE_LIMIT_STEP_UP_PER_MINUTE,
)


async def _record_step_up(session_id: str, store: SessionStore) -> StepUpVerifiedResponse:
    """Mark the session stepped-up and return the freshness horizon."""
    started = datetime.now(UTC)
    if not await store.mark_step_up(session_id):
        raise_step_up_required()
    return StepUpVerifiedResponse(
        step_up_valid_until=started + timedelta(seconds=settings.step_up_window_seconds)
    )


@router.get(
    "/step-up/status",
    response_model=StepUpStatusResponse,
    summary="Step-up methods and freshness",
    description="Which re-authentication methods this account can use, and until when "
    "the current session's step-up (if any) stays fresh.",
)
async def step_up_status(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    store: SessionStore = Depends(get_session_store),
    lia_session: str | None = Cookie(default=None),
) -> StepUpStatusResponse:
    """Report available step-up methods for the Security UI."""
    from src.domains.auth.security_queries import methods_for_account

    password_set = user.hashed_password is not None
    has_passkeys, has_totp = False, False
    if settings.mfa_enabled:
        webauthn_service = WebAuthnService(db)
        has_passkeys = bool(await webauthn_service.list_credentials(user))
        totp_service = TOTPService(db)
        has_totp = await totp_service.has_confirmed_totp(user.id)
    methods = methods_for_account(user, has_passkeys=has_passkeys, has_totp=has_totp)

    valid_until: datetime | None = None
    if lia_session:
        session = await store.get_session(lia_session)
        if session and session.user_id == str(user.id):
            valid_until = step_up_valid_until(
                session.step_up_at, datetime.now(UTC), settings.step_up_window_seconds
            )

    return StepUpStatusResponse(
        methods=methods,
        password_set=password_set,
        step_up_valid_until=valid_until,
    )


@router.post(
    "/step-up/password",
    response_model=StepUpVerifiedResponse,
    summary="Step-up with the account password",
)
async def step_up_password(
    data: StepUpPasswordRequest,
    user: User = Depends(get_current_active_session),
    store: SessionStore = Depends(get_session_store),
    lia_session: str = Cookie(),
    _rate_limit: None = Depends(rate_limit_step_up),
) -> StepUpVerifiedResponse:
    """Re-verify with the current password (401 on mismatch, no oracle)."""
    if user.hashed_password is None or not verify_password(data.password, user.hashed_password):
        logger.warning("step_up_password_rejected", user_id=str(user.id))
        raise_invalid_credentials()

    logger.info("step_up_verified", user_id=str(user.id), method="password")
    return await _record_step_up(lia_session, store)


@router.post(
    "/step-up/totp",
    response_model=StepUpVerifiedResponse,
    summary="Step-up with a TOTP or backup code",
)
async def step_up_totp(
    data: StepUpTotpRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    store: SessionStore = Depends(get_session_store),
    lia_session: str = Cookie(),
    _rate_limit: None = Depends(rate_limit_step_up),
) -> StepUpVerifiedResponse:
    """Re-verify with the TOTP second factor."""
    service = TOTPService(db)
    await service.verify_for_login(user.id, data.code)

    logger.info("step_up_verified", user_id=str(user.id), method="totp")
    return await _record_step_up(lia_session, store)


@router.post(
    "/step-up/webauthn/options",
    response_model=WebAuthnOptionsResponse,
    summary="Start a step-up passkey ceremony",
)
async def step_up_webauthn_options(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_step_up),
) -> WebAuthnOptionsResponse:
    """Issue an allow-listed assertion challenge for the user's passkeys."""
    service = WebAuthnService(db)
    options_json = await service.generate_stepup_options(user)
    return WebAuthnOptionsResponse(options=options_json)


@router.post(
    "/step-up/webauthn/verify",
    response_model=StepUpVerifiedResponse,
    summary="Complete a step-up passkey ceremony",
)
async def step_up_webauthn_verify(
    data: StepUpWebAuthnVerifyRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    store: SessionStore = Depends(get_session_store),
    lia_session: str = Cookie(),
    _rate_limit: None = Depends(rate_limit_step_up),
) -> StepUpVerifiedResponse:
    """Verify the passkey assertion (ownership enforced by the service)."""
    service = WebAuthnService(db)
    await service.verify_stepup(user, data.credential)

    logger.info("step_up_verified", user_id=str(user.id), method="passkey")
    return await _record_step_up(lia_session, store)


@router.post(
    "/password/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable password sign-in (A8 guards)",
    description="Explicitly disable password sign-in. Requires a fresh step-up AND at "
    "least 2 active passkeys. Email password-reset remains available as the "
    "documented escape hatch.",
)
async def disable_password(
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_step_up),
) -> None:
    """Disable password sign-in under the A8 guard rail."""
    if user.hashed_password is None:
        raise_invalid_input("Password sign-in is already disabled")

    if not settings.mfa_enabled:
        raise_invalid_input("Passkeys are not enabled on this instance")

    webauthn_service = WebAuthnService(db)
    passkeys = await webauthn_service.list_credentials(user)
    if len(passkeys) < 2:
        raise_invalid_input(
            "Disabling the password requires at least 2 active passkeys "
            "(resilience to losing one device)"
        )

    user.hashed_password = None
    db.add(user)
    await db.commit()

    logger.warning(
        "password_sign_in_disabled",
        user_id=str(user.id),
        passkeys_count=len(passkeys),
    )
