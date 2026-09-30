"""Unit tests for briefing/formatters.py — pure functions, no I/O."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import RecurrenceSpec
from src.domains.briefing.formatters import (
    WEATHER_EMOJI_DEFAULT,
    WEATHER_EMOJI_MAP,
    ForecastAlertRule,
    _format_event_time,
    detect_forecast_alert,
    format_agenda_event,
    format_email_item,
    format_reminder_item,
    format_weather_data,
    make_health_summary_item,
    upcoming_birthdays_from_connections,
)
from src.domains.briefing.schemas import ForecastAlert, ForecastAlertKind, WeatherData

# Birthday computation moved to the neutral connectors home (P7) — the
# private occurrence helper is imported from its new module; the public
# ``upcoming_birthdays_from_connections`` stays importable from formatters
# (re-export guarded by tests/unit/domains/connectors/test_birthdays.py).
from src.domains.connectors.birthdays import _next_birthday_occurrence  # noqa: E402

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
        out = format_weather_data(
            current=current,
            forecast=forecast,
            city="Paris",
            user_tz=PARIS,
            daily_forecast_days=5,
            now=ALERT_NOW,
        )
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
        out = format_weather_data(
            current=current,
            forecast={"list": []},
            city=None,
            user_tz=PARIS,
            daily_forecast_days=5,
            now=ALERT_NOW,
        )
        assert out.icon_emoji == WEATHER_EMOJI_DEFAULT

    def test_missing_weather_array_uses_unknown(self) -> None:
        out = format_weather_data(
            current={"main": {"temp": 5}, "weather": []},
            forecast={"list": []},
            city=None,
            user_tz=PARIS,
            daily_forecast_days=5,
            now=ALERT_NOW,
        )
        assert out.condition_code == "Unknown"
        assert out.description == "Unknown"


# =============================================================================
# _detect_forecast_alert
# =============================================================================


#: The reference instant of the detection tests: 13:00 in Paris.
ALERT_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
FOUR_HOURS = ForecastAlertRule(horizon=timedelta(hours=4))
CLEAR = {"weather": [{"main": "Clear"}]}


def _slot(at: datetime, main: str, *, pop: object = None) -> dict[str, object]:
    """One OWM-shaped forecast slot."""
    entry: dict[str, object] = {"dt": int(at.timestamp()), "weather": [{"main": main}]}
    if pop is not None:
        entry["pop"] = pop
    return entry


def _detect(
    *slots: dict[str, object],
    current: dict[str, object] = CLEAR,
    rule: ForecastAlertRule = FOUR_HOURS,
) -> ForecastAlert | None:
    return detect_forecast_alert(
        current=current, forecast={"list": list(slots)}, user_tz=PARIS, now=ALERT_NOW, rule=rule
    )


@pytest.mark.unit
class TestDetectForecastAlert:
    def test_returns_none_when_currently_raining(self) -> None:
        current = {"weather": [{"main": "Rain"}]}
        assert _detect(_slot(ALERT_NOW, "Rain"), current=current) is None

    def test_emits_structured_alert_when_rain_appears_in_forecast(self) -> None:
        out = _detect(_slot(datetime(2026, 1, 1, 16, 0, tzinfo=PARIS), "Rain"))
        assert out is not None
        assert out.kind is ForecastAlertKind.RAIN
        assert out.time == "16:00"
        assert out.starts_at == datetime(2026, 1, 1, 15, 0, tzinfo=UTC)

    def test_maps_thunderstorm_to_enum(self) -> None:
        out = _detect(_slot(datetime(2026, 1, 1, 15, 30, tzinfo=PARIS), "Thunderstorm"))
        assert out is not None
        assert out.kind is ForecastAlertKind.THUNDERSTORM

    def test_no_alert_for_clouds_only(self) -> None:
        assert _detect(_slot(ALERT_NOW, "Clouds")) is None


@pytest.mark.unit
class TestTheAlertHorizon:
    """A change is announced only when it is due within the rule's horizon."""

    def test_the_last_instant_of_the_horizon_is_inside_it(self) -> None:
        assert _detect(_slot(ALERT_NOW + timedelta(hours=4), "Rain")) is not None

    def test_a_change_past_the_horizon_is_no_alert(self) -> None:
        # The defect: a 5-day forecast read whole announced a rain four days away.
        later = ALERT_NOW + timedelta(hours=4, seconds=1)
        assert _detect(_slot(later, "Rain"), _slot(ALERT_NOW + timedelta(days=4), "Rain")) is None

    def test_a_slot_past_the_horizon_never_hides_one_inside_it(self) -> None:
        # Providers list slots chronologically, but nothing is assumed.
        out = _detect(
            _slot(ALERT_NOW + timedelta(hours=9), "Snow"),
            _slot(ALERT_NOW + timedelta(hours=2), "Rain"),
        )
        assert out is not None
        assert out.kind is ForecastAlertKind.RAIN

    def test_the_hour_under_way_is_stated_from_now_never_in_the_past(self) -> None:
        # Google's first hourly slot starts at the top of the CURRENT hour.
        out = _detect(_slot(ALERT_NOW - timedelta(minutes=37), "Rain"))
        assert out is not None
        assert out.starts_at == ALERT_NOW
        assert out.time == "13:00"

    def test_an_unreadable_slot_is_skipped_not_fatal(self) -> None:
        out = _detect(
            {"weather": [{"main": "Rain"}]},
            {"dt": "soon", "weather": [{"main": "Rain"}]},
            {"dt": 1, "weather": []},
            _slot(ALERT_NOW + timedelta(hours=1), "Snow"),
        )
        assert out is not None
        assert out.kind is ForecastAlertKind.SNOW


