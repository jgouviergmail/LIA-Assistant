"""Native chart statistics must match the existing UI without materializing raw samples."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from src.core.config import settings
from src.domains.agents.application.health_aggregate import read_health_aggregate
from src.domains.agents.application.health_aggregate_schemas import HealthAggregateRead
from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.service import HealthMetricsService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("period", ["hour", "day", "week", "month", "year"])
async def test_native_chart_aggregate_matches_ui_with_bounded_sql(
    async_session, test_user, monkeypatch, period
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    test_user.health_metrics_agents_enabled = True
    start = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)
    end = start + timedelta(days=2)
    rows = [
        HealthSample(
            user_id=owner,
            kind="heart_rate" if i % 2 else "steps",
            date_start=start + timedelta(minutes=i % 2400),
            date_end=start + timedelta(minutes=i % 2400, seconds=i + 1),
            value=50 + i % 70 if i % 2 else i % 37,
            source="watch",
        )
        for i in range(3003)
    ]
    async_session.add_all(rows)
    await async_session.commit()
    await async_session.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))
    reference = await HealthMetricsService(async_session).aggregate(
        user_id=owner, period=period, from_ts=start, to_ts=end
    )
    fetch = AsyncMock(
        side_effect=AssertionError("Native aggregation must not materialize raw history")
    )
    monkeypatch.setattr(
        "src.domains.health_metrics.repository.HealthSampleRepository.fetch_samples_asc", fetch
    )
    observed = await read_health_aggregate(
        async_session, owner, HealthAggregateRead(period=period, from_ts=start, to_ts=end)
    )
    assert observed.model_dump(mode="json") == reference.model_dump(mode="json")
    fetch.assert_not_called()


@pytest.mark.parametrize("scenario", ["empty", "withdrawn", "late_withdrawal"])
async def test_chart_empty_window_and_live_authority(
    async_session, test_user, monkeypatch, scenario
):
    from src.core.exceptions import AuthorizationError
    from src.domains.agents.application import health_aggregate

    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    test_user.health_metrics_agents_enabled = True
    await async_session.commit()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    query = HealthAggregateRead(period="day", from_ts=start, to_ts=start + timedelta(days=2))
    if scenario == "withdrawn":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "late_withdrawal":
        original = health_aggregate.read_chart_statistics

        async def disable(*args, **kwargs):
            result = await original(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(health_aggregate, "read_chart_statistics", disable)
    if scenario != "empty":
        with pytest.raises(AuthorizationError):
            await read_health_aggregate(async_session, owner, query)
        return
    observed = await read_health_aggregate(async_session, owner, query)
    assert len(observed.points) == 2 and not any(point.has_data for point in observed.points)
    assert observed.averages.heart_rate_avg is None and observed.averages.steps_per_day_avg is None
