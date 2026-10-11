"""Chart reads share current health consent and source defaults, without raw-row materialization."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.health_aggregate_schemas import (
    HEALTH_CHART_MAX_BUCKETS,
    HealthAggregateRead,
)
from src.domains.agents.application.health_queries import require_health_access
from src.domains.health_metrics.chart_read import read_chart_statistics
from src.domains.health_metrics.schemas import HealthMetricAggregateResponse
from src.domains.health_metrics.service import _default_window_for


async def read_health_aggregate(
    db: AsyncSession, actor_id: UUID, query: HealthAggregateRead
) -> HealthMetricAggregateResponse:
    selected = HealthAggregateRead.model_validate(query.model_dump())
    await require_health_access(db, actor_id)
    end = selected.to_ts or datetime.now(UTC)
    start = selected.from_ts or end - _default_window_for(selected.period)
    observed = await read_chart_statistics(
        db,
        actor_id,
        period=selected.period,
        from_ts=start,
        to_ts=end,
        maximum_buckets=HEALTH_CHART_MAX_BUCKETS,
    )
    await require_health_access(db, actor_id)
    return observed
