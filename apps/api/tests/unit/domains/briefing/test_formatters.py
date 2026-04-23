"""Unit tests for briefing/formatters.py — pure functions, no I/O."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.formatters import (
    WEATHER_EMOJI_DEFAULT,
    WEATHER_EMOJI_MAP,
    _detect_forecast_alert,
    _format_event_time,
    _next_birthday_occurrence,
    format_agenda_event,
    format_email_item,
    format_reminder_item,
    format_weather_data,
    make_health_summary_item,
    upcoming_birthdays_from_connections,
)

PARIS = ZoneInfo("Europe/Paris")
NEW_YORK = ZoneInfo("America/New_York")


# =============================================================================
# format_weather_data
# =============================================================================


@pytest.mark.unit
class TestFormatWeatherData:
    def test_typical_clear_weather(self) -> None:
        current = {
            "main": {"temp": 18.4},
            "weather": [{"main": "Clear", "description": "ciel dégagé"}],
        }
        forecast = {"list": []}
        out = format_weather_data(current=current, forecast=forecast, city="Paris", user_tz=PARIS)
        assert out.temperature_c == 18.4
        assert out.condition_code == "Clear"
        assert out.icon_emoji == WEATHER_EMOJI_MAP["Clear"]
        assert out.description == "Ciel dégagé"  # capitalized
        assert out.location_city == "Paris"
        assert out.forecast_alert is None

    def test_unknown_condition_falls_back_to_default_emoji(self) -> None:
        current = {
            "main": {"temp": 12},
            "weather": [{"main": "Wibble", "description": "weird stuff"}],
        }
        out = format_weather_data(current=current, forecast={"list": []}, city=None, user_tz=PARIS)
        assert out.icon_emoji == WEATHER_EMOJI_DEFAULT

    def test_missing_weather_array_uses_unknown(self) -> None:
        out = format_weather_data(
            current={"main": {"temp": 5}, "weather": []},
            forecast={"list": []},
            city=None,
            user_tz=PARIS,
        )
        assert out.condition_code == "Unknown"
        assert out.description == "Unknown"


# =============================================================================
# _detect_forecast_alert
# =============================================================================


@pytest.mark.unit
class TestDetectForecastAlert:
    def test_returns_none_when_currently_raining(self) -> None:
        current = {"weather": [{"main": "Rain"}]}
        forecast = {"list": [{"dt": 0, "weather": [{"main": "Rain"}]}]}
        assert _detect_forecast_alert(current=current, forecast=forecast, user_tz=PARIS) is None

    def test_emits_alert_when_rain_appears_in_forecast(self) -> None:
        current = {"weather": [{"main": "Clear"}]}
        # 16:00 Paris = epoch
        ts = int(datetime(2026, 1, 1, 16, 0, tzinfo=PARIS).timestamp())
        forecast = {"list": [{"dt": ts, "weather": [{"main": "Rain"}]}]}
        out = _detect_forecast_alert(current=current, forecast=forecast, user_tz=PARIS)
        assert out is not None
        assert "16:00" in out
        assert "Rain" in out

    def test_no_alert_for_clouds_only(self) -> None:
        current = {"weather": [{"main": "Clear"}]}
        forecast = {"list": [{"dt": 0, "weather": [{"main": "Clouds"}]}]}
        assert _detect_forecast_alert(current=current, forecast=forecast, user_tz=PARIS) is None


# =============================================================================
# _format_event_time
# =============================================================================


@pytest.mark.unit
class TestFormatEventTime:
    def test_today_event_returns_hh_mm(self) -> None:
        now_local = datetime.now(PARIS)
        iso = now_local.replace(hour=14, minute=0, second=0, microsecond=0).isoformat()
        out = _format_event_time({"dateTime": iso}, PARIS)
        assert out == "14:00"

    def test_other_day_event_returns_full_date(self) -> None:
        # Tomorrow 09:00 Paris
        tomorrow = datetime.now(PARIS).date().toordinal() + 1
        d = date.fromordinal(tomorrow)
        iso = datetime(d.year, d.month, d.day, 9, 0, tzinfo=PARIS).isoformat()
        out = _format_event_time({"dateTime": iso}, PARIS)
        assert out == f"{d.isoformat()} 09:00"

    def test_all_day_event(self) -> None:
        out = _format_event_time({"date": "2026-04-23"}, PARIS)
        assert out == "2026-04-23 (all day)"

    def test_naive_datetime_with_microsoft_timezone_field(self) -> None:
        # 10:00 Europe/Paris naive → Paris local
        out = _format_event_time(
            {"dateTime": "2026-04-23T10:00:00", "timeZone": "Europe/Paris"},
            NEW_YORK,
        )
        # In NEW_YORK, 10:00 Paris = 04:00 NY (CEST in April: Paris UTC+2, NY UTC-4 → 6 h delta)
        assert out.endswith("04:00")

    def test_missing_field_returns_question_mark(self) -> None:
        assert _format_event_time(None, PARIS) == "?"
        assert _format_event_time({}, PARIS) == "?"


# =============================================================================
# format_agenda_event
# =============================================================================


@pytest.mark.unit
def test_format_agenda_event_extracts_title_and_location() -> None:
    now_local = datetime.now(PARIS)
    raw = {
        "summary": "Réunion Marc",
        "location": "Bureau",
        "start": {
            "dateTime": now_local.replace(hour=14, minute=0, second=0, microsecond=0).isoformat(),
        },
    }
    item = format_agenda_event(raw, PARIS)
    assert item.title == "Réunion Marc"
    assert item.location == "Bureau"
    assert item.start_local == "14:00"


@pytest.mark.unit
def test_format_agenda_event_falls_back_to_untitled() -> None:
    item = format_agenda_event({}, PARIS)
    assert item.title == "Untitled"
    assert item.location is None
    assert item.start_local == "?"


# =============================================================================
# format_email_item
# =============================================================================


@pytest.mark.unit
class TestFormatEmailItem:
    def test_today_message(self) -> None:
        # Today 09:30 Paris in epoch ms
        now_local = datetime.now(PARIS).replace(hour=9, minute=30, second=0, microsecond=0)
        epoch_ms = int(now_local.timestamp() * 1000)
        item = format_email_item(
            {
                "from": "Sophie <sophie@acme.com>",
                "subject": "Brief Q2",
                "internalDate": str(epoch_ms),
            },
            PARIS,
        )
        assert (item.sender_name or "").startswith("Sophie")
        assert item.sender_email == "sophie@acme.com"
        assert item.subject == "Brief Q2"
        assert item.received_local == "09:30"

    def test_missing_fields_use_fallbacks(self) -> None:
        item = format_email_item({}, PARIS)
        # Both sender_name and sender_email are None when the From header is missing.
        assert item.sender_name is None
        assert item.sender_email is None
        assert item.subject == "(no subject)"
        assert item.received_local == "?"


# =============================================================================
# format_reminder_item
# =============================================================================


@pytest.mark.unit
def test_format_reminder_item_today() -> None:
    now_utc = datetime.now(UTC).replace(microsecond=0)
    reminder = SimpleNamespace(content="Call mom", trigger_at=now_utc)
    item = format_reminder_item(reminder, PARIS)
    assert item.content == "Call mom"
    # Should be HH:MM (today)
    assert ":" in item.trigger_at_local
    assert "tomorrow" not in item.trigger_at_local


@pytest.mark.unit
def test_format_reminder_item_tomorrow() -> None:
    from datetime import timedelta as td

    now_utc = datetime.now(UTC).replace(microsecond=0) + td(days=1)
    reminder = SimpleNamespace(content="Wake up early", trigger_at=now_utc)
    item = format_reminder_item(reminder, PARIS)
    # New format: "HH:MM tomorrow" (time first, then relative day marker).
    assert item.trigger_at_local.endswith(" tomorrow")
    assert ":" in item.trigger_at_local


# =============================================================================
# Birthdays
# =============================================================================


@pytest.mark.unit
class TestNextBirthdayOccurrence:
    def test_future_in_year(self) -> None:
        today = date(2026, 1, 1)
        out = _next_birthday_occurrence(today, 6, 15)
        assert out == date(2026, 6, 15)

    def test_past_rolls_to_next_year(self) -> None:
        today = date(2026, 6, 30)
        out = _next_birthday_occurrence(today, 6, 15)
        assert out == date(2027, 6, 15)

    def test_today_returns_today(self) -> None:
        today = date(2026, 6, 15)
        out = _next_birthday_occurrence(today, 6, 15)
        assert out == today

    def test_feb_29_in_non_leap_falls_to_28(self) -> None:
        today = date(2026, 1, 1)  # 2026 is not leap
        out = _next_birthday_occurrence(today, 2, 29)
        assert out == date(2026, 2, 28)


@pytest.mark.unit
class TestUpcomingBirthdaysFromConnections:
    def test_extracts_birthdays_within_horizon(self) -> None:
        today = date(2026, 6, 1)
        connections = [
            {
                "names": [{"displayName": "Pauline", "metadata": {"primary": True}}],
                "birthdays": [{"date": {"month": 6, "day": 4}}],
            },
            {
                "names": [{"displayName": "Marc", "metadata": {"primary": True}}],
                "birthdays": [{"date": {"month": 12, "day": 25}}],  # outside 14-day horizon
            },
        ]
        out = upcoming_birthdays_from_connections(
            connections, horizon_days=14, max_items=5, today=today
        )
        assert len(out) == 1
        assert out[0].contact_name == "Pauline"
        assert out[0].days_until == 3
        assert out[0].date_iso == "--06-04"

    def test_sorts_by_days_until_ascending(self) -> None:
        today = date(2026, 6, 1)
        connections = [
            {
                "names": [{"displayName": "Bob"}],
                "birthdays": [{"date": {"month": 6, "day": 10}}],
            },
            {
                "names": [{"displayName": "Alice"}],
                "birthdays": [{"date": {"month": 6, "day": 3}}],
            },
        ]
        out = upcoming_birthdays_from_connections(
            connections, horizon_days=14, max_items=5, today=today
        )
        assert [b.contact_name for b in out] == ["Alice", "Bob"]

    def test_year_known_uses_full_iso(self) -> None:
        today = date(2026, 6, 1)
        connections = [
            {
                "names": [{"displayName": "Alice"}],
                "birthdays": [{"date": {"year": 1990, "month": 6, "day": 3}}],
            }
        ]
        out = upcoming_birthdays_from_connections(
            connections, horizon_days=14, max_items=5, today=today
        )
        assert out[0].date_iso == "1990-06-03"

    def test_skips_contacts_without_name(self) -> None:
        today = date(2026, 6, 1)
        connections = [
            {"names": [], "birthdays": [{"date": {"month": 6, "day": 3}}]},
        ]
        out = upcoming_birthdays_from_connections(
            connections, horizon_days=14, max_items=5, today=today
        )
        assert out == []

    def test_skips_birthdays_without_month_or_day(self) -> None:
        today = date(2026, 6, 1)
        connections = [
            {
                "names": [{"displayName": "Alice"}],
                "birthdays": [{"date": {"year": 1990}}],
            }
        ]
        out = upcoming_birthdays_from_connections(
            connections, horizon_days=14, max_items=5, today=today
        )
        assert out == []

    def test_caps_to_max_items(self) -> None:
        today = date(2026, 6, 1)
        connections = [
            {
                "names": [{"displayName": f"Person {i}"}],
                "birthdays": [{"date": {"month": 6, "day": 1 + i}}],
            }
            for i in range(10)
        ]
        out = upcoming_birthdays_from_connections(
            connections, horizon_days=14, max_items=3, today=today
        )
        assert len(out) == 3


# =============================================================================
# make_health_summary_item
# =============================================================================


@pytest.mark.unit
class TestMakeHealthSummaryItem:
    def test_builds_steps_item_with_today_and_avg(self) -> None:
        item = make_health_summary_item(
            kind="steps",
            value_today=7243.0,
            value_avg_window=6100.0,
            unit="steps",
            window_days=14,
            days_with_data=10,
        )
        assert item.kind == "steps"
        assert item.value_today == 7243.0
        assert item.value_avg_window == 6100.0
        assert item.unit == "steps"
        assert item.window_days == 14
        assert item.days_with_data == 10

    def test_builds_heart_rate_item_with_nullable_today(self) -> None:
        item = make_health_summary_item(
            kind="heart_rate",
            value_today=None,
            value_avg_window=68.0,
            unit="bpm",
            window_days=14,
            days_with_data=3,
        )
        assert item.kind == "heart_rate"
        assert item.value_today is None
        assert item.value_avg_window == 68.0

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValueError, match="Unsupported health kind"):
            make_health_summary_item(
                kind="blood_pressure",
                value_today=120.0,
                value_avg_window=118.0,
                unit="mmHg",
                window_days=14,
                days_with_data=5,
            )
