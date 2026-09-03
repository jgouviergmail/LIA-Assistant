"""Scheduler registration of the meetings reapers (ADR-258).

Extracted from ``startup/schedulers.py`` (frozen at its size cap): the startup
step stays the single ORDERING point and calls :func:`register_meetings_jobs`
under the ``meetings_enabled`` flag; this module owns only the two jobs.

- ``meetings_job_reaper`` — stale recordings → ``interrupted``, expired
  processing leases → ``stopped``, orphaned stopped meetings re-driven;
- ``meetings_audio_retention_reaper`` — kept audio purged past its retention.

Both carry a jitter proportional to their period (shared-divisor alignment,
ADR-254). The jitter guard scans this module as well as the startup step.
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_MEETINGS_REAPER, SCHEDULER_JOB_MEETINGS_RETENTION
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for

logger = structlog.get_logger(__name__)


def register_meetings_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the two meetings reapers on ``scheduler``.

    Args:
        scheduler: The application scheduler, before the leader elector starts.
    """
    from src.domains.meetings.reapers import (
        meetings_audio_retention_reaper,
        meetings_job_reaper,
    )

    scheduler.add_job(
        meetings_job_reaper,
        trigger="interval",
        seconds=settings.meetings_reaper_interval_seconds,
        jitter=jitter_seconds_for(seconds=settings.meetings_reaper_interval_seconds),
        id=SCHEDULER_JOB_MEETINGS_REAPER,
        name="Meetings recording/job recovery",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        meetings_audio_retention_reaper,
        trigger="interval",
        minutes=settings.meetings_retention_reaper_interval_minutes,
        jitter=jitter_seconds_for(minutes=settings.meetings_retention_reaper_interval_minutes),
        id=SCHEDULER_JOB_MEETINGS_RETENTION,
        name="Meetings audio retention purge",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    logger.info(
        "meetings_reapers_scheduled",
        interval_seconds=settings.meetings_reaper_interval_seconds,
        retention_interval_minutes=settings.meetings_retention_reaper_interval_minutes,
    )
