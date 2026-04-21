"""FastAPI router for authenticated (user-session) Health Metrics endpoints.

Covers:
- Metric listing (raw rows)
- Aggregation (bucketed points + period-wide averages)
- Deletion (by field / all)
- Token management (list / create / revoke)

The external ingestion endpoint lives in ``ingest_router.py`` — it is
authenticated by a per-user Bearer token rather than the session cookie.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import HEALTH_METRICS_DELETABLE_FIELDS
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_input
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.health_metrics.schemas import (
    HealthMetricAggregateResponse,
    HealthMetricDeleteResponse,
    HealthMetricRow,
    HealthMetricTokenCreateRequest,
    HealthMetricTokenCreateResponse,
    HealthMetricTokenListResponse,
    HealthMetricTokenRow,
)
from src.domains.health_metrics.service import HealthMetricsService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health-metrics", tags=["Health Metrics"])


# =============================================================================
# Metrics listing & aggregation
# =============================================================================


@router.get("", response_model=list[HealthMetricRow])
async def list_metrics(
    from_ts: datetime | None = Query(default=None, description="Inclusive window start (UTC)."),
    to_ts: datetime | None = Query(default=None, description="Exclusive window end (UTC)."),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[HealthMetricRow]:
    """Return raw metrics for the authenticated user (most recent first)."""
    service = HealthMetricsService(db)
    rows = await service.repo.list_metrics(
        current_user.id,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )
    return [HealthMetricRow.model_validate(row) for row in rows]


@router.get("/aggregate", response_model=HealthMetricAggregateResponse)
async def aggregate_metrics_endpoint(
    period: Literal["hour", "day", "week", "month", "year"] = Query(default="day"),
    from_ts: datetime | None = Query(default=None),
    to_ts: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HealthMetricAggregateResponse:
    """Return aggregated bucketed points + period averages for charts."""
    service = HealthMetricsService(db)
    return await service.aggregate(
        user_id=current_user.id,
        period=period,
        from_ts=from_ts,
        to_ts=to_ts,
    )


# =============================================================================
# Deletion
# =============================================================================


@router.delete("/all", response_model=HealthMetricDeleteResponse)
async def delete_all_metrics(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HealthMetricDeleteResponse:
    """Delete every metric row for the authenticated user."""
    service = HealthMetricsService(db)
    count = await service.delete_all(current_user.id)
    await db.commit()
    return HealthMetricDeleteResponse(scope="all", field=None, affected_rows=count)


@router.delete("", response_model=HealthMetricDeleteResponse)
async def delete_metric_field(
    field: str = Query(..., description="Column name to nullify across all rows."),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HealthMetricDeleteResponse:
    """Nullify one column for every metric row of the authenticated user."""
    if field not in HEALTH_METRICS_DELETABLE_FIELDS:
        raise_invalid_input(
            f"Unsupported field: {field}",
            allowed=list(HEALTH_METRICS_DELETABLE_FIELDS),
        )
    service = HealthMetricsService(db)
    count = await service.delete_field(current_user.id, field)
    await db.commit()
    return HealthMetricDeleteResponse(scope="field", field=field, affected_rows=count)


# =============================================================================
# Tokens
# =============================================================================


@router.get("/tokens", response_model=HealthMetricTokenListResponse)
async def list_tokens(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HealthMetricTokenListResponse:
    """List ingestion tokens owned by the authenticated user."""
    service = HealthMetricsService(db)
    rows = await service.list_tokens(current_user.id)
    return HealthMetricTokenListResponse(
        tokens=[HealthMetricTokenRow.model_validate(r) for r in rows]
    )


@router.post(
    "/tokens",
    response_model=HealthMetricTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_token(
    body: HealthMetricTokenCreateRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HealthMetricTokenCreateResponse:
    """Generate a fresh ingestion token (raw value is returned once only)."""
    service = HealthMetricsService(db)
    response = await service.create_token(current_user.id, label=body.label)
    await db.commit()
    return response


@router.delete(
    "/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_token(
    token_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke one of the user's ingestion tokens (idempotent)."""
    service = HealthMetricsService(db)
    await service.revoke_token(current_user.id, token_id)
    await db.commit()
