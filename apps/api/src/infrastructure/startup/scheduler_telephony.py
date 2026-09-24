"""Scheduler registration of the telephony reapers (agentic calls — spec P4.3).

Extracted from ``startup/schedulers.py`` (frozen at its size cap): the startup
step stays the single ORDERING point and calls :func:`register_telephony_jobs`
under the ``telephony_enabled`` flag; this module owns only the four jobs.

- stale-call reaper (interval): frees phantom in-flight calls with no webhook;
- notification reaper (interval): re-dispatches return notifications a crash
  left PENDING (T1 durability);
- return reaper (interval): replays return syntheses a crash stranded;
- retention reaper (daily cron): clears summary/structured_data past TTL (D-8).

The interval jobs carry a jitter proportional to their period (shared-divisor
alignment, ADR-254). The jitter guard scans this module as well as the step.
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.core.constants import (
    SCHEDULER_JOB_TELEPHONY_NOTIFICATION_REAPER,
    SCHEDULER_JOB_TELEPHONY_RETENTION_REAPER,
    SCHEDULER_JOB_TELEPHONY_RETURN_REAPER,
    SCHEDULER_JOB_TELEPHONY_STALE_REAPER,
)
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for

logger = structlog.get_logger(__name__)


def register_telephony_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the four telephony reapers on ``scheduler``.

    Args:
        scheduler: The application scheduler, before the leader elector starts.
    """
    from src.domains.telephony.reapers import (
        telephony_notification_reaper,
        telephony_retention_reaper,
        telephony_return_reaper,
        telephony_stale_call_reaper,
    )

    scheduler.add_job(
        telephony_stale_call_reaper,
        trigger="interval",
        minutes=settings.telephony_stale_reaper_interval_minutes,
        jitter=jitter_seconds_for(minutes=settings.telephony_stale_reaper_interval_minutes),
        id=SCHEDULER_JOB_TELEPHONY_STALE_REAPER,
        name="Telephony stale-call recovery",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        telephony_notification_reaper,
        trigger="interval",
        minutes=settings.telephony_notification_reaper_interval_minutes,
        jitter=jitter_seconds_for(minutes=settings.telephony_notification_reaper_interval_minutes),
        id=SCHEDULER_JOB_TELEPHONY_NOTIFICATION_REAPER,
        name="Telephony return-notification recovery",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        telephony_return_reaper,
        trigger="interval",
        minutes=settings.telephony_return_reaper_interval_minutes,
        jitter=jitter_seconds_for(minutes=settings.telephony_return_reaper_interval_minutes),
        id=SCHEDULER_JOB_TELEPHONY_RETURN_REAPER,
        name="Telephony pre-synthesis return recovery",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        telephony_retention_reaper,
        trigger="cron",
        hour=4,
        minute=30,
        id=SCHEDULER_JOB_TELEPHONY_RETENTION_REAPER,
        name="Telephony call retention purge",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=600,
    )
    logger.info(
        "telephony_reapers_scheduled",
        stale_interval_minutes=settings.telephony_stale_reaper_interval_minutes,
        notification_interval_minutes=settings.telephony_notification_reaper_interval_minutes,
    )
