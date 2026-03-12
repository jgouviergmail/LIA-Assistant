"""
Scheduled task for proactive interest notifications.

Runs every 15 minutes to send interest-based notifications to eligible users.
Uses the ProactiveTaskRunner infrastructure for:
- Batch processing
- Eligibility checking
- Content generation
- Notification dispatch
- Token tracking

NOTE: Uses SchedulerLock to prevent duplicate execution with multiple uvicorn workers.
Each worker's APScheduler triggers this job, but only one acquires the lock and executes.

References:
    - Pattern: reminder_notification.py
"""

from typing import Any

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_INTEREST_NOTIFICATION
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.interests.models import InterestNotification
from src.domains.interests.proactive_task import InterestProactiveTask
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.proactive.eligibility import EligibilityChecker
from src.infrastructure.proactive.runner import execute_proactive_task

logger = get_logger(__name__)


def _create_interest_eligibility_checker() -> EligibilityChecker:
    """
    Create eligibility checker for interest notifications.

    Uses settings from User model:
    - interests_enabled: Feature toggle
    - interests_notify_start_hour: Start of notification window
    - interests_notify_end_hour: End of notification window
    - interests_notify_min_per_day: Minimum notifications per day
    - interests_notify_max_per_day: Maximum notifications per day

    Returns:
        Configured EligibilityChecker instance
    """
    return EligibilityChecker(
        task_type="interest",
        enabled_field="interests_enabled",
        start_hour_field="interests_notify_start_hour",
        end_hour_field="interests_notify_end_hour",
        min_per_day_field="interests_notify_min_per_day",
        max_per_day_field="interests_notify_max_per_day",
        notification_model=InterestNotification,
        global_cooldown_hours=settings.interest_global_cooldown_hours,
        activity_cooldown_minutes=settings.interest_activity_cooldown_minutes,
        interval_minutes=settings.interest_notification_interval_minutes,
        # Cross-type: don't fire if a heartbeat notification was sent recently
        cross_type_models=[HeartbeatNotification],
        cross_type_cooldown_minutes=settings.proactive_cross_type_cooldown_minutes,
    )


async def process_interest_notifications() -> dict[str, Any]:
    """
    Process interest notifications for all eligible users.

    This is the main entry point called by APScheduler every 15 minutes.
    Uses distributed lock to prevent duplicate execution with multiple workers.

    Flow:
    1. Acquire distributed lock (skip if another worker has it)
    2. Creates InterestProactiveTask and EligibilityChecker
    3. Executes via ProactiveTaskRunner which:
       - Fetches eligible users (batch)
       - Checks eligibility (timezone, quota, cooldowns)
       - Selects interest targets
       - Generates content
       - Dispatches notifications
       - Tracks tokens
    4. Returns execution statistics

    Returns:
        Dict with execution statistics (or skipped status if lock not acquired)

    Metrics:
        - proactive_task_processed_total{task_type="interest"}
        - proactive_task_success_total{task_type="interest"}
        - proactive_task_failed_total{task_type="interest"}
        - proactive_task_skipped_total{task_type="interest"}
        - background_job_duration_seconds{job_name="proactive_interest"}
    """
    # Acquire distributed lock to prevent duplicate execution across workers
    redis = await get_redis_cache()
    async with SchedulerLock(redis, SCHEDULER_JOB_INTEREST_NOTIFICATION) as lock:
        if not lock.acquired:
            # Another worker is executing this job - skip silently
            logger.debug(
                "interest_notification_job_skipped_lock_busy",
                job_id=SCHEDULER_JOB_INTEREST_NOTIFICATION,
            )
            return {"status": "skipped", "reason": "lock_busy"}

        logger.info(
            "interest_notification_job_started",
            interval_minutes=settings.interest_notification_interval_minutes,
        )

        try:
            task = InterestProactiveTask()
            eligibility_checker = _create_interest_eligibility_checker()

            stats = await execute_proactive_task(
                task=task,
                eligibility_checker=eligibility_checker,
                batch_size=settings.interest_notification_batch_size,
            )

            logger.info(
                "interest_notification_job_completed",
                **stats.to_dict(),
            )

            return stats.to_dict()

        except Exception as e:
            logger.error(
                "interest_notification_job_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise
