"""
Unit tests for the forecast tools' date reading (``weather_dates.calculate_target_date``).

The published contract is an ISO date or datetime (the model resolves relative
expressions from its context). The tool still reads, without publishing them,
the English words the pipeline planner may emit (``today``, ``tomorrow``,
``in N days``, ``this week``) and localized absolute dates. Anything else is
REFUSED: until 2026-09-23 it fell back to today in silence, and « demain » sent
by a ReAct loop came back as a successful forecast for the wrong day.

Tests use a fixed timezone so they never depend on the machine's.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

TEST_TIMEZONE = "UTC"


def _get_test_today() -> date:
    """Today's date in the test timezone (UTC)."""
    return datetime.now(UTC).date()


def _offset(ref: str | None, tz: str = TEST_TIMEZONE) -> int:
    """Days from today the tool reads for ``ref``."""
    from src.domains.agents.tools.weather_dates import calculate_target_date

    return calculate_target_date(ref, tz)[1]


class TestNoDate:
    """No date asked means today."""

    def test_none_returns_zero(self) -> None:
        assert _offset(None) == 0

    def test_empty_string_returns_zero(self) -> None:
        assert _offset("") == 0


class TestLenientEnglishReadings:
    """English words the pipeline planner may emit — read, never published."""

    def test_today_references(self) -> None:
        for ref in ["today", "now", "TODAY"]:
            assert _offset(ref) == 0, f"Failed for '{ref}'"

    def test_tomorrow_references(self) -> None:
        for ref in ["tomorrow", "Tomorrow", "TOMORROW"]:
            assert _offset(ref) == 1, f"Failed for '{ref}'"

    def test_day_after_tomorrow_references(self) -> None:
        for ref in ["after tomorrow", "day after tomorrow"]:
            assert _offset(ref) == 2, f"Failed for '{ref}'"

    def test_in_x_days(self) -> None:
        assert _offset("in 1 day") == 1
        assert _offset("in 2 days") == 2
        assert _offset("in 3 days") == 3
        assert _offset("in 5 days") == 5

    def test_week_references_return_zero(self) -> None:
        for ref in ["this week", "week"]:
            assert _offset(ref) == 0, f"Failed for '{ref}'"

    def test_whitespace_handling(self) -> None:
        assert _offset("  tomorrow  ") == 1
        assert _offset("\ttomorrow\n") == 1


class TestIsoDate:
    """ISO dates (YYYY-MM-DD) — the published contract."""

    def test_iso_date_today(self) -> None:
        assert _offset(_get_test_today().strftime("%Y-%m-%d")) == 0

    def test_iso_date_tomorrow(self) -> None:
        tomorrow = _get_test_today() + timedelta(days=1)
        assert _offset(tomorrow.strftime("%Y-%m-%d")) == 1

    def test_iso_date_five_days_ahead(self) -> None:
        future = _get_test_today() + timedelta(days=5)
        assert _offset(future.strftime("%Y-%m-%d")) == 5

    def test_iso_date_past_returns_zero(self) -> None:
        """Past weather cannot be requested: a past date reads as today."""
        past = _get_test_today() - timedelta(days=5)
        assert _offset(past.strftime("%Y-%m-%d")) == 0

    def test_far_future_date(self) -> None:
        """The offset is read whole; the tool enforces the forecast limit itself."""
        far_future = _get_test_today() + timedelta(days=30)
        assert _offset(far_future.strftime("%Y-%m-%d")) == 30


class TestIsoDatetime:
    """ISO datetimes, as calendar events carry them."""

    def test_iso_datetime_with_timezone_offset(self) -> None:
        tomorrow = _get_test_today() + timedelta(days=1)
        assert _offset(f"{tomorrow.strftime('%Y-%m-%d')}T14:00:00+01:00") == 1

    def test_iso_datetime_with_z_suffix(self) -> None:
        in_3_days = _get_test_today() + timedelta(days=3)
        assert _offset(f"{in_3_days.strftime('%Y-%m-%d')}T09:30:00Z") == 3

    def test_iso_datetime_with_milliseconds(self) -> None:
        in_2_days = _get_test_today() + timedelta(days=2)
        assert _offset(f"{in_2_days.strftime('%Y-%m-%d')}T15:45:30.123456+02:00") == 2

    def test_iso_datetime_extracts_date_only(self) -> None:
        tomorrow = _get_test_today() + timedelta(days=1)
        morning = f"{tomorrow.strftime('%Y-%m-%d')}T08:00:00+01:00"
        evening = f"{tomorrow.strftime('%Y-%m-%d')}T20:00:00+01:00"
        assert _offset(morning) == _offset(evening) == 1

    def test_iso_datetime_negative_offset_timezone(self) -> None:
        in_4_days = _get_test_today() + timedelta(days=4)
        assert _offset(f"{in_4_days.strftime('%Y-%m-%d')}T10:00:00-05:00") == 4


class TestAnUnreadableReferenceIsRefused:
    """2026-09-23: « demain » fell back to TODAY in silence and the loop served
    the wrong day as a success. A value the tool cannot read is refused."""

    @pytest.mark.parametrize("ref", ["demain", "mañana", "morgen", "gibberish", "next month"])
    def test_an_unreadable_reference_raises(self, ref: str) -> None:
        from src.domains.agents.tools.weather_dates import (
            UnreadableDateError,
            calculate_target_date,
        )

        with pytest.raises(UnreadableDateError) as caught:
            calculate_target_date(ref, TEST_TIMEZONE)
        assert caught.value.reference == ref

    def test_the_refusal_says_what_to_send_and_what_today_is(self) -> None:
        from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
        from src.core.time_utils import now_in_timezone
        from src.domains.agents.tools.common import ToolErrorCode
        from src.domains.agents.tools.weather_dates import unreadable_date_result

        result = unreadable_date_result("demain", DEFAULT_USER_DISPLAY_TIMEZONE)
        today = now_in_timezone(DEFAULT_USER_DISPLAY_TIMEZONE).date().isoformat()
        assert result["success"] is False
        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
        assert "'demain'" in result["message"] and "YYYY-MM-DD" in result["message"]
        assert today in result["message"] and DEFAULT_USER_DISPLAY_TIMEZONE in result["message"]


def test_the_manifest_publishes_the_iso_contract() -> None:
    from src.domains.agents.weather.catalogue_manifests import _DATE_PARAM

    assert "YYYY-MM-DD" in _DATE_PARAM.description
    assert "temporal reference" not in _DATE_PARAM.description


@pytest.mark.parametrize("name", ["get_weather_forecast_tool", "get_hourly_forecast_tool"])
def test_the_react_tool_schema_publishes_the_same_contract(name: str) -> None:
    """The ReAct loop reads the tool's own schema, not the manifest. On 2026-09-23 it
    listed « 'demain', 'après-demain', 'dans 2 jours' » as examples — words the
    implementation never read — and the model sent exactly that."""
    from src.domains.agents.tools import weather_tools
    from src.domains.agents.weather.catalogue_manifests import FORECAST_DATE_DESCRIPTION

    description = getattr(weather_tools, name).args_schema.model_fields["date"].description
    assert description is not None and description.startswith(FORECAST_DATE_DESCRIPTION)
    assert "demain" not in description and "emporal reference" not in description
