"""
Scheduled task to proactively refresh OAuth tokens before expiration.

Runs periodically (default: every 15 minutes) and refreshes tokens expiring
within a configurable margin (default: 30 minutes). This prevents disconnections
when users return after periods of inactivity.

NOTE: Uses SchedulerLock to prevent duplicate execution with multiple uvicorn workers.
This is critical for token refresh to avoid race conditions (double refresh).

Configuration (via .env):
    OAUTH_PROACTIVE_REFRESH_ENABLED=true
    OAUTH_PROACTIVE_REFRESH_INTERVAL_MINUTES=15
    OAUTH_PROACTIVE_REFRESH_MARGIN_SECONDS=1800
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_TOKEN_REFRESH
from src.core.security import decrypt_data
from src.domains.connectors.models import Connector
from src.domains.connectors.repository import ConnectorRepository
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)

logger = structlog.get_logger(__name__)

# Job name for metrics (matches SCHEDULER_JOB_TOKEN_REFRESH constant)
_JOB_NAME = "token_refresh"


async def refresh_expiring_tokens() -> None:
    """
    Proactively refresh OAuth tokens that are expiring soon.

    Runs periodically via APScheduler. Refreshes tokens expiring within
    the configured margin to prevent disconnections.

    Configuration:
        - settings.oauth_proactive_refresh_margin_seconds: Refresh window
        - Tokens expiring within this margin will be refreshed

    Metrics:
        - background_job_duration_seconds{job_name="token_refresh"}
        - background_job_errors_total{job_name="token_refresh"}

    Logs (structured):
        - token_refresh_starting: Job start with total connectors
        - token_refresh_needed: Individual connector needs refresh
        - token_refresh_success: Individual connector refreshed
        - token_refresh_connector_failed: Individual connector error
        - token_refresh_completed: Job summary with stats
    """
    # Acquire distributed lock to prevent duplicate execution across workers.
    # Lock is retained via TTL (not released on context exit) — see SchedulerLock.
    redis = await get_redis_cache()
    if redis:
        async with SchedulerLock(redis, SCHEDULER_JOB_TOKEN_REFRESH) as lock:
            if not lock.acquired:
                logger.debug("token_refresh_skipped_lock_busy")
                return

    start_time = time.perf_counter()
    refreshed_count = 0
    error_count = 0
    skipped_count = 0

    async with get_db_context() as db:
        try:
            # Get all active OAuth connectors using repository pattern
            repository = ConnectorRepository(db)
            connectors = await repository.get_active_oauth_connectors()

            if not connectors:
                logger.debug("token_refresh_no_connectors")
                _record_duration(start_time)
                return

            logger.info(
                "token_refresh_starting",
                total_connectors=len(connectors),
                margin_seconds=settings.oauth_proactive_refresh_margin_seconds,
            )

            # Calculate refresh threshold using settings
            refresh_threshold = datetime.now(UTC) + timedelta(
                seconds=settings.oauth_proactive_refresh_margin_seconds
            )

            # Process each connector
            for connector in connectors:
                result = await _process_connector(connector, refresh_threshold, db)
                if result == "refreshed":
                    refreshed_count += 1
                elif result == "error":
                    error_count += 1
                else:
                    skipped_count += 1

            # Commit any pending changes
            await db.commit()

            # Record metrics and log completion
            duration = _record_duration(start_time)
            logger.info(
                "token_refresh_completed",
                refreshed=refreshed_count,
                errors=error_count,
                skipped=skipped_count,
                total=len(connectors),
                duration_seconds=round(duration, 3),
            )

        except Exception as e:
            background_job_errors_total.labels(job_name=_JOB_NAME).inc()
            duration = _record_duration(start_time)

            logger.error(
                "token_refresh_failed",
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(duration, 3),
            )
            raise


async def _process_connector(
    connector: Connector,
    refresh_threshold: datetime,
    db: AsyncSession,
) -> str:
    """
    Process a single connector for token refresh.

    Args:
        connector: Connector to check and potentially refresh
        refresh_threshold: Datetime threshold - refresh if expires before this
        db: Database session

    Returns:
        "refreshed" if token was refreshed
        "skipped" if token doesn't need refresh
        "error" if refresh failed
    """
    try:
        # Check if credentials need refresh
        if not connector.credentials_encrypted:
            return "skipped"

        credentials = _decrypt_credentials(connector)
        if credentials is None:
            return "error"

        # Check expiration
        if not credentials.expires_at:
            return "skipped"

        if credentials.expires_at > refresh_threshold:
            # Token still valid, no refresh needed
            return "skipped"

        # Token expiring soon - refresh it
        time_until_expiry = (credentials.expires_at - datetime.now(UTC)).total_seconds()

        logger.info(
            "token_refresh_needed",
            connector_id=str(connector.id),
            connector_type=connector.connector_type.value,
            user_id=str(connector.user_id),
            expires_in_seconds=round(time_until_expiry),
        )

        # Use ConnectorService for refresh (reuses existing logic with retry)
        service = ConnectorService(db)
        await service._refresh_oauth_token(connector, credentials)

        logger.info(
            "token_refresh_success",
            connector_id=str(connector.id),
            connector_type=connector.connector_type.value,
            user_id=str(connector.user_id),
        )
        return "refreshed"

    except Exception as e:
        logger.error(
            "token_refresh_connector_failed",
            connector_id=str(connector.id),
            connector_type=connector.connector_type.value,
            user_id=str(connector.user_id),
            error=str(e),
            error_type=type(e).__name__,
        )
        return "error"


def _decrypt_credentials(connector: Connector) -> ConnectorCredentials | None:
    """
    Safely decrypt connector credentials.

    Args:
        connector: Connector with encrypted credentials

    Returns:
        Decrypted credentials or None if decryption fails
    """
    try:
        decrypted_json = decrypt_data(connector.credentials_encrypted)
        return ConnectorCredentials.model_validate_json(decrypted_json)
    except Exception as e:
        logger.error(
            "token_refresh_decrypt_failed",
            connector_id=str(connector.id),
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def _record_duration(start_time: float) -> float:
    """Record job duration metric and return elapsed time."""
    duration = time.perf_counter() - start_time
    background_job_duration_seconds.labels(job_name=_JOB_NAME).observe(duration)
    return duration
