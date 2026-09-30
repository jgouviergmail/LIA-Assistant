"""SchedulerSettings — the weather routine's rule is coherent or the app refuses to boot.

A weather routine announces a change due within its horizon (ADR-322
amendment 2026-09-29). Checked less often than the horizon is long, the hours
between the end of one check's window and the start of the next are read by
nobody: a shower there is never announced.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config.scheduler import SchedulerSettings
from src.core.constants import GOOGLE_WEATHER_FORECAST_PAGE_SIZE

pytestmark = pytest.mark.unit

_ENV_VARS = (
    "SCHEDULED_ACTIONS_WEATHER_CHECK_MINUTES",
    "SCHEDULED_ACTIONS_WEATHER_HORIZON_HOURS",
    "SCHEDULED_ACTIONS_WEATHER_MIN_PRECIPITATION_PERCENT",
)


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


class TestTheWeatherRule:
    def test_the_owner_decided_defaults(self) -> None:
        s = SchedulerSettings()
        assert s.scheduled_actions_weather_horizon_hours == 4
        assert s.scheduled_actions_weather_min_precipitation_percent == 50

    def test_a_check_every_horizon_leaves_no_hour_unread(self) -> None:
        s = SchedulerSettings(
            scheduled_actions_weather_horizon_hours=2, scheduled_actions_weather_check_minutes=120
        )
        assert s.scheduled_actions_weather_check_minutes == 120

    def test_checks_further_apart_than_the_horizon_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="SCHEDULED_ACTIONS_WEATHER_CHECK_MINUTES"):
            SchedulerSettings(
                scheduled_actions_weather_horizon_hours=2,
                scheduled_actions_weather_check_minutes=121,
            )

    @pytest.mark.parametrize("hours", [0, GOOGLE_WEATHER_FORECAST_PAGE_SIZE])
    def test_the_horizon_is_bounded_to_one_forecast_page(self, hours: int) -> None:
        # The horizon plus the hour under way must fit ONE billed page.
        with pytest.raises(ValidationError):
            SchedulerSettings(scheduled_actions_weather_horizon_hours=hours)

    @pytest.mark.parametrize("percent", [-1, 100])
    def test_a_threshold_nothing_could_pass_is_refused(self, percent: int) -> None:
        # Strictly above 100 % is never; below 0 % is not a probability.
        with pytest.raises(ValidationError):
            SchedulerSettings(scheduled_actions_weather_min_precipitation_percent=percent)
