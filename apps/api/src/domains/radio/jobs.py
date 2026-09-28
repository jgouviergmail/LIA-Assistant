"""The radio's two background jobs, as the scheduler runs them (ADR-324).

- ``run_newsroom_pass`` — one pass of the newsroom: the shipped catalogue and
  the listeners' own sites, for as long as someone listened recently. The
  capability is read at EVERY tick: an operator switching the radio off is
  obeyed without a restart, and from the next tick on no stranger's server is
  read. What the newsroom already filed stays (records, not the capability).
- ``sweep_radio_media`` — the session directories a crash left behind. It never
  removes one a live session names, and when the live sessions cannot be read
  it removes nothing: without them, no directory is known to be safe.

Both run on the scheduler leader alone. The pass takes no lock of its own: a
leader runs one at a time (``max_instances=1``), a pass ends under its interval
(``RADIO_NEWSROOM_PASS_TIMEOUT_SECONDS``, refused at boot otherwise), and a
newly elected leader first ticks about an interval after it starts. At worst —
a handover while a long pass finishes — one feed is read twice, which every
write absorbs (conditional GETs, ``ON CONFLICT DO NOTHING``, column arithmetic).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import structlog

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.radio.live_store import RadioSessions
from src.domains.radio.media import sweep_orphans
from src.domains.radio.newsroom.collector import PassReport, collect_pass
from src.domains.radio.newsroom.store import NewsroomDatabase
from src.domains.radio.settings_view import collector_limits, radio_media_root, radio_runtime
from src.domains.radio.wiring import newsroom_client, newsroom_robots
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.errors import database_error_fields
from src.infrastructure.observability.metrics_radio import (
    radio_media_orphans_removed_total,
    radio_newsroom_feed_readings_total,
    radio_newsroom_last_run_timestamp_seconds,
    radio_newsroom_passes_total,
    radio_newsroom_stories_total,
    radio_newsroom_texts_total,
)

logger = structlog.get_logger(__name__)

#: How a newsroom tick ended (``radio_newsroom_passes_total{outcome}``).
PASS_COMPLETED: Final[str] = "completed"
PASS_CUT: Final[str] = "cut"
PASS_FAILED: Final[str] = "failed"
PASS_OFF: Final[str] = "off"


def _tick_ended(outcome: str) -> None:
    """Count a tick that ran to its end, and stamp when (a failed one stamps nothing)."""
    radio_newsroom_passes_total.labels(outcome=outcome).inc()
    radio_newsroom_last_run_timestamp_seconds.set_to_current_time()


def _count_pass(report: PassReport) -> None:
    """What one pass did, on the dashboard's counters."""
    _tick_ended(PASS_CUT if report.cut else PASS_COMPLETED)
    radio_newsroom_feed_readings_total.labels(outcome="read").inc(report.feeds_read)
    radio_newsroom_feed_readings_total.labels(outcome="failed").inc(report.feeds_failed)
    radio_newsroom_stories_total.labels(event="new").inc(report.items_new)
    radio_newsroom_stories_total.labels(event="purged").inc(report.purged)
    radio_newsroom_texts_total.labels(outcome="ready").inc(report.texts_ready)
    radio_newsroom_texts_total.labels(outcome="unavailable").inc(report.texts_unavailable)


async def run_newsroom_pass() -> PassReport | None:
    """One newsroom pass — nothing while the radio is switched off.

    Returns:
        What the pass did; None when it did not run (switched off) or failed
        (logged by its facts, never by its text — ADR-317).
    """
    if not await is_capability_enabled(PlatformCapability.RADIO):
        _tick_ended(PASS_OFF)
        return None
    try:
        robots = await newsroom_robots()
        async with newsroom_client() as client:
            report = await collect_pass(
                NewsroomDatabase(),
                client,
                robots,
                now=datetime.now(UTC),
                limits=collector_limits(),
            )
    except Exception as exc:
        radio_newsroom_passes_total.labels(outcome=PASS_FAILED).inc()
        logger.error(
            "radio_newsroom_pass_failed",
            error_type=type(exc).__name__,
            **database_error_fields(exc),
        )
        return None
    _count_pass(report)
    return report


async def sweep_radio_media() -> int:
    """Remove the session directories no live session claims and nobody touched lately.

    Housekeeping, not the capability: it runs whether or not the radio is
    switched on, because a crash may have left audio behind before the switch.

    Returns:
        How many directories went (0 when the sweep could not run).
    """
    try:
        redis = await get_redis_cache()
        live = await RadioSessions(redis, ttl_s=settings.radio_record_ttl_seconds).active_ids(
            now=datetime.now(UTC), horizon_s=radio_runtime().live_horizon_s
        )
    except Exception as exc:
        # Doubt never deletes: without the live sessions, nothing is known orphaned.
        logger.warning("radio_media_sweep_skipped", error_type=type(exc).__name__)
        return 0
    try:
        removed = await sweep_orphans(
            radio_media_root(),
            live=live,
            older_than_s=float(settings.radio_media_orphan_age_seconds),
        )
    except OSError as exc:
        logger.warning("radio_media_sweep_failed", error_type=type(exc).__name__)
        return 0
    if removed:
        radio_media_orphans_removed_total.inc(removed)
        logger.info("radio_media_swept", removed=removed)
    return removed


__all__ = ["run_newsroom_pass", "sweep_radio_media"]
