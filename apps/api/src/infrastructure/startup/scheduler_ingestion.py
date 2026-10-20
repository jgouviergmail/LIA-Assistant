"""Register the durable ingestion sweep on the existing elected scheduler."""

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.infrastructure.scheduler.ingestion_delivery_job import run_ingestion_deliveries
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for


def register_ingestion_jobs(scheduler: AsyncIOScheduler) -> None:
    if not settings.sms_enabled:
        return
    scheduler.add_job(
        run_ingestion_deliveries,
        trigger="interval",
        seconds=settings.ingestion_delivery_interval_seconds,
        jitter=jitter_seconds_for(seconds=settings.ingestion_delivery_interval_seconds),
        next_run_time=datetime.now(UTC) + timedelta(seconds=5),
        id="phone_ingestion_deliveries",
        name="Deliver phone ingestion notices",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
