"""
Scheduled task for proactive OAuth token health check notifications.

SIMPLIFIED DESIGN:
- Only notifies on status=ERROR (refresh failed, needs manual re-auth)
- Does NOT notify on normal token expiration (proactive refresh handles that)
- Sends push notifications to offline users so they know to reconnect

Why this design:
- Proactive refresh job runs every 15 min, refreshes tokens 30 min before expiry
- access_token.expires_at in the past is NORMAL - on-demand refresh gets new token
- Only status=ERROR indicates a real problem (refresh token revoked/expired)

Configuration (via .env):
    OAUTH_HEALTH_CHECK_ENABLED=true
    OAUTH_HEALTH_CHECK_INTERVAL_MINUTES=5
    OAUTH_HEALTH_CRITICAL_COOLDOWN_HOURS=24

Notification Flow:
    1. Check if connector has status=ERROR
    2. Check if user has active SSE connection (Redis key)
    3. If NO SSE: Send FCM push notification
    4. Always publish to Redis channel (frontend shows modal if connected)
    5. Anti-spam: Use Redis cooldown keys to avoid re-notifying

NOTE: Uses SchedulerLock to prevent duplicate execution with multiple uvicorn workers.
Each worker's APScheduler triggers this job, but only one acquires the lock and executes.

Metrics:
    - background_job_duration_seconds{job_name="oauth_health_check"}
    - background_job_errors_total{job_name="oauth_health_check"}
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, cast

import structlog

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.connectors.models import Connector

from src.core.config import settings
from src.core.constants import (
    OAUTH_HEALTH_NOTIFIED_KEY_PREFIX,
    SCHEDULER_JOB_OAUTH_HEALTH,
    SSE_CONNECTION_KEY_PREFIX,
)
from src.core.i18n_api_messages import APIMessages, SupportedLanguage
from src.domains.connectors.models import (
    ConnectorStatus,
    get_connector_authorize_path,
    get_connector_display_name,
)
from src.domains.connectors.repository import ConnectorRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)

# Job name for metrics (matches SCHEDULER_JOB_OAUTH_HEALTH constant)
_JOB_NAME = SCHEDULER_JOB_OAUTH_HEALTH


async def check_oauth_health_all_users() -> dict[str, Any]:
    """
    Check OAuth connector health for all users and send notifications.

    SIMPLIFIED: Only notifies on status=ERROR (refresh failed).
    Normal token expiration is handled by proactive refresh job.

    Uses distributed lock to prevent duplicate execution with multiple workers.

    Configuration:
        - settings.oauth_health_critical_cooldown_hours: Cooldown before re-notifying

    Metrics:
        - background_job_duration_seconds{job_name="oauth_health_check"}
        - background_job_errors_total{job_name="oauth_health_check"}

    Returns:
        Stats dict with checked, healthy, error, notified counts,
        or {"status": "skipped", "reason": "lock_busy"} if another worker is executing.
    """
    # Acquire distributed lock to prevent duplicate execution across workers
    redis = await get_redis_cache()
    if not redis:
        logger.warning("oauth_health_check_redis_unavailable")
        return {"checked": 0, "healthy": 0, "error": 0, "notified": 0}

    async with SchedulerLock(redis, SCHEDULER_JOB_OAUTH_HEALTH) as lock:
        if not lock.acquired:
            # Another worker is executing this job - skip silently
            logger.debug(
                "oauth_health_check_skipped_lock_busy",
                job_id=SCHEDULER_JOB_OAUTH_HEALTH,
            )
            return {"status": "skipped", "reason": "lock_busy"}

        return await _execute_oauth_health_check(redis)


async def _execute_oauth_health_check(redis: Redis) -> dict[str, int]:
    """
    Execute the actual OAuth health check logic.

    Separated from main function to keep lock scope clean.

    Args:
        redis: Redis client (already verified available)

    Returns:
        Stats dict with checked, healthy, error, notified counts
    """
    start_time = time.perf_counter()
    stats: dict[str, int] = {
        "checked": 0,
        "healthy": 0,
        "error": 0,
        "notified": 0,
    }

    async with get_db_context() as db:
        try:
            repository = ConnectorRepository(db)
            connectors = await repository.get_oauth_connectors_for_health_check()

            if not connectors:
                logger.debug("oauth_health_check_no_connectors")
                _record_duration(start_time)
                return stats

            logger.info(
                "oauth_health_check_starting",
                total_connectors=len(connectors),
            )

            for connector in connectors:
                stats["checked"] += 1

                # SIMPLIFIED: Only check for ERROR status
                if connector.status == ConnectorStatus.ERROR:
                    stats["error"] += 1
                    # Try to notify
                    notified = await _maybe_notify(
                        connector=connector,
                        redis=redis,
                        db=db,
                    )
                    if notified:
                        stats["notified"] += 1
                else:
                    stats["healthy"] += 1

            # Commit any pending changes
            await db.commit()

            # Record metrics and log completion
            duration = _record_duration(start_time)
            logger.info(
                "oauth_health_check_completed",
                **stats,
                duration_seconds=round(duration, 3),
            )

            return stats

        except Exception as e:
            background_job_errors_total.labels(job_name=_JOB_NAME).inc()
            duration = _record_duration(start_time)

            logger.error(
                "oauth_health_check_failed",
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 3),
            )
            raise


async def _maybe_notify(
    connector: Connector,
    redis: Redis,
    db: AsyncSession,
) -> bool:
    """
    Send notification for ERROR connector if not already notified recently.

    Args:
        connector: Connector model instance with status=ERROR.
        redis: Redis client.
        db: Database session.

    Returns:
        True if notification was sent, False if skipped (already notified).
    """
    # Check cooldown Redis key
    notified_key = f"{OAUTH_HEALTH_NOTIFIED_KEY_PREFIX}:{connector.user_id}:{connector.id}"
    if await redis.exists(notified_key):
        return False  # Already notified recently

    # Get user for language preference
    from src.domains.users.repository import UserRepository

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(connector.user_id)
    if not user:
        return False

    # Get connector display name and authorize URL
    connector_name = get_connector_display_name(connector.connector_type)
    authorize_path = get_connector_authorize_path(connector.connector_type)
    authorize_url = f"/connectors{authorize_path}" if authorize_path else ""

    # Generate i18n message (only critical - ERROR status)
    # Cast to SupportedLanguage (user.language is validated at DB level)
    language = cast(SupportedLanguage, user.language or settings.default_language)
    title = APIMessages.oauth_health_critical_title(language)
    body = APIMessages.oauth_health_critical_body(connector_name, language)

    # Check if user has active SSE connection
    sse_key = f"{SSE_CONNECTION_KEY_PREFIX}:{connector.user_id}"
    has_sse = await redis.exists(sse_key)

    # Send FCM push notification only if NO SSE connection
    if not has_sse:
        try:
            from src.domains.notifications.service import FCMNotificationService

            fcm_service = FCMNotificationService(db)
            await fcm_service.send_to_user(
                user_id=connector.user_id,
                title=title,
                body=body,
                data={
                    "type": "oauth_health_critical",
                    "connector_id": str(connector.id),
                    "connector_type": connector.connector_type.value,
                    "authorize_url": authorize_url,
                },
            )
            logger.debug(
                "oauth_health_push_sent",
                user_id=str(connector.user_id),
                connector_id=str(connector.id),
            )
        except Exception as e:
            logger.warning(
                "oauth_health_push_failed",
                user_id=str(connector.user_id),
                connector_id=str(connector.id),
                error=str(e),
            )

    # Always publish to Redis for SSE (frontend will display modal)
    try:
        channel = f"user_notifications:{connector.user_id}"
        await redis.publish(
            channel,
            json.dumps(
                {
                    "type": "oauth_health_critical",
                    "title": title,
                    "content": body,
                    "connector_id": str(connector.id),
                    "connector_type": connector.connector_type.value,
                    "display_name": connector_name,
                    "authorize_url": authorize_url,
                },
                ensure_ascii=False,
            ),
        )
    except Exception as e:
        logger.warning(
            "oauth_health_sse_publish_failed",
            user_id=str(connector.user_id),
            connector_id=str(connector.id),
            error=str(e),
        )

    # Set cooldown key with TTL
    cooldown_seconds = settings.oauth_health_critical_cooldown_hours * 3600
    await redis.setex(notified_key, cooldown_seconds, "1")

    logger.info(
        "oauth_health_notification_sent",
        user_id=str(connector.user_id),
        connector_id=str(connector.id),
        connector_type=connector.connector_type.value,
        push_sent=not has_sse,
        cooldown_hours=cooldown_seconds // 3600,
    )

    return True


def _record_duration(start_time: float) -> float:
    """Record job duration metric and return elapsed time."""
    duration = time.perf_counter() - start_time
    background_job_duration_seconds.labels(job_name=_JOB_NAME).observe(duration)
    return duration
