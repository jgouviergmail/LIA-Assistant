"""New-login notification with FCM device attestation (D2, arbitration A4).

A device is "known" when the login request presents a valid, active FCM
token registered to the account — possession of a registered token ≈
possession of the device (a stolen password alone cannot suppress the
alert). Every failure mode (no token, rotated token, push disabled) falls
toward NOTIFYING, never toward silence. Passkey logins are known by
definition (device-bound credential) and never notify.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages
from src.domains.notifications.models import UserFCMToken
from src.domains.notifications.service import FCMNotificationService
from src.domains.users.models import User
from src.infrastructure.observability.metrics_mfa import login_notifications_total

logger = structlog.get_logger(__name__)


async def resolve_attestation(
    db: AsyncSession, user_id: uuid.UUID, fcm_token: str | None
) -> tuple[bool, str | None]:
    """Check whether the login request attests a known device.

    Args:
        db: Database session.
        user_id: Account UUID.
        fcm_token: FCM token presented by the client, if any.

    Returns:
        (known, fcm_token_row_id) — known only when the token is active and
        belongs to this account.
    """
    if not fcm_token:
        return False, None

    result = await db.execute(
        select(UserFCMToken).where(
            UserFCMToken.user_id == user_id,
            UserFCMToken.token == fcm_token,
            UserFCMToken.is_active.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False, None
    return True, str(row.id)


async def notify_new_login_if_unknown(db: AsyncSession, user: User, known: bool) -> None:
    """Fire the new-login FCM notification unless the device attested itself.

    Best-effort: a push failure is logged and counted, never raised — the
    login itself must not fail because FCM is down.

    Args:
        db: Database session.
        user: The freshly signed-in user.
        known: Whether the device attested itself (A4).
    """
    if known:
        login_notifications_total.labels(status="skipped_known").inc()
        return
    if not user.login_notifications_enabled:
        login_notifications_total.labels(status="skipped_pref").inc()
        return

    try:
        language = normalize_language(user.language)
        service = FCMNotificationService(db)
        result = await service.send_to_user(
            user_id=user.id,
            title=APIMessages.new_login_notification_title(language),
            body=APIMessages.new_login_notification_body(language),
            data={"kind": "new_login"},
        )
        login_notifications_total.labels(
            status="sent" if result.success_count > 0 else "failed"
        ).inc()
        logger.info(
            "new_login_notification_dispatched",
            user_id=str(user.id),
            sent=result.success_count,
            failed=result.failure_count,
        )
    except Exception as exc:
        login_notifications_total.labels(status="failed").inc()
        logger.warning(
            "new_login_notification_failed",
            user_id=str(user.id),
            error=str(exc),
        )
