"""Chart reads share current health consent and source defaults, without raw-row materialization."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import HEALTH_METRICS_CHART_MAX_BUCKETS
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.application.health_aggregate_schemas import HealthAggregateRead
from src.domains.agents.application.health_queries import require_health_access
from src.domains.health_metrics.chart_read import default_chart_window, read_chart_statistics
from src.domains.health_metrics.schemas import HealthMetricAggregateResponse


async def read_health_aggregate(
    db: AsyncSession, actor_id: UUID, query: HealthAggregateRead
) -> HealthMetricAggregateResponse:
    """The Settings chart, read for the assistant at the account's clock.

    Args:
        db: The command's session.
        actor_id: The account reading.
        query: The period and optional window.

    Returns:
        The chart the Settings screen draws for the same window.

    Raises:
        AuthorizationError: The feature is off or the consent is not given.
        ValueError: The window needs more buckets than a chart draws.
    """
    selected = HealthAggregateRead.model_validate(query.model_dump())
    actor = await require_health_access(db, actor_id)
    zone = resolve_user_timezone(actor)
    start, end = default_chart_window(
        selected.period,
        zone=zone,
        now=datetime.now(UTC),
        from_ts=selected.from_ts,
        to_ts=selected.to_ts,
    )
    observed = await read_chart_statistics(
        db,
        actor_id,
        period=selected.period,
        zone=zone,
        from_ts=start,
        to_ts=end,
        maximum_buckets=HEALTH_METRICS_CHART_MAX_BUCKETS,
    )
    await require_health_access(db, actor_id)
    return observed