@pytest.mark.unit
class TestTheProbabilityThreshold:
    """With a threshold, a slot counts only when its probability is STRICTLY above it."""

    RULE = ForecastAlertRule(horizon=timedelta(hours=4), min_precipitation_percent=50)

    @pytest.mark.parametrize(
        ("pop", "fires"),
        [(0.5, False), (0.51, True), (0.49, False), (1, True), (0, False)],
    )
    def test_strictly_above_the_threshold(self, pop: float, fires: bool) -> None:
        out = _detect(_slot(ALERT_NOW + timedelta(hours=1), "Rain", pop=pop), rule=self.RULE)
        assert (out is not None) is fires

    def test_a_slot_with_no_probability_is_not_likely(self) -> None:
        assert _detect(_slot(ALERT_NOW + timedelta(hours=1), "Rain"), rule=self.RULE) is None

    @pytest.mark.parametrize("pop", ["0.9", True, None])
    def test_an_unreadable_probability_is_not_likely(self, pop: object) -> None:
        entry = _slot(ALERT_NOW + timedelta(hours=1), "Rain")
        entry["pop"] = pop
        assert _detect(entry, rule=self.RULE) is None

    def test_an_unlikely_slot_never_hides_a_likely_one(self) -> None:
        out = _detect(
            _slot(ALERT_NOW + timedelta(hours=1), "Rain", pop=0.2),
            _slot(ALERT_NOW + timedelta(hours=2), "Rain", pop=0.8),
            rule=self.RULE,
        )
        assert out is not None
        assert out.starts_at == ALERT_NOW + timedelta(hours=2)
        assert out.precipitation_percent == 80

    @pytest.mark.parametrize(("pop", "percent"), [(1.7, 100), (-0.2, 0)])
    def test_an_out_of_range_probability_is_clamped_never_fatal(
        self, pop: float, percent: int
    ) -> None:
        # The card reads the same detector: a bad provider value must not
        # fail the whole weather card on the alert's 0-100 bounds.
        out = _detect(_slot(ALERT_NOW + timedelta(hours=1), "Rain", pop=pop))
        assert out is not None
        assert out.precipitation_percent == percent

    @pytest.mark.parametrize("pop", [float("nan"), float("inf")])
    def test_a_non_finite_probability_is_unknown(self, pop: float) -> None:
        out = _detect(_slot(ALERT_NOW + timedelta(hours=1), "Rain", pop=pop))
        assert out is not None
        assert out.precipitation_percent is None
        assert (
            _detect(_slot(ALERT_NOW + timedelta(hours=1), "Rain", pop=pop), rule=self.RULE) is None
        )

    def test_the_probability_is_carried_even_without_a_threshold(self) -> None:
        out = _detect(_slot(ALERT_NOW + timedelta(hours=1), "Rain", pop=0.3))
        assert out is not None
        assert out.precipitation_percent == 30


