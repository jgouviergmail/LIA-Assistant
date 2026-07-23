"""Device sessions endpoints — "My devices" (security program D2, Lot 4).

Mounted unconditionally: session visibility/revocation is core account
hygiene, independent of the MFA flag. The raw session id never reaches the
client — rows are addressed by an opaque sha256-prefix display id. Revoking
one device needs plain auth (a thief revoking devices only helps the
victim); revoking ALL OTHERS requires a fresh step-up.
"""

import structlog
from fastapi import APIRouter, Cookie, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_not_found_or_unauthorized
from src.core.session_dependencies import (
    get_current_active_session,
    get_session_store,
    require_recent_step_up,
)
from src.domains.auth.schemas import DeviceSessionResponse, RevokeOthersResponse
from src.domains.notifications.repository import FCMTokenRepository
from src.domains.users.models import User
from src.infrastructure.cache.session_store import SessionStore, UserSession
from src.infrastructure.observability.metrics_mfa import session_revocations_total

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth/sessions", tags=["Authentication"])


async def _device_names_by_token_id(db: AsyncSession, user: User) -> dict[str, str]:
    """Map FCM token row ids → device names for attested sessions (A4)."""
    repository = FCMTokenRepository(db)
    tokens = await repository.get_all_tokens_for_user(user.id)
    return {str(token.id): token.device_name for token in tokens if token.device_name}


def _to_response(
    session: UserSession,
    current_session_id: str | None,
    device_names: dict[str, str],
) -> DeviceSessionResponse:
    """Build the bounded API row for one session."""
    return DeviceSessionResponse(
        id=session.display_id,
        current=session.session_id == current_session_id,
        ua_family=session.ua_family,
        os_family=session.os_family,
        ip_trunc=session.ip_trunc,
        auth_methods=session.auth_methods,
        created_at=session.created_at,
        last_seen_at=session.last_seen_at,
        device_name=(device_names.get(session.fcm_token_id) if session.fcm_token_id else None),
    )


@router.get(
    "",
    response_model=list[DeviceSessionResponse],
    summary="List my active sessions",
    description="Every live session of the account with bounded device metadata "
    "(coarse families, truncated IP). The caller's own session is flagged.",
)
async def list_sessions(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    store: SessionStore = Depends(get_session_store),
    lia_session: str | None = Cookie(default=None),
) -> list[DeviceSessionResponse]:
    """List the user's live sessions, newest first."""
    sessions = await store.list_user_sessions(str(user.id))
    device_names = await _device_names_by_token_id(db, user)
    return [_to_response(session, lia_session, device_names) for session in sessions]


@router.delete(
    "/{display_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke one session",
    description="Sign out one device. Its next request answers 401; active SSE "
    "streams close within one keepalive tick. Detached background runs "
    "(ADR-117) continue server-side by design.",
)
async def revoke_session(
    display_id: str,
    user: User = Depends(get_current_active_session),
    store: SessionStore = Depends(get_session_store),
) -> None:
    """Revoke one of the caller's sessions by display id (404 when unknown)."""
    deleted = await store.delete_session_by_display_id(str(user.id), display_id)
    if not deleted:
        raise_not_found_or_unauthorized("session")

    session_revocations_total.labels(scope="one").inc()
    logger.info(
        "device_session_revoked",
        user_id=str(user.id),
        display_id=display_id,
    )


@router.post(
    "/revoke-others",
    response_model=RevokeOthersResponse,
    summary="Sign out every other device (step-up required)",
    description="Revoke every session except the current one. Requires a fresh "
    "step-up re-authentication.",
)
async def revoke_other_sessions(
    user: User = Depends(require_recent_step_up),
    store: SessionStore = Depends(get_session_store),
    lia_session: str = Cookie(),
) -> RevokeOthersResponse:
    """Revoke all sessions except the caller's own."""
    revoked = await store.delete_other_user_sessions(str(user.id), lia_session)

    session_revocations_total.labels(scope="others").inc()
    logger.info(
        "other_device_sessions_revoked",
        user_id=str(user.id),
        revoked=revoked,
    )
    return RevokeOthersResponse(revoked=revoked)
