"""Hourly product analytics rollup (ADR-178).

Leader-elected APScheduler job. Metrics:
- background_job_duration_seconds{job_name="product_analytics_rollup"}
- background_job_errors_total{job_name="product_analytics_rollup"}

Steps, in order:
1. Backfill ``cost_eur`` from ``message_token_summary`` (EUR-only contract).
2. Promote uncorrected action outcomes past the window to E2 (spec §4).
3. Purge raw rows past retention (decision #6 — settings-driven, 180 d).
4. Refresh the DB-backed Prometheus gauges + freshness stamp.

The freshness gauge is stamped by step 4 only on full success — a failing
rollup must trip the 2 h freshness SLA, never hide behind a partial pass.
"""

import time

import structlog

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_PRODUCT_ROLLUP

logger = structlog.get_logger(__name__)


async def run_product_rollup() -> None:
    """Execute one rollup tick (cost backfill, E2, purge, gauges)."""
    if not getattr(settings, "product_analytics_enabled", False):
        return

    from src.domains.product.repository import ProductRepository
    from src.infrastructure.database import get_db_context
    from src.infrastructure.observability.metrics import (
        background_job_duration_seconds,
        background_job_errors_total,
    )
    from src.infrastructure.observability.metrics_product import (
        refresh_product_gauges,
        track_outcome_event,
    )

    started = time.monotonic()
    try:
        async with get_db_context() as db:
            repo = ProductRepository(db)

            backfilled = await repo.backfill_costs()
            promoted = await repo.upgrade_e2_candidates(settings.product_e2_validation_window_hours)
            outcomes_purged, events_purged = await repo.purge_older_than(
                settings.product_outcomes_retention_days
            )
            await db.commit()

        # Counter increments AFTER the commit: an aborted transaction must
        # not leave phantom E2 increments in Prometheus.
        for result_type, domain in promoted:
            track_outcome_event(result_type, domain, "E2")

        await refresh_product_gauges()

        logger.info(
            "product_rollup_completed",
            cost_backfilled=backfilled,
            e2_promoted=len(promoted),
            outcomes_purged=outcomes_purged,
            events_purged=events_purged,
            duration_seconds=round(time.monotonic() - started, 3),
        )
    except Exception:
        background_job_errors_total.labels(job_name=SCHEDULER_JOB_PRODUCT_ROLLUP).inc()
        logger.exception("product_rollup_failed")
    finally:
        background_job_duration_seconds.labels(job_name=SCHEDULER_JOB_PRODUCT_ROLLUP).observe(
            time.monotonic() - started
        )
