"""Proactive admin notifications for critical incidents (superusers only).

Doctrine (spec 2026-08-27, pillar 6): in-app + push (+ bound channels) via the
existing proactive dispatcher; NO email (Alertmanager already emails — a
duplicate would be noise). Cooldown per correlation key via one atomic
``SET NX EX`` (never SET NX + separate EXPIRE), fail-OPEN: losing Redis must
not silence critical notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import REDIS_KEY_DIAGNOSTICS_NOTIFY_PREFIX
from src.core.i18n_diagnostics import get_incident_notification
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.proactive.notification import NotificationDispatcher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: task_type used in the dispatcher's proactive metadata.
DIAGNOSTICS_TASK_TYPE = "diagnostics"


async def _active_superusers(db: AsyncSession) -> list[Any]:
    """Active superusers — the only audience of diagnostics notifications.

    Args:
        db: Caller's session.

    Returns:
        Active superuser rows.
    """
    from src.domains.users.models import User

    result = await db.execute(
        select(User).where(User.is_superuser.is_(True), User.is_active.is_(True))
    )
    return list(result.scalars().all())


async def _cooldown_acquired(correlation_key: str) -> bool:
    """Try to acquire the per-key notification cooldown (atomic NX + TTL).

    Fail-open: a Redis failure returns True — losing the cooldown store must
    not silence critical notifications (worst case: one duplicate).

    Args:
        correlation_key: Incident correlation key.

    Returns:
        True when this caller may notify now.
    """
    try:
        redis = await get_redis_cache()
        acquired = await redis.set(
            f"{REDIS_KEY_DIAGNOSTICS_NOTIFY_PREFIX}{correlation_key}",
            "1",
            nx=True,
            ex=settings.diagnostics_notification_cooldown_seconds,
        )
        return bool(acquired)
    except Exception as exc:
        logger.warning("diagnostics_notify_cooldown_unavailable", error=str(exc))
        return True


async def notify_admins_of_incident(
    *,
    incident_id: UUID,
    correlation_key: str,
    severity: str,
    title: str,
    db: AsyncSession,
) -> int:
    """Notify every active superuser about a newly opened incident.

    Args:
        incident_id: The incident row id (notification target id).
        correlation_key: Deduplication identity (cooldown key).
        severity: 'critical' or 'warning'.
        title: Incident human title.
        db: Caller's session (the caller owns the transaction).

    Returns:
        Number of superusers notified (0 when the cooldown is active).
    """
    if not await _cooldown_acquired(correlation_key):
        logger.debug("diagnostics_notify_cooldown_active", correlation_key=correlation_key)
        return 0

    admins = await _active_superusers(db)
    if not admins:
        return 0

    dispatcher = NotificationDispatcher()
    sent = 0
    for admin in admins:
        notif_title, body = get_incident_notification(
            getattr(admin, "language", None), severity=severity, title=title
        )
        try:
            await dispatcher.dispatch(
                user=admin,
                content=body,
                task_type=DIAGNOSTICS_TASK_TYPE,
                target_id=str(incident_id),
                metadata={"severity": severity, "correlation_key": correlation_key},
                db=db,
                title=notif_title,
            )
            sent += 1
        except Exception:
            # One admin's broken channel must not starve the others.
            logger.exception("diagnostics_notify_dispatch_failed", user_id=str(admin.id))

    if sent:
        await DiagnosticsRepository(db).mark_notified(incident_id)
    logger.info(
        "diagnostics_admins_notified",
        correlation_key=correlation_key,
        severity=severity,
        notified=sent,
    )
    return sent
