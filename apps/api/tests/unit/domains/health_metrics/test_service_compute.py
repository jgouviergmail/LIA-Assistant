"""Unit tests for ``HealthMetricsService.compute_kind_summary`` time bounds.

Verifies the defaulting logic introduced with the v1.17.2 refactor:

- ``time_min=None`` -> today's midnight UTC.
- ``time_max=None`` -> ``datetime.now(UTC)``.
- Both bounds forwarded verbatim to the sample repo.

Complements the tool-level tests in ``tests/unit/domains/agents/tools/
test_health_tools.py`` (which mock the service) and the ingestion-level
tests in ``test_aggregator.py`` / ``test_baseline_signals.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.domains.health_metrics.service import HealthMetricsService

pytestmark = pytest.mark.unit


_USER_ID = UUID("35e9301b-86e1-4665-b47a-23363fff33aa")


def _make_service_with_mocked_repo() -> tuple[HealthMetricsService, AsyncMock]:
    """Instantiate the service with both repos mocked to AsyncMock."""
    db_mock = MagicMock(name="AsyncSession")
    service = HealthMetricsService(db_mock)
    fetch_mock = AsyncMock(return_value=[])
    service.sample_repo.fetch_samples_kind = fetch_mock  # type: ignore[method-assign]
    return service, fetch_mock


class TestComputeKindSummaryDefaults:
    """Defaulting behaviour of ``time_min`` / ``time_max`` in compute_kind_summary."""

    async def test_both_bounds_none_uses_today_midnight_and_now(self) -> None:
        """When both bounds are omitted, window is today 00:00 UTC -> now."""
        service, fetch_mock = _make_service_with_mocked_repo()

        before = datetime.now(UTC)
        result = await service.compute_kind_summary(_USER_ID, "steps")
        after = datetime.now(UTC)

        fetch_mock.assert_awaited_once()
        kwargs = fetch_mock.await_args.kwargs
        from_ts: datetime = kwargs["from_ts"]
        to_ts: datetime = kwargs["to_ts"]

        assert from_ts == before.replace(hour=0, minute=0, second=0, microsecond=0)
        assert before <= to_ts <= after
        assert result["samples_count"] == 0
        assert result["total"] is None

    async def test_explicit_bounds_forwarded_verbatim(self) -> None:
        """Explicit ``time_min`` and ``time_max`` are forwarded unchanged."""
        service, fetch_mock = _make_service_with_mocked_repo()
        tmin = datetime(2026, 4, 20, 0, 0, 0, tzinfo=UTC)
        tmax = datetime(2026, 4, 22, 23, 59, 59, tzinfo=UTC)

        result = await service.compute_kind_summary(_USER_ID, "steps", time_min=tmin, time_max=tmax)

        kwargs = fetch_mock.await_args.kwargs
        assert kwargs["from_ts"] == tmin
        assert kwargs["to_ts"] == tmax
        assert result["from_ts"] == tmin.isoformat()
        assert result["to_ts"] == tmax.isoformat()

    async def test_time_max_only_keeps_today_midnight_for_time_min(self) -> None:
        """Omitted ``time_min`` still falls back to today's midnight UTC."""
        service, fetch_mock = _make_service_with_mocked_repo()
        tmax = datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC)

        await service.compute_kind_summary(_USER_ID, "steps", time_max=tmax)

        kwargs = fetch_mock.await_args.kwargs
        now = datetime.now(UTC)
        assert kwargs["from_ts"] == now.replace(hour=0, minute=0, second=0, microsecond=0)
        assert kwargs["to_ts"] == tmax


class TestComputeOverviewParallel:
    """``compute_overview`` dispatches one ``compute_kind_summary`` per kind."""

    async def test_iterates_all_registered_kinds(self) -> None:
        """One ``compute_kind_summary`` call per registered kind."""
        from src.domains.health_metrics.kinds import HEALTH_KINDS

        service, fetch_mock = _make_service_with_mocked_repo()

        result = await service.compute_overview(_USER_ID)

        assert set(result.keys()) == set(HEALTH_KINDS.keys())
        # One repo fetch per kind (sequential or parallel — we only assert
        # the aggregate was computed for every kind).
        assert fetch_mock.await_count == len(HEALTH_KINDS)
