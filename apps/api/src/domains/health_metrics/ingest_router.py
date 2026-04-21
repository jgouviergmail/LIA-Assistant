"""Public ingestion endpoints for the Health Metrics domain.

Isolated from ``router.py`` because it uses a different authentication
mechanism: a per-user Bearer token (hashed in DB), NOT the session cookie.
Both endpoints below accept the same token (one Bearer scoped to
``POST /api/v1/ingest/health/*``).

Two endpoints, one per kind:

- ``POST /api/v1/ingest/health/steps``      → body carries steps samples
- ``POST /api/v1/ingest/health/heart_rate`` → body carries HR samples

Each endpoint accepts four envelope shapes (iOS Shortcuts wrapping,
NDJSON, JSON array, ``{"data": [...]}``) thanks to the flexible parser,
then hands off to the service for per-sample validation and UPSERT.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
Revised: 2026-04-21 — split into 2 endpoints + batch upsert + parser.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    HEALTH_METRICS_KIND_HEART_RATE,
    HEALTH_METRICS_KIND_STEPS,
    HEALTH_METRICS_RATE_LIMIT_KEY_PREFIX,
    HEALTH_METRICS_RATE_LIMIT_WINDOW_SECONDS,
    HEALTH_METRICS_TOKEN_PREFIX,
)
from src.core.dependencies import get_db
from src.domains.health_metrics.constants import (
    LOG_EVENT_PARSER_ERROR,
    LOG_EVENT_RATE_LIMIT_HIT,
    LOG_EVENT_TOKEN_REJECTED,
)
from src.domains.health_metrics.models import HealthMetricToken
from src.domains.health_metrics.parser import (
    HealthSamplesBodyParseError,
    parse_samples_body,
)
from src.domains.health_metrics.schemas import HealthIngestResponse
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

ingest_router = APIRouter(prefix="/ingest/health", tags=["Health Metrics Ingestion"])


# =============================================================================
# Token extraction helper
# =============================================================================


def _extract_token_from_header(authorization: str | None) -> str | None:
    """Parse the Authorization header to retrieve a raw health-metrics token.

    Args:
        authorization: Raw value of the ``Authorization`` request header.

    Returns:
        The bare token value (starting with ``hm_``) if found, else None.

    Notes:
        Accepts both ``Bearer hm_xxx`` and the bare ``hm_xxx`` form so the
        iPhone Shortcut editor stays simple to configure.
    """
    if not authorization:
        return None
    stripped = authorization.strip()
    candidate = stripped[7:].strip() if stripped.lower().startswith("bearer ") else stripped
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
        # Raw HTTPException kept on purpose: centralized raisers in
        # src.core.exceptions do not propagate the WWW-Authenticate challenge
        # header (RFC 7235 §3.1) to FastAPI's response.
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
    """Enforce a per-token sliding-window rate limit.

    Args:
        token: The authenticated :class:`HealthMetricToken`.

    Returns:
        The same token after the request has been counted in Redis.

    Raises:
        HTTPException: 429 with a ``Retry-After`` header on rate-limit hit.

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
        allowed = await limiter.acquire(key=key, max_calls=max_calls, window_seconds=window_seconds)
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
# Body parsing + size guard
# =============================================================================


async def _parse_and_guard_body(request: Request) -> list[dict[str, Any]]:
    """Parse the raw body with the flexible parser and enforce size limits.

    Args:
        request: FastAPI Request (provides ``.body()``).

    Returns:
        List of raw sample dicts ready for per-sample validation.

    Raises:
        HTTPException: 400 on malformed body, 413 if the batch exceeds
            :data:`settings.health_metrics_max_samples_per_request`.
    """
    raw_body = await request.body()
    try:
        samples = parse_samples_body(raw_body)
    except HealthSamplesBodyParseError as exc:
        logger.warning(LOG_EVENT_PARSER_ERROR, reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed request body: {exc}",
        ) from exc

    max_samples = settings.health_metrics_max_samples_per_request
    if len(samples) > max_samples:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Batch too large: {len(samples)} samples " f"(max {max_samples} per request)."
            ),
        )
    return samples


# =============================================================================
# Endpoints
# =============================================================================


@ingest_router.post("/steps", response_model=HealthIngestResponse)
async def ingest_steps(
    request: Request,
    token: HealthMetricToken = Depends(_rate_limit_by_token),
    db: AsyncSession = Depends(get_db),
) -> HealthIngestResponse:
    """Ingest a batch of step samples.

    Accepts iOS Shortcuts wrapping, NDJSON, JSON array, or
    ``{"data":[…]}``. Each sample must have ``date_start``, ``date_end``,
    ``steps`` (int), and optionally ``o`` (source). Upsert is idempotent on
    ``(user_id, kind, date_start, date_end)``.
    """
    with health_metrics_ingest_duration_seconds.time():
        samples = await _parse_and_guard_body(request)
        service = HealthMetricsService(db)
        response = await service.ingest_batch(
            token_record=token,
            kind=HEALTH_METRICS_KIND_STEPS,
            raw_samples=samples,
        )
        await db.commit()
    return response


@ingest_router.post("/heart_rate", response_model=HealthIngestResponse)
async def ingest_heart_rate(
    request: Request,
    token: HealthMetricToken = Depends(_rate_limit_by_token),
    db: AsyncSession = Depends(get_db),
) -> HealthIngestResponse:
    """Ingest a batch of heart-rate samples.

    Accepts iOS Shortcuts wrapping, NDJSON, JSON array, or
    ``{"data":[…]}``. Each sample must have ``date_start``, ``date_end``,
    ``heart_rate`` (int), and optionally ``o`` (source). Upsert is
    idempotent on ``(user_id, kind, date_start, date_end)``.
    """
    with health_metrics_ingest_duration_seconds.time():
        samples = await _parse_and_guard_body(request)
        service = HealthMetricsService(db)
        response = await service.ingest_batch(
            token_record=token,
            kind=HEALTH_METRICS_KIND_HEART_RATE,
            raw_samples=samples,
        )
        await db.commit()
    return response
