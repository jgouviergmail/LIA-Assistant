"""Startup step: Google push jobs (lot H sync + ADR-261 wake sweep).

Extracted from ``schedulers.py`` (frozen at its audited size): same
feature-flag guards, same job ids, same jitter doctrine (ADR-254). The
jitter guard test lists this module next to ``schedulers.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from src.core.config import settings
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for

logger = structlog.get_logger(__name__)


def register_push_jobs(scheduler: Any) -> None:
    """Register the push channel sync and the push-driven wake sweep.

    Args:
        scheduler: The APScheduler instance (jobs are added before start).
    """
    # Google push channel sync (lot H): ensure/renew watch channels for
    # every active Google connector. The job body re-checks the flag, so a
    # schedule left behind by a config change stays inert.
    if getattr(settings, "push_channels_enabled", False):
        from src.core.constants import (
            PUSH_SYNC_INITIAL_DELAY_MINUTES,
            SCHEDULER_JOB_PUSH_CHANNEL_SYNC,
        )
        from src.domains.push_channels.sync import sync_push_channels

        scheduler.add_job(
            sync_push_channels,
            trigger="interval",
            minutes=settings.push_sync_interval_minutes,
            jitter=jitter_seconds_for(minutes=settings.push_sync_interval_minutes),
            # next_run_time pins the FIRST sweep shortly after boot. An
            # interval-only job would open no channel for a full interval
            # (6 h by default) — the flag would read "on" while push is
            # simply absent, and an API restarting more often than the
            # interval would never open one at all (ADR-178 starvation,
            # measured there on the product rollup).
            next_run_time=datetime.now(UTC) + timedelta(minutes=PUSH_SYNC_INITIAL_DELAY_MINUTES),
            id=SCHEDULER_JOB_PUSH_CHANNEL_SYNC,
            name="Ensure/renew Google push watch channels",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=600,
        )
        logger.info(
            "push_channel_sync_scheduled",
            interval_minutes=settings.push_sync_interval_minutes,
        )

    # Push-driven heartbeat wake sweep (ADR-261): serves the wakes the
    # webhook queued, under the full eligibility checker. The job body
    # re-checks every flag, so a schedule left behind by a config change
    # stays inert.
    if (
        getattr(settings, "push_channels_enabled", False)
        and getattr(settings, "push_wake_enabled", False)
        and getattr(settings, "heartbeat_enabled", False)
    ):
        from src.core.constants import (
            PUSH_WAKE_INITIAL_DELAY_SECONDS,
            SCHEDULER_JOB_HEARTBEAT_WAKE_SWEEP,
        )
        from src.infrastructure.scheduler.heartbeat_wake_sweep import (
            run_heartbeat_wake_sweep,
        )

        scheduler.add_job(
            run_heartbeat_wake_sweep,
            trigger="interval",
            seconds=settings.push_wake_sweep_interval_seconds,
            jitter=jitter_seconds_for(seconds=settings.push_wake_sweep_interval_seconds),
            next_run_time=datetime.now(UTC) + timedelta(seconds=PUSH_WAKE_INITIAL_DELAY_SECONDS),
            id=SCHEDULER_JOB_HEARTBEAT_WAKE_SWEEP,
            name="Serve push-driven heartbeat wakes",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=60,
        )
        logger.info(
            "heartbeat_wake_sweep_scheduled",
            interval_seconds=settings.push_wake_sweep_interval_seconds,
        )
