"""The assistant's chart command reads the Settings chart's own door, at the account's clock.

Since the ADR-148 amendment of 2026-11-14 the Settings chart and the
assistant's ``health_chart.read`` both read ``chart_read.read_chart_statistics``
— one SQL statement per kind, counted through the fusion door, bucketed at the
account's midnight whatever the session ``TimeZone``.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from src.core.config import settings
from src.domains.agents.application.health_aggregate import read_health_aggregate
from src.domains.agents.application.health_aggregate_schemas import HealthAggregateRead
from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.service import HealthMetricsService

pytestmark = pytest.mark.integration

PARIS = ZoneInfo("Europe/Paris")


@pytest.mark.parametrize("period", ["hour", "day", "week", "month", "year"])
async def test_the_assistant_reads_the_chart_the_settings_screen_draws(
    async_session, test_user, monkeypatch, period
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    test_user.health_metrics_agents_enabled = True
    test_user.timezone = PARIS.key
    # 29 March: the spring clock change in Paris falls inside the window.
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
    # A session clock elsewhere changes nothing: days are cut at the account's.
    await async_session.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))

    settings_chart = await HealthMetricsService(async_session).aggregate(
        user_id=owner, zone=PARIS, period=period, from_ts=start, to_ts=end
    )
    observed = await read_health_aggregate(
        async_session, owner, HealthAggregateRead(period=period, from_ts=start, to_ts=end)
    )

    assert observed.model_dump(mode="json") == settings_chart.model_dump(mode="json")
    buckets = [point.bucket for point in observed.points]
    assert buckets == sorted(buckets) and len(set(buckets)) == len(buckets)
    assert any(point.has_data for point in observed.points)
    for bucket in buckets:
        local = bucket.astimezone(PARIS)
        assert (local.minute, local.second) == (0, 0)
        if period != "hour":
            assert local.hour == 0, bucket
    if period == "hour":
        # 02:00 never happened on 29 March in Paris: no bucket is drawn for it.
        assert datetime(2026, 3, 29, 2, 0) not in {b.replace(tzinfo=None) for b in buckets}


@pytest.mark.parametrize("scenario", ["empty", "withdrawn", "late_withdrawal"])
async def test_chart_empty_window_and_live_authority(
    async_session, test_user, monkeypatch, scenario
):
    from src.core.exceptions import AuthorizationError
    from src.domains.agents.application import health_aggregate

    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    test_user.health_metrics_agents_enabled = True
    test_user.timezone = PARIS.key
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
    # 48 hours from midnight UTC touch three Paris days: 1 January from 01:00,
    # 2 January, and 3 January until 01:00.
    assert [point.bucket.astimezone(PARIS).date().isoformat() for point in observed.points] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]
    assert not any(point.has_data for point in observed.points)
    assert observed.averages.heart_rate_avg is None and observed.averages.steps_per_day_avg is None
