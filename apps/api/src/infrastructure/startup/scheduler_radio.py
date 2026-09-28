"""Startup step: the personal radio's two background jobs (ADR-324).

A separate module because ``schedulers.py`` is frozen at its audited size; the
startup step stays the single ORDERING point and calls
:func:`register_radio_jobs`. Both jobs exist only where the deployment ships
the radio (``RADIO_ENABLED``); the operator's switch is read by the newsroom
pass at every tick (``domains/radio/jobs.py``), never here.

- the NEWSROOM pass reads the shipped catalogue and the listeners' own sites;
- the MEDIA sweep removes the session directories a crash left behind.

Both carry a jitter proportional to their period (ADR-254), and neither takes a
``SchedulerLock``: they run on the leader alone, one at a time, and the jobs
module states why a handover needs no more.
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_RADIO_MEDIA_SWEEP, SCHEDULER_JOB_RADIO_NEWSROOM_COLLECT
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for

logger = structlog.get_logger(__name__)


def register_radio_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the newsroom pass and the media sweep on ``scheduler``.

    Args:
        scheduler: The application scheduler, before the leader elector starts.
    """
    if not settings.radio_enabled:
        return

    from src.domains.radio.jobs import run_newsroom_pass, sweep_radio_media

    newsroom_interval = settings.radio_newsroom_interval_seconds
    scheduler.add_job(
        run_newsroom_pass,
        trigger="interval",
        seconds=newsroom_interval,
        jitter=jitter_seconds_for(seconds=newsroom_interval),
        id=SCHEDULER_JOB_RADIO_NEWSROOM_COLLECT,
        name="Radio newsroom pass",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    sweep_interval = settings.radio_media_sweep_interval_seconds
    scheduler.add_job(
        sweep_radio_media,
        trigger="interval",
        seconds=sweep_interval,
        jitter=jitter_seconds_for(seconds=sweep_interval),
        id=SCHEDULER_JOB_RADIO_MEDIA_SWEEP,
        name="Radio media orphan sweep",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    logger.info(
        "radio_jobs_scheduled",
        newsroom_interval_seconds=newsroom_interval,
        media_sweep_interval_seconds=sweep_interval,
    )


__all__ = ["register_radio_jobs"]