@pytest.mark.unit
class TestTheWatchedKinds:
    """A rule watching some kinds reads the forecast for THOSE kinds only."""

    SNOW_ONLY = ForecastAlertRule(
        horizon=timedelta(hours=4), kinds=frozenset({ForecastAlertKind.SNOW})
    )

    def test_an_earlier_unwatched_kind_never_hides_a_watched_one(self) -> None:
        out = _detect(
            _slot(ALERT_NOW + timedelta(hours=1), "Rain"),
            _slot(ALERT_NOW + timedelta(hours=3), "Snow"),
            rule=self.SNOW_ONLY,
        )
        assert out is not None
        assert out.kind is ForecastAlertKind.SNOW

    def test_an_unwatched_kind_falling_now_is_not_already_happening(self) -> None:
        out = _detect(
            _slot(ALERT_NOW + timedelta(hours=2), "Snow"),
            current={"weather": [{"main": "Rain"}]},
            rule=self.SNOW_ONLY,
        )
        assert out is not None

    def test_a_watched_kind_falling_now_is_already_happening(self) -> None:
        out = _detect(
            _slot(ALERT_NOW + timedelta(hours=2), "Snow"),
            current={"weather": [{"main": "Snow"}]},
            rule=self.SNOW_ONLY,
        )
        assert out is None

    def test_no_watched_kind_in_the_forecast_is_no_alert(self) -> None:
        assert _detect(_slot(ALERT_NOW + timedelta(hours=1), "Rain"), rule=self.SNOW_ONLY) is None


@pytest.mark.unit
class TestTheCardsAlert:
    """The card keeps its documented contract: the next change within 24 hours."""

    @staticmethod
    def _card(*slots: dict[str, object]) -> WeatherData:
        return format_weather_data(
            current={"main": {"temp": 10}, "weather": [{"main": "Clear"}]},
            forecast={"list": list(slots)},
            city=None,
            user_tz=PARIS,
            daily_forecast_days=5,
            now=ALERT_NOW,
        )

    def test_a_change_tomorrow_morning_is_on_the_card(self) -> None:
        out = self._card(_slot(ALERT_NOW + timedelta(hours=20), "Rain", pop=0.1))
        assert out.forecast_alert is not None
        assert out.forecast_alert.time == "09:00"

    def test_a_change_in_three_days_is_not_announced_at_an_hour_of_today(self) -> None:
        out = self._card(_slot(ALERT_NOW + timedelta(days=3), "Rain"))
        assert out.forecast_alert is None


# =============================================================================
# _format_event_time
# =============================================================================


