"""
Scheduled task for proactive heartbeat notifications.

Runs every 30 minutes (configurable) to send heartbeat notifications to eligible users.
Uses the ProactiveTaskRunner infrastructure for:
- Batch processing
- Eligibility checking
- Context aggregation + LLM decision
- Message generation
- Notification dispatch
- Token tracking

NOTE: Uses SchedulerLock to prevent duplicate execution with multiple uvicorn workers.
Only registered if HEARTBEAT_ENABLED=true in .env (feature flag pattern).
"""

from typing import Any

from src.core.config import settings
from src.core.constants import (
    HEARTBEAT_MAX_PER_DAY_DEFAULT,
    HEARTBEAT_MIN_PER_DAY_DEFAULT,
    HEARTBEAT_NOTIFY_END_HOUR_DEFAULT,
    HEARTBEAT_NOTIFY_START_HOUR_DEFAULT,
    SCHEDULER_JOB_HEARTBEAT_NOTIFICATION,
)
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
from src.domains.interests.models import InterestNotification
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.proactive.eligibility import EligibilityChecker
from src.infrastructure.proactive.runner import execute_proactive_task

logger = get_logger(__name__)


def _create_heartbeat_eligibility_checker() -> EligibilityChecker:
    """
    Create eligibility checker for heartbeat notifications.

    Uses settings from User model:
    - heartbeat_enabled: Feature toggle (opt-in)
    - heartbeat_notify_start_hour: Dedicated notification window start
    - heartbeat_notify_end_hour: Dedicated notification window end
    - heartbeat_max_per_day: Maximum heartbeat notifications per day

    Returns:
        Configured EligibilityChecker instance
    """
    return EligibilityChecker(
        task_type="heartbeat",
        enabled_field="heartbeat_enabled",
        start_hour_field="heartbeat_notify_start_hour",
        end_hour_field="heartbeat_notify_end_hour",
        min_per_day_field="heartbeat_min_per_day",
        max_per_day_field="heartbeat_max_per_day",
        notification_model=HeartbeatNotification,
        global_cooldown_hours=settings.heartbeat_global_cooldown_hours,
        activity_cooldown_minutes=settings.heartbeat_activity_cooldown_minutes,
        interval_minutes=settings.heartbeat_notification_interval_minutes,
        # Cross-type: don't fire if an interest notification was sent recently
        cross_type_models=[InterestNotification],
        cross_type_cooldown_minutes=settings.proactive_cross_type_cooldown_minutes,
        default_start_hour=HEARTBEAT_NOTIFY_START_HOUR_DEFAULT,
        default_end_hour=HEARTBEAT_NOTIFY_END_HOUR_DEFAULT,
        default_min_per_day=HEARTBEAT_MIN_PER_DAY_DEFAULT,
        default_max_per_day=HEARTBEAT_MAX_PER_DAY_DEFAULT,
    )


async def process_heartbeat_notifications() -> dict[str, Any]:
    """
    Process heartbeat notifications for all eligible users.

    This is the main entry point called by APScheduler every 30 minutes.
    Uses distributed lock to prevent duplicate execution with multiple workers.

    Flow:
    1. Acquire distributed lock (skip if another worker has it)
    2. Creates HeartbeatProactiveTask and EligibilityChecker
    3. Executes via ProactiveTaskRunner which:
       - Fetches eligible users (batch)
       - Checks eligibility (timezone, quota, cooldowns)
       - Aggregates context (calendar, weather, interests, memories)
       - LLM decision (skip or notify)
       - Generates personalized message
       - Dispatches notifications
       - Tracks tokens
    4. Returns execution statistics

    Returns:
        Dict with execution statistics (or skipped status if lock not acquired)
    """
    redis = await get_redis_cache()
    async with SchedulerLock(redis, SCHEDULER_JOB_HEARTBEAT_NOTIFICATION) as lock:
        if not lock.acquired:
            logger.debug(
                "heartbeat_notification_job_skipped_lock_busy",
                job_id=SCHEDULER_JOB_HEARTBEAT_NOTIFICATION,
            )
            return {"status": "skipped", "reason": "lock_busy"}

        logger.info(
            "heartbeat_notification_job_started",
            interval_minutes=settings.heartbeat_notification_interval_minutes,
        )

        try:
            task = HeartbeatProactiveTask()
            eligibility_checker = _create_heartbeat_eligibility_checker()

            stats = await execute_proactive_task(
                task=task,
                eligibility_checker=eligibility_checker,
                batch_size=settings.heartbeat_notification_batch_size,
            )

            logger.info(
                "heartbeat_notification_job_completed",
                **stats.to_dict(),
            )

            return stats.to_dict()

        except Exception as e:
            logger.error(
                "heartbeat_notification_job_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise
