"""Unit tests for ``HealthMetricsService.compute_kind_summary`` windows and values.

What holds since the ADR-148 amendment of 2026-11-14:

- ``time_min=None`` -> the person's midnight (their "today"), not UTC's.
- ``time_max=None`` -> now.
- Explicit bounds are forwarded verbatim, and every instant said back is
  said in the person's zone.
- The values are the counted ones (``fetch_window_summary``): a SUM kind
  reports its counted total, an AVG kind the average over its counted rows;
  nothing counted reports no value at all.

Complements the tool-level tests in ``tests/unit/domains/agents/tools/
test_health_tools.py`` (which mock the service) and the PostgreSQL proof of
the fusion and the local day in ``tests/integration/test_health_daily_stats_rollup.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from src.core.local_day import local_midnight, local_today
from src.domains.health_metrics.repository import CountedAggregate, WindowSummary
from src.domains.health_metrics.service import HealthMetricsService

pytestmark = pytest.mark.unit

_USER_ID = UUID("35e9301b-86e1-4665-b47a-23363fff33aa")
PARIS = ZoneInfo("Europe/Paris")
NOTHING = WindowSummary(counted=None, samples=0, last_start=None, last_value=None)


def _service() -> HealthMetricsService:
    return HealthMetricsService(MagicMock(name="AsyncSession"))


def _midnight(moment: datetime) -> datetime:
    return local_midnight(local_today(moment, PARIS), PARIS)


class TestComputeKindSummaryWindow:
    """Defaulting behaviour of ``time_min`` / ``time_max`` in compute_kind_summary."""

    async def test_both_bounds_none_uses_the_person_s_midnight_and_now(self) -> None:
        service = _service()
        fetch = AsyncMock(return_value=NOTHING)
        with patch.object(service.sample_repo, "fetch_window_summary", fetch):
            before = datetime.now(UTC)
            result = await service.compute_kind_summary(_USER_ID, "steps", zone=PARIS)
            after = datetime.now(UTC)

        kwargs = fetch.await_args.kwargs
        assert kwargs["from_ts"] in {_midnight(before), _midnight(after)}
        assert kwargs["from_ts"].astimezone(PARIS).time().isoformat() == "00:00:00"
        assert before <= kwargs["to_ts"] <= after
        assert result["samples_count"] == 0
        assert result["total"] is None

    async def test_explicit_bounds_forwarded_verbatim_and_said_in_the_zone(self) -> None:
        service = _service()
        fetch = AsyncMock(return_value=NOTHING)
        tmin = datetime(2026, 4, 19, 22, 0, tzinfo=UTC)  # 20 April, midnight in Paris
        tmax = datetime(2026, 4, 22, 22, 0, tzinfo=UTC)
        with patch.object(service.sample_repo, "fetch_window_summary", fetch):
            result = await service.compute_kind_summary(
                _USER_ID, "steps", zone=PARIS, time_min=tmin, time_max=tmax
            )

        kwargs = fetch.await_args.kwargs
        assert (kwargs["from_ts"], kwargs["to_ts"]) == (tmin, tmax)
        assert result["from_ts"] == "2026-04-20T00:00:00+02:00"
        assert result["to_ts"] == "2026-04-23T00:00:00+02:00"

    async def test_time_max_only_keeps_the_person_s_midnight_for_time_min(self) -> None:
        service = _service()
        fetch = AsyncMock(return_value=NOTHING)
        tmax = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)
        with patch.object(service.sample_repo, "fetch_window_summary", fetch):
            before = datetime.now(UTC)
            await service.compute_kind_summary(_USER_ID, "steps", zone=PARIS, time_max=tmax)
            after = datetime.now(UTC)

        kwargs = fetch.await_args.kwargs
        assert kwargs["from_ts"] in {_midnight(before), _midnight(after)}
        assert kwargs["to_ts"] == tmax


class TestComputeKindSummaryValues:
    """The counted values, per aggregation method."""

    async def test_steps_report_their_counted_total(self) -> None:
        """Two devices' overlap is already fused below: the total is the counted one."""
        service = _service()
        last = datetime(2026, 11, 14, 17, 0, tzinfo=UTC)
        window = WindowSummary(
            counted=CountedAggregate(rows=40, total=13296.6, minimum=0.4, maximum=900.0),
            samples=205,
            last_start=last,
            last_value=120,
        )
        with patch.object(
            service.sample_repo, "fetch_window_summary", AsyncMock(return_value=window)
        ):
            result = await service.compute_kind_summary(_USER_ID, "steps", zone=PARIS)

        assert result["total"] == 13297
        assert result["samples_count"] == 205
        assert result["last_value"] == 120
        assert result["last_sample_at"] == "2026-11-14T18:00:00+01:00"

    async def test_heart_rate_reports_the_average_over_its_counted_rows(self) -> None:
        service = _service()
        window = WindowSummary(
            counted=CountedAggregate(rows=3, total=214.0, minimum=70.0, maximum=73.0),
            samples=3,
            last_start=datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
            last_value=73,
        )
        with patch.object(
            service.sample_repo, "fetch_window_summary", AsyncMock(return_value=window)
        ):
            result = await service.compute_kind_summary(_USER_ID, "heart_rate", zone=PARIS)

        assert (result["avg"], result["min"], result["max"]) == (71.3, 70, 73)


class TestComputeOverview:
    """``compute_overview`` dispatches one ``compute_kind_summary`` per kind."""

    async def test_iterates_all_registered_kinds_in_the_person_s_zone(self) -> None:
        from src.domains.health_metrics.kinds import HEALTH_KINDS

        service = _service()
        fetch = AsyncMock(return_value=NOTHING)
        with patch.object(service.sample_repo, "fetch_window_summary", fetch):
            result = await service.compute_overview(_USER_ID, zone=PARIS)

        assert set(result) == set(HEALTH_KINDS)
        assert fetch.await_count == len(HEALTH_KINDS)
        assert {call.kwargs["kind"] for call in fetch.await_args_list} == set(HEALTH_KINDS)
