"""Public ingestion endpoint for the Health Metrics domain.

Isolated from ``router.py`` because it uses a different authentication
mechanism: a per-user Bearer token (hashed in DB), NOT the session cookie.
This endpoint is typically consumed by an iPhone Shortcut automation that
cannot hold a session cookie.

Rate limiting is enforced per-token via the existing Redis sliding-window
limiter. Mixed per-field validation is applied by the service layer.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    HEALTH_METRICS_RATE_LIMIT_KEY_PREFIX,
    HEALTH_METRICS_RATE_LIMIT_WINDOW_SECONDS,
    HEALTH_METRICS_TOKEN_PREFIX,
)
from src.core.dependencies import get_db
from src.domains.health_metrics.constants import (
    LOG_EVENT_RATE_LIMIT_HIT,
    LOG_EVENT_TOKEN_REJECTED,
)
from src.domains.health_metrics.models import HealthMetricToken
from src.domains.health_metrics.schemas import (
    HealthMetricIngestRequest,
    HealthMetricIngestResponse,
)
from src.domains.health_metrics.service import HealthMetricsService
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_health_metrics import (
    health_metrics_auth_failures_total,
    health_metrics_ingest_duration_seconds,
    health_metrics_rate_limit_hits_total,
)
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

logger = get_logger(__name__)

ingest_router = APIRouter(prefix="/ingest", tags=["Health Metrics Ingestion"])


# =============================================================================
# Token extraction helper
# =============================================================================


def _extract_token_from_header(authorization: str | None) -> str | None:
    """Parse the Authorization header to retrieve a raw health-metrics token.

    Args:
        authorization: Raw value of the ``Authorization`` request header (or
            None if absent).

    Returns:
        The bare token value (starting with ``hm_``) if found, else None.

    Notes:
        Accepts both ``Bearer hm_xxx`` and the bare ``hm_xxx`` form so the
        iPhone Shortcut editor stays simple to configure.
    """
    if not authorization:
        return None
    stripped = authorization.strip()
    if stripped.lower().startswith("bearer "):
        candidate = stripped[7:].strip()
    else:
        candidate = stripped
    if not candidate.startswith(HEALTH_METRICS_TOKEN_PREFIX):
        return None
    return candidate


# =============================================================================
# Authentication dependency
# =============================================================================


async def _authenticate(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> HealthMetricToken:
    """Resolve the raw token from the Authorization header to its DB record.

    Args:
        authorization: Value of the ``Authorization`` header injected by FastAPI.
        db: Async DB session injected by FastAPI.

    Returns:
        The persisted, non-revoked :class:`HealthMetricToken` matching the
        SHA-256 hash of the supplied raw token.

    Raises:
        HTTPException: 401 with a ``WWW-Authenticate: Bearer`` challenge if the
            header is absent, malformed, or if the token is unknown / revoked.
    """
    raw = _extract_token_from_header(authorization)
    if raw is None:
        logger.warning(LOG_EVENT_TOKEN_REJECTED, reason="missing_or_malformed_header")
        health_metrics_auth_failures_total.labels(reason="missing_or_malformed_header").inc()
        # Raw HTTPException kept on purpose: the centralized raisers in
        # src.core.exceptions do not propagate the WWW-Authenticate challenge
        # header (RFC 7235 §3.1) to FastAPI's response. Same pattern as
        # auth/dependencies.py for the Retry-After header.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed ingestion token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    service = HealthMetricsService(db)
    token = await service.authenticate_token(raw)
    if token is None:
        logger.warning(LOG_EVENT_TOKEN_REJECTED, reason="unknown_or_revoked")
        health_metrics_auth_failures_total.labels(reason="unknown_or_revoked").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid ingestion token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


# =============================================================================
# Rate-limit dependency (per-token sliding window)
# =============================================================================


async def _rate_limit_by_token(
    token: HealthMetricToken = Depends(_authenticate),
) -> HealthMetricToken:
    """Enforce a per-token sliding-window rate limit over a 1-hour window.

    Args:
        token: The authenticated :class:`HealthMetricToken` (forwarded after
            successful resolution by :func:`_authenticate`).

    Returns:
        The same token, after the request has been counted in Redis.

    Raises:
        HTTPException: 429 with a ``Retry-After`` header when the per-token
            rate limit is exceeded.

    Notes:
        Fails open on Redis errors to avoid dropping legitimate ingestion
        traffic — same policy as the auth rate limiter.
    """
    max_calls = settings.health_metrics_rate_limit_per_hour
    window_seconds = HEALTH_METRICS_RATE_LIMIT_WINDOW_SECONDS
    key = f"{HEALTH_METRICS_RATE_LIMIT_KEY_PREFIX}:{token.id}"

    try:
        redis = await get_redis_cache()
        limiter = RedisRateLimiter(redis)
        allowed = await limiter.acquire(
            key=key,
            max_calls=max_calls,
            window_seconds=window_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - fail-open by design
        logger.error(
            "health_metrics_rate_limit_check_failed",
            token_id=str(token.id),
            error=str(exc),
        )
        return token

    if not allowed:
        logger.warning(
            LOG_EVENT_RATE_LIMIT_HIT,
            token_id=str(token.id),
            user_id=str(token.user_id),
            max_calls=max_calls,
            window_seconds=window_seconds,
        )
        health_metrics_rate_limit_hits_total.inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many ingestion requests. Please slow down.",
                "retry_after_seconds": window_seconds,
            },
            headers={"Retry-After": str(window_seconds)},
        )
    return token


# =============================================================================
# Endpoint
# =============================================================================


@ingest_router.post(
    "/health",
    response_model=HealthMetricIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_health(
    body: HealthMetricIngestRequest,
    token: HealthMetricToken = Depends(_rate_limit_by_token),
    db: AsyncSession = Depends(get_db),
) -> HealthMetricIngestResponse:
    """Ingest one health metric payload from an external authenticated client.

    The server timestamps the measurement at reception — clients do not
    supply a timestamp. Per-field validation is mixed: invalid values are
    stored as NULL, valid fields of the same payload are preserved.
    """
    with health_metrics_ingest_duration_seconds.time():
        service = HealthMetricsService(db)
        response = await service.ingest(token_record=token, payload=body.data)
        await db.commit()
    return response