@pytest.mark.unit
class TestFormatEventTime:
    def test_today_event_returns_hh_mm(self) -> None:
        now_local = datetime.now(PARIS)
        iso = now_local.replace(hour=14, minute=0, second=0, microsecond=0).isoformat()
        assert _format_event_time({"dateTime": iso}, PARIS, "fr") == "14:00"

    def test_tomorrow_event_uses_localized_word_french(self) -> None:
        tomorrow = datetime.now(PARIS).date() + timedelta(days=1)
        iso = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, 0, tzinfo=PARIS).isoformat()
        assert _format_event_time({"dateTime": iso}, PARIS, "fr") == "09:00 demain"

    def test_tomorrow_event_uses_localized_word_english(self) -> None:
        tomorrow = datetime.now(PARIS).date() + timedelta(days=1)
        iso = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, 0, tzinfo=PARIS).isoformat()
        assert _format_event_time({"dateTime": iso}, PARIS, "en") == "09:00 tomorrow"

    def test_other_day_uses_locale_date_format_french(self) -> None:
        # +5 days @ 09:00 Paris — French dd/mm/yyyy with year.
        target = datetime.now(PARIS).date() + timedelta(days=5)
        iso = datetime(target.year, target.month, target.day, 9, 0, tzinfo=PARIS).isoformat()
        out = _format_event_time({"dateTime": iso}, PARIS, "fr")
        expected = f"09:00 {target.strftime('%d/%m/%Y')}"
        assert out == expected

    def test_other_day_uses_locale_date_format_english(self) -> None:
        # +5 days @ 09:00 Paris — US mm/dd/yyyy with year.
        target = datetime.now(PARIS).date() + timedelta(days=5)
        iso = datetime(target.year, target.month, target.day, 9, 0, tzinfo=PARIS).isoformat()
        out = _format_event_time({"dateTime": iso}, PARIS, "en")
        expected = f"09:00 {target.strftime('%m/%d/%Y')}"
        assert out == expected

    def test_all_day_today_returns_localized_word(self) -> None:
        today_iso = datetime.now(PARIS).date().isoformat()
        assert _format_event_time({"date": today_iso}, PARIS, "fr") == "toute la journée"
        assert _format_event_time({"date": today_iso}, PARIS, "en") == "all day"

    def test_all_day_tomorrow_combines_localized_words(self) -> None:
        tomorrow_iso = (datetime.now(PARIS).date() + timedelta(days=1)).isoformat()
        out_fr = _format_event_time({"date": tomorrow_iso}, PARIS, "fr")
        assert out_fr == "demain (toute la journée)"
        out_en = _format_event_time({"date": tomorrow_iso}, PARIS, "en")
        assert out_en == "tomorrow (all day)"

    def test_all_day_other_day_uses_locale_date(self) -> None:
        target = datetime.now(PARIS).date() + timedelta(days=5)
        out_fr = _format_event_time({"date": target.isoformat()}, PARIS, "fr")
        assert out_fr == f"{target.strftime('%d/%m/%Y')} (toute la journée)"
        out_en = _format_event_time({"date": target.isoformat()}, PARIS, "en")
        assert out_en == f"{target.strftime('%m/%d/%Y')} (all day)"

    def test_naive_datetime_with_microsoft_timezone_field(self) -> None:
        # 10:00 Europe/Paris naive → Paris local. In NY: 10:00 Paris ≈ 04:00 NY.
        out = _format_event_time(
            {"dateTime": "2026-04-23T10:00:00", "timeZone": "Europe/Paris"},
            NEW_YORK,
            "en",
        )
        assert out.startswith("04:00")

    def test_missing_field_returns_question_mark(self) -> None:
        assert _format_event_time(None, PARIS, "fr") == "?"
        assert _format_event_time({}, PARIS, "fr") == "?"


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
    item = format_agenda_event(raw, PARIS, "fr")
    assert item.title == "Réunion Marc"
    assert item.location == "Bureau"
    assert item.start_local == "14:00"


@pytest.mark.unit
def test_format_agenda_event_tomorrow_uses_locale_word() -> None:
    tomorrow = datetime.now(PARIS).date() + timedelta(days=1)
    raw = {
        "summary": "Atelier",
        "start": {
            "dateTime": datetime(
                tomorrow.year, tomorrow.month, tomorrow.day, 14, 30, tzinfo=PARIS
            ).isoformat(),
        },
    }
    assert format_agenda_event(raw, PARIS, "fr").start_local == "14:30 demain"
    assert format_agenda_event(raw, PARIS, "en").start_local == "14:30 tomorrow"


@pytest.mark.unit
def test_format_agenda_event_falls_back_to_untitled() -> None:
    # An event with no summary is named in the READER's language. This used to
    # bake "Untitled" into the payload whatever the request asked for, so a
    # German reader saw an English word in the middle of their agenda — and the
    # test pinned it, French request included.
    item = format_agenda_event({}, PARIS, "fr")
    assert item.title == "Sans titre"
    assert item.location is None
    assert item.start_local == "?"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("fr", "Sans titre"),
        ("en", "Untitled"),
        ("de", "Ohne Titel"),
        ("es", "Sin título"),
        ("it", "Senza titolo"),
        ("zh-CN", "无标题"),
        # Frontend-canonical Chinese must reach the same table, not fall back.
        ("zh", "无标题"),
    ],
)
def test_format_agenda_event_names_an_untitled_event_in_every_language(
    language: str, expected: str
) -> None:
    assert format_agenda_event({}, PARIS, language).title == expected


@pytest.mark.unit
def test_a_real_summary_is_never_replaced_by_the_fallback() -> None:
    assert format_agenda_event({"summary": "Dentiste"}, PARIS, "de").title == "Dentiste"


