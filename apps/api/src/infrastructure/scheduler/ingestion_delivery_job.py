"""APScheduler composition root for phone ingestion; no paid model calls."""

from datetime import UTC, datetime

from src.core.config import settings
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_ingestion import (
    ingestion_delivery_sweep_timestamp_seconds,
)
from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker
from src.infrastructure.scheduler.ingestion_transport import IngestionTransport


async def run_ingestion_deliveries() -> None:
    if not settings.sms_enabled:
        return
    await IngestionDeliveryWorker(get_db_context, IngestionTransport()).run_once(
        limit=settings.ingestion_delivery_batch_size
    )
    ingestion_delivery_sweep_timestamp_seconds.set(datetime.now(UTC).timestamp())
