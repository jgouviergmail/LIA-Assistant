"""
Scheduled task for automatic attachment cleanup.

Removes expired attachment files (disk + DB) as a safety net
for orphan files (uploaded but never sent in a message).

Runs at the configured interval with bounded work. Failed file removals keep
their durable paths and are retried; unknown upload writers are never reclaimed.

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
Reference: docs/technical/ATTACHMENTS_INTEGRATION.md
Pattern: interest_cleanup.py
"""

import time

import structlog

from src.core.constants import SCHEDULER_JOB_ATTACHMENT_CLEANUP
from src.domains.attachments.service import AttachmentService
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)


async def cleanup_expired_attachments() -> dict[str, int]:
    """
    Bounded periodic attachment cleanup job.

    Removes expired attachments from disk and database.
    The explicit expires_at column owns expiry; kept files carry no deadline.

    Metrics:
        - background_job_duration_seconds{job_name="attachment_cleanup"}
        - background_job_errors_total{job_name="attachment_cleanup"}

    Returns:
        Stats dict with deleted count and errors.
    """
    start_time = time.perf_counter()
    job_name = SCHEDULER_JOB_ATTACHMENT_CLEANUP

    try:
        logger.info("attachment_cleanup_started")

        async with get_db_context() as db:
            service = AttachmentService(db)
            stats = await service.cleanup_expired()

        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)
        if stats["errors"]:
            background_job_errors_total.labels(job_name=job_name).inc()

        logger.info(
            "attachment_cleanup_completed",
            deleted=stats["deleted"],
            errors=stats["errors"],
            duration_seconds=round(duration, 3),
        )

        return stats

    except Exception as e:
        background_job_errors_total.labels(job_name=job_name).inc()

        duration = time.perf_counter() - start_time
        background_job_duration_seconds.labels(job_name=job_name).observe(duration)

        logger.error(
            "attachment_cleanup_failed",
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3),
            exc_info=True,
        )
        raise
