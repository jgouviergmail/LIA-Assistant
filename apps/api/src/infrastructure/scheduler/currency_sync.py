"""
Scheduled task to sync currency rates daily.

Fetches USD->EUR from API and persists to DB for audit trail.
"""

import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import update

from src.core.constants import SUPPORTED_CURRENCIES
from src.domains.llm.models import CurrencyExchangeRate
from src.infrastructure.database import get_db_context
from src.infrastructure.external.currency_api import CurrencyRateService
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)

# Currency sync is always USD->EUR (LLM pricing base currency + target)
_CURRENCY_USD = SUPPORTED_CURRENCIES[0]  # "USD"
_CURRENCY_EUR = SUPPORTED_CURRENCIES[1]  # "EUR"


async def sync_currency_rates() -> None:
    """
    Sync USD->EUR rate daily at 3:00 AM UTC.

    Creates new active entry and deactivates previous for audit trail.

    Metrics:
        - background_job_duration_seconds{job_name="currency_sync"}
        - background_job_errors_total{job_name="currency_sync"}
    """
    start_time = time.perf_counter()
    job_name = "currency_sync"

    async with get_db_context() as db:
        try:
            # Fetch live rate from API
            api = CurrencyRateService()
            rate = await api.get_rate(_CURRENCY_USD, _CURRENCY_EUR)

            if not rate:
                logger.error("currency_sync_failed_api_unavailable")
                background_job_errors_total.labels(job_name=job_name).inc()
                return

            # Deactivate previous active rate
            stmt = (
                update(CurrencyExchangeRate)
                .where(
                    CurrencyExchangeRate.from_currency == _CURRENCY_USD,
                    CurrencyExchangeRate.to_currency == _CURRENCY_EUR,
                    CurrencyExchangeRate.is_active,
                )
                .values(is_active=False)
            )
            await db.execute(stmt)

            # Insert new active rate
            new_rate = CurrencyExchangeRate(
                from_currency=_CURRENCY_USD,
                to_currency=_CURRENCY_EUR,
                rate=rate,
                effective_from=datetime.now(UTC),
                is_active=True,
            )
            db.add(new_rate)

            # Track duration
            duration = time.perf_counter() - start_time
            background_job_duration_seconds.labels(job_name=job_name).observe(duration)

            logger.info(
                "currency_rate_synced",
                from_currency=_CURRENCY_USD,
                to_currency=_CURRENCY_EUR,
                rate=float(rate),
                effective_from=new_rate.effective_from.isoformat(),
                duration_seconds=round(duration, 3),
            )

        except Exception as e:
            # Track error
            background_job_errors_total.labels(job_name=job_name).inc()

            # Track duration even on error
            duration = time.perf_counter() - start_time
            background_job_duration_seconds.labels(job_name=job_name).observe(duration)

            logger.error(
                "currency_sync_failed",
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 3),
            )
            raise
