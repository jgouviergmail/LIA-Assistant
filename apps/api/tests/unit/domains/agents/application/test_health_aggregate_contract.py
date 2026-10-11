"""Window sizes fail before SQL, and source calendar boundaries remain authoritative."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.domains.agents.application.health_aggregate_schemas import (
    HEALTH_CHART_MAX_BUCKETS,
    HealthAggregateRead,
)
from src.domains.agents.application.health_aggregate_spec import HEALTH_AGGREGATE_MANIFEST
from src.domains.health_metrics.chart_read import chart_bucket_starts, read_chart_statistics

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"period": "unknown"},
        {"user_id": "other"},
        {"from_ts": "2026-01-01T00:00:00"},
        {"from_ts": "2026-01-02T00:00:00Z", "to_ts": "2026-01-01T00:00:00Z"},
    ],
)
def test_chart_input_requires_source_period_owned_scope_and_aware_valid_window(payload):
    with pytest.raises(ValidationError):
        HealthAggregateRead.model_validate(payload)


async def test_excessive_points_are_refused_before_query_and_bound_is_published():
    db = AsyncMock()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    from uuid import uuid4

    with pytest.raises(ValueError, match=str(HEALTH_CHART_MAX_BUCKETS)):
        await read_chart_statistics(
            db,
            uuid4(),
            period="hour",
            from_ts=start,
            to_ts=start + timedelta(hours=HEALTH_CHART_MAX_BUCKETS + 1),
            maximum_buckets=HEALTH_CHART_MAX_BUCKETS,
        )
    db.execute.assert_not_called()
    assert str(HEALTH_CHART_MAX_BUCKETS) in HEALTH_AGGREGATE_MANIFEST.description


def test_last_bucket_does_not_advance_beyond_datetime_domain():
    result = chart_bucket_starts(
        "year",
        datetime(9999, 1, 1, tzinfo=UTC),
        datetime(9999, 12, 31, tzinfo=UTC),
        maximum=HEALTH_CHART_MAX_BUCKETS,
    )
    assert result == [datetime(9999, 1, 1, tzinfo=UTC)]