# =============================================================================
# format_email_item
# =============================================================================


@pytest.mark.unit
class TestFormatEmailItem:
    def test_today_message(self) -> None:
        now_local = datetime.now(PARIS).replace(hour=9, minute=30, second=0, microsecond=0)
        epoch_ms = int(now_local.timestamp() * 1000)
        item = format_email_item(
            {
                "from": "Sophie <sophie@acme.com>",
                "subject": "Brief Q2",
                "internalDate": str(epoch_ms),
            },
            PARIS,
            "fr",
        )
        assert (item.sender_name or "").startswith("Sophie")
        assert item.sender_email == "sophie@acme.com"
        assert item.subject == "Brief Q2"
        assert item.received_local == "09:30"

    def test_yesterday_message_uses_locale_date(self) -> None:
        yesterday_local = datetime.now(PARIS).replace(
            hour=9, minute=30, second=0, microsecond=0
        ) - timedelta(days=1)
        epoch_ms = int(yesterday_local.timestamp() * 1000)
        item = format_email_item(
            {"from": "Sophie <sophie@acme.com>", "subject": "Brief", "internalDate": str(epoch_ms)},
            PARIS,
            "fr",
        )
        # Mails are never tomorrow → falls into the "other day" branch with a
        # locale-aware date prefix (dd/mm/yyyy in French).
        assert item.received_local == f"09:30 {yesterday_local.strftime('%d/%m/%Y')}"

    def test_missing_fields_use_fallbacks(self) -> None:
        item = format_email_item({}, PARIS, "fr")
        assert item.sender_name is None
        assert item.sender_email is None
        assert item.subject == "(no subject)"
        assert item.received_local == "?"


# =============================================================================
# format_reminder_item
# =============================================================================


def _once() -> RecurrenceSpec:
    """A reminder that happens once — what every reminder was before 2026-09-06."""
    return RecurrenceSpec.model_validate(
        {
            "freq": "once",
            "interval": 1,
            "anchor_date": "2026-09-06",
            "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
        }
    )


def _daily() -> RecurrenceSpec:
    return RecurrenceSpec.model_validate(
        {
            "freq": "daily",
            "interval": 1,
            "anchor_date": "2026-09-06",
            "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
        }
    )


@pytest.mark.unit
def test_format_reminder_item_today() -> None:
    now_utc = datetime.now(UTC).replace(microsecond=0)
    # `id` is not optional on the model (UUIDMixin); a double without it
    # would only prove the double is incomplete. Same for `recurrence_spec`:
    # the card reads it to know whether cancelling removes a SERIES.
    reminder = SimpleNamespace(
        id=uuid4(), content="Call mom", trigger_at=now_utc, recurrence_spec=_once()
    )
    item = format_reminder_item(reminder, PARIS)
    assert item.content == "Call mom"
    # Should be HH:MM (today)
    assert ":" in item.trigger_at_local
    assert "tomorrow" not in item.trigger_at_local


@pytest.mark.unit
def test_format_reminder_item_tomorrow() -> None:
    from datetime import timedelta as td

    now_utc = datetime.now(UTC).replace(microsecond=0) + td(days=1)
    reminder = SimpleNamespace(
        id=uuid4(), content="Wake up early", trigger_at=now_utc, recurrence_spec=_once()
    )
    item = format_reminder_item(reminder, PARIS, "en")
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


@pytest.mark.unit
class TestTheCardKnowsWhetherCancellingRemovesASeries:
    """The briefing card shows ONE line and offers a cancel.

    Cancelling deletes the row, so for a repeating reminder every future
    occurrence goes with it. Without this flag the card could only offer a
    confirmation that reads like it removes one firing.
    """

    def test_a_single_occurrence_does_not_repeat(self) -> None:
        reminder = SimpleNamespace(
            id=uuid4(), content="x", trigger_at=datetime.now(UTC), recurrence_spec=_once()
        )
        assert format_reminder_item(reminder, PARIS).repeats is False

    def test_a_daily_reminder_repeats(self) -> None:
        reminder = SimpleNamespace(
            id=uuid4(), content="x", trigger_at=datetime.now(UTC), recurrence_spec=_daily()
        )
        assert format_reminder_item(reminder, PARIS).repeats is True
