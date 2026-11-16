"""Unit tests for the Health Metrics agent tool pack (v1.17.2).

Single ``health_agent`` owns seven tools. Tests cover:

- Toggle gating: ``_check_user_toggle_or_error`` returning ``PERMISSION_DENIED``
  short-circuits before touching the service.
- Happy paths: each tool returns the expected ``structured_data`` shape.
- Empty-data / bootstrap modes surface honestly in the LLM message.
- Runtime-config failures propagate as ``UnifiedToolOutput``.
- Service exceptions get wrapped via ``handle_tool_exception``.
- Argument clamping (days / window_days).
- Window reading (``_read_window``) through the date contract: a date is a
  whole day in the user's timezone, an unreadable bound is refused, never
  replaced (ADR-318, ADR-148 amendment 2026-11-14).

Strategy: patch ``validate_runtime_config``, ``get_db_context``,
``_check_user_toggle_or_error``, and ``HealthMetricsService`` so the tool
functions run without Postgres or a real ToolRuntime.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = pytest.mark.unit


class _MockConfig:
    user_id = "01JA9XWN11N3J3BM0GZNB9FZKM"


@asynccontextmanager
async def _fake_db_context():
    yield MagicMock(name="AsyncSession")


def _patch_runtime():
    return patch(
        "src.domains.agents.tools.health_tools.validate_runtime_config",
        return_value=_MockConfig(),
    )


def _patch_db():
    return patch(
        "src.domains.agents.tools.health_tools.get_db_context",
        new=_fake_db_context,
    )


def _patch_toggle(return_value: UnifiedToolOutput | None = None):
    return patch(
        "src.domains.agents.tools.health_tools._check_user_toggle_or_error",
        new=AsyncMock(return_value=return_value),
    )


# =============================================================================
# _read_window — the date contract, in the user's timezone
# =============================================================================

PARIS = ZoneInfo("Europe/Paris")


def _patch_zone(zone: ZoneInfo = PARIS):
    return patch("src.domains.agents.tools.health_tools.resolve_user_timezone", return_value=zone)


class TestReadWindow:
    """The planner's bounds read by ``read_period`` (ADR-318), days cut at the user's midnight."""

    def test_omitted_bounds_stay_open(self) -> None:
        from src.domains.agents.tools.health_tools import _read_window

        with _patch_zone():
            assert _read_window(None, None, None) == (PARIS, None, None)

    def test_a_date_is_a_whole_local_day_and_the_last_one_counts(self) -> None:
        """« This week » from the 20th to the 26th covers the 26th too."""
        from src.domains.agents.tools.health_tools import _read_window

        with _patch_zone():
            window = _read_window(None, "2026-04-20", "2026-04-26")

        assert not isinstance(window, UnifiedToolOutput)
        zone, since, until = window
        assert since == datetime(2026, 4, 20, tzinfo=PARIS)
        assert until == datetime(2026, 4, 27, tzinfo=PARIS)
        assert since.astimezone(UTC) == datetime(2026, 4, 19, 22, 0, tzinfo=UTC)

    def test_an_instant_with_an_offset_is_taken_as_it_names(self) -> None:
        from src.domains.agents.tools.health_tools import _read_window

        with _patch_zone():
            window = _read_window(None, "2026-04-20T12:00:00+02:00", None)

        assert not isinstance(window, UnifiedToolOutput)
        assert window[1] == datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    @pytest.mark.parametrize("unreadable", ["not a date", "2026-13-01"])
    def test_an_unreadable_bound_is_refused_never_replaced(self, unreadable: str) -> None:
        from src.domains.agents.tools.health_tools import _read_window

        with _patch_zone():
            window = _read_window(None, unreadable, None)

        assert isinstance(window, UnifiedToolOutput)
        assert window.success is False
        assert window.error_code == "INVALID_INPUT"

    async def test_the_summary_tool_returns_the_refusal_without_reading(self) -> None:
        from src.domains.agents.tools.health_tools import get_steps_summary_tool

        service_mock = MagicMock()
        service_mock.compute_kind_summary = AsyncMock()
        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_steps_summary_tool.ainvoke({"time_min": "yesterday-ish"})

        assert result.success is False
        service_mock.compute_kind_summary.assert_not_called()

    async def test_the_summary_tool_reads_in_the_user_s_zone(self) -> None:
        from src.domains.agents.tools.health_tools import get_steps_summary_tool

        service_mock = MagicMock()
        service_mock.compute_kind_summary = AsyncMock(
            return_value={"kind": "steps", "unit": "steps", "total": None, "samples_count": 0}
        )
        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            _patch_zone(),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            await get_steps_summary_tool.ainvoke({"time_min": "2026-04-20"})

        kwargs = service_mock.compute_kind_summary.await_args.kwargs
        assert kwargs["zone"] == PARIS
        assert kwargs["time_min"] == datetime(2026, 4, 20, tzinfo=PARIS)
        assert kwargs["time_max"] is None


# =============================================================================
# get_steps_summary_tool
# =============================================================================


class TestGetStepsSummaryTool:
    async def test_returns_success_with_total(self) -> None:
        from src.domains.agents.tools.health_tools import get_steps_summary_tool

        service_mock = MagicMock()
        service_mock.compute_kind_summary = AsyncMock(
            return_value={
                "kind": "steps",
                "unit": "steps",
                "period": "day",
                "total": 8421,
                "samples_count": 12,
                "last_sample_at": "2026-04-22T10:00:00+00:00",
                "last_value": 310,
            }
        )

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_steps_summary_tool.ainvoke({})

        assert result.success is True
        assert "8421" in result.message
        assert result.structured_data["total"] == 8421

    async def test_empty_data_graceful(self) -> None:
        from src.domains.agents.tools.health_tools import get_steps_summary_tool

        service_mock = MagicMock()
        service_mock.compute_kind_summary = AsyncMock(
            return_value={
                "kind": "steps",
                "unit": "steps",
                "period": "day",
                "total": None,
                "samples_count": 0,
                "last_sample_at": None,
                "last_value": None,
            }
        )
        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_steps_summary_tool.ainvoke({})

        assert result.success is True
        assert "No steps data" in result.message

    async def test_toggle_off_returns_permission_denied(self) -> None:
        from src.domains.agents.tools.health_tools import get_steps_summary_tool

        denial = UnifiedToolOutput.failure(message="disabled", error_code="PERMISSION_DENIED")
        service_mock = MagicMock()
        service_mock.compute_kind_summary = AsyncMock()

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(denial),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_steps_summary_tool.ainvoke({})

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        service_mock.compute_kind_summary.assert_not_called()

    async def test_runtime_config_failure_propagates(self) -> None:
        from src.domains.agents.tools.health_tools import get_steps_summary_tool

        validation_error = UnifiedToolOutput.failure(
            message="user_id missing", error_code="configuration_error"
        )
        with patch(
            "src.domains.agents.tools.health_tools.validate_runtime_config",
            return_value=validation_error,
        ):
            result = await get_steps_summary_tool.ainvoke({})

        assert result.success is False
        assert result.error_code == "configuration_error"

    async def test_service_exception_wrapped(self) -> None:
        from src.domains.agents.tools.health_tools import get_steps_summary_tool

        service_mock = MagicMock()
        service_mock.compute_kind_summary = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_steps_summary_tool.ainvoke({})

        assert result.success is False
        assert result.error_code == "INTERNAL_ERROR"


# =============================================================================
# get_steps_daily_breakdown_tool
# =============================================================================


class TestGetStepsDailyBreakdownTool:
    async def test_returns_breakdown(self) -> None:
        from src.domains.agents.tools.health_tools import get_steps_daily_breakdown_tool

        breakdown = [
            {"date": "2026-04-20", "value": 7200},
            {"date": "2026-04-21", "value": 8100},
        ]
        service_mock = MagicMock()
        service_mock.compute_kind_daily_breakdown = AsyncMock(return_value=breakdown)

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_steps_daily_breakdown_tool.ainvoke({"days": 7})

        assert result.success is True
        assert result.structured_data["window"] == 7
        assert len(result.structured_data["days"]) == 2
        # The Response LLM only sees ``result.message`` — the per-day totals
        # must be inlined there, not only in structured_data. Regression
        # guard for the "Pas de données" bug fixed 2026-04-22.
        assert "2026-04-20: 7200" in result.message
        assert "2026-04-21: 8100" in result.message

    async def test_empty_breakdown_no_dangling_separator(self) -> None:
        """Empty breakdown surfaces a clean message, no dangling ``—``."""
        from src.domains.agents.tools.health_tools import get_steps_daily_breakdown_tool

        service_mock = MagicMock()
        service_mock.compute_kind_daily_breakdown = AsyncMock(return_value=[])

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_steps_daily_breakdown_tool.ainvoke({"days": 7})

        assert result.success is True
        assert "No steps data" in result.message
        assert "—" not in result.message

    async def test_clamps_out_of_range_days(self) -> None:
        from src.domains.agents.tools.health_tools import get_steps_daily_breakdown_tool

        service_mock = MagicMock()
        service_mock.compute_kind_daily_breakdown = AsyncMock(return_value=[])

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            await get_steps_daily_breakdown_tool.ainvoke({"days": 999})
            await get_steps_daily_breakdown_tool.ainvoke({"days": 0})

        call_args = [
            c.kwargs["days"] for c in service_mock.compute_kind_daily_breakdown.call_args_list
        ]
        assert call_args == [30, 1]


# =============================================================================
# compare_steps_to_baseline_tool
# =============================================================================


class TestCompareStepsToBaselineTool:
    async def test_rolling_success_message_mentions_delta(self) -> None:
        from src.domains.agents.tools.health_tools import compare_steps_to_baseline_tool

        service_mock = MagicMock()
        service_mock.compute_kind_baseline_delta = AsyncMock(
            return_value={
                "kind": "steps",
                "unit": "steps",
                "mode": "rolling",
                "baseline_value": 8500.0,
                "window_value": 5100.0,
                "delta_pct": -40.0,
                "window_days": 7,
                "days_available": 28,
            }
        )
        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await compare_steps_to_baseline_tool.ainvoke({"window_days": 7})

        assert result.success is True
        assert "-40.0%" in result.message
        assert "rolling" in result.message

    async def test_empty_mode_returns_helpful_message(self) -> None:
        from src.domains.agents.tools.health_tools import compare_steps_to_baseline_tool

        service_mock = MagicMock()
        service_mock.compute_kind_baseline_delta = AsyncMock(
            return_value={
                "kind": "steps",
                "unit": "steps",
                "mode": "empty",
                "baseline_value": None,
                "window_value": None,
                "delta_pct": None,
                "window_days": 7,
            }
        )
        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await compare_steps_to_baseline_tool.ainvoke({"window_days": 7})

        assert result.success is True
        assert "baseline" in result.message.lower()


# =============================================================================
# get_heart_rate_summary_tool
# =============================================================================


class TestGetHeartRateSummaryTool:
    async def test_returns_avg_min_max(self) -> None:
        from src.domains.agents.tools.health_tools import get_heart_rate_summary_tool

        service_mock = MagicMock()
        service_mock.compute_kind_summary = AsyncMock(
            return_value={
                "kind": "heart_rate",
                "unit": "bpm",
                "period": "day",
                "avg": 71.2,
                "min": 58,
                "max": 112,
                "samples_count": 288,
            }
        )
        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_heart_rate_summary_tool.ainvoke({})

        assert result.success is True
        assert "71.2" in result.message
        assert "58" in result.message

    async def test_empty_data_graceful(self) -> None:
        from src.domains.agents.tools.health_tools import get_heart_rate_summary_tool

        service_mock = MagicMock()
        service_mock.compute_kind_summary = AsyncMock(
            return_value={
                "kind": "heart_rate",
                "unit": "bpm",
                "period": "day",
                "avg": None,
                "min": None,
                "max": None,
                "samples_count": 0,
            }
        )
        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_heart_rate_summary_tool.ainvoke({})

        assert result.success is True
        assert "No heart rate data" in result.message


# =============================================================================
# compare_heart_rate_to_baseline_tool
# =============================================================================


class TestCompareHeartRateToBaselineTool:
    async def test_bootstrap_mode_exposed(self) -> None:
        from src.domains.agents.tools.health_tools import (
            compare_heart_rate_to_baseline_tool,
        )

        service_mock = MagicMock()
        service_mock.compute_kind_baseline_delta = AsyncMock(
            return_value={
                "kind": "heart_rate",
                "unit": "bpm",
                "mode": "bootstrap",
                "baseline_value": 68.0,
                "window_value": 74.5,
                "delta_pct": 9.6,
                "window_days": 7,
                "days_available": 4,
            }
        )
        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await compare_heart_rate_to_baseline_tool.ainvoke({"window_days": 7})

        assert result.success is True
        assert "+9.6%" in result.message
        assert "bootstrap" in result.message


# =============================================================================
# get_health_overview_tool
# =============================================================================


class TestGetHealthOverviewTool:
    async def test_surfaces_kinds_with_data(self) -> None:
        from src.domains.agents.tools.health_tools import get_health_overview_tool

        overview = {
            "steps": {"kind": "steps", "samples_count": 42, "total": 6200},
            "heart_rate": {
                "kind": "heart_rate",
                "samples_count": 12,
                "avg": 68.0,
                "min": 60,
                "max": 98,
            },
        }
        service_mock = MagicMock()
        service_mock.compute_overview = AsyncMock(return_value=overview)

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_health_overview_tool.ainvoke({})

        assert result.success is True
        assert "steps" in result.message
        assert "heart_rate" in result.message
        # Inlined figures: the Response LLM must see total/avg directly
        # in the message (regression guard for "Pas de données" bug).
        assert "total 6200" in result.message
        assert "avg 68.0" in result.message

    async def test_no_data_graceful(self) -> None:
        from src.domains.agents.tools.health_tools import get_health_overview_tool

        overview = {
            "steps": {"kind": "steps", "samples_count": 0},
            "heart_rate": {"kind": "heart_rate", "samples_count": 0},
        }
        service_mock = MagicMock()
        service_mock.compute_overview = AsyncMock(return_value=overview)

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await get_health_overview_tool.ainvoke({})

        assert result.success is True
        assert "No health data yet" in result.message


# =============================================================================
# detect_health_changes_tool
# =============================================================================


class TestDetectHealthChangesTool:
    async def test_reports_variations(self) -> None:
        from src.domains.agents.tools.health_tools import detect_health_changes_tool

        variations = [
            {
                "kind": "steps",
                "trend": "falling",
                "days": 4,
                "delta_pct": -35.0,
                "baseline_mode": "rolling",
                "notable": True,
            },
            {"kind": "steps", "event": "inactivity_streak", "days": 4},
        ]
        service_mock = MagicMock()
        service_mock.detect_all_variations = AsyncMock(return_value=variations)

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await detect_health_changes_tool.ainvoke({"window_days": 7})

        assert result.success is True
        assert "2 notable change" in result.message
        # Regression guard: trend + event entries inlined in the message
        # so the Response LLM can surface them factually.
        assert "steps falling for 4d" in result.message
        assert "-35.0%" in result.message
        assert "event=inactivity_streak" in result.message

    async def test_variations_without_trend_or_event_no_dangling_separator(self) -> None:
        """Defensive: unknown-shape variations don't leave a dangling ``—``."""
        from src.domains.agents.tools.health_tools import detect_health_changes_tool

        variations = [{"kind": "steps", "unknown_shape": True}]
        service_mock = MagicMock()
        service_mock.detect_all_variations = AsyncMock(return_value=variations)

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await detect_health_changes_tool.ainvoke({"window_days": 7})

        assert result.success is True
        assert "1 notable change" in result.message
        # Count is surfaced but no dangling separator when entries are empty.
        assert "—" not in result.message

    async def test_no_variations(self) -> None:
        from src.domains.agents.tools.health_tools import detect_health_changes_tool

        service_mock = MagicMock()
        service_mock.detect_all_variations = AsyncMock(return_value=[])

        with (
            _patch_runtime(),
            _patch_db(),
            _patch_toggle(None),
            patch(
                "src.domains.health_metrics.service.HealthMetricsService",
                return_value=service_mock,
            ),
        ):
            result = await detect_health_changes_tool.ainvoke({"window_days": 7})

        assert result.success is True
        assert "No notable health variations" in result.message
