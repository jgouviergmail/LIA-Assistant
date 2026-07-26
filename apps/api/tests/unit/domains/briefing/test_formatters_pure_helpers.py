"""Briefing formatters — the pure helpers behind what the home page shows.

Companion to ``test_formatters.py``, which covers the public formatters. This
file drives the private helpers that decide what the Today Briefing *omits*,
and the numeric aggregates it prints:

* ``is_event_past`` filters the agenda. Anything it wrongly calls "past"
  disappears from the home page with no error anywhere — the user simply never
  sees the meeting.
* the weather aggregates (``_pick_dominant_condition``,
  ``_today_min_max_from_forecast``, ``_first_forecast_pop``) turn 3-hour slots
  into the single line the card prints. The bearing→compass mapping moved to
  ``core.geo_utils`` — see ``tests/unit/core/test_wind_cardinals.py``.
* the health helpers turn a raw daily breakdown into "moy. 14 j (12 jours)".
* ``_parse_from_header`` splits the RFC 2822 ``From`` of every mail row.

None of them touch I/O, and none of them were exercised.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.formatters import (
    _first_forecast_pop,
    _format_all_day,
    _parse_from_header,
    _pick_dominant_condition,
    _today_min_max_from_forecast,
    daily_average_from_breakdown,
    extract_today_value_from_summary,
    is_event_past,
)

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")


def _timed_end(dt: datetime, time_zone: str | None = None) -> dict[str, Any]:
    """A provider `end` field for a timed event."""
    field: dict[str, Any] = {"dateTime": dt.isoformat()}
    if time_zone is not None:
        field["timeZone"] = time_zone
    return field


class TestIsEventPast:
    """The agenda filter — dropping an event is invisible, so it must be right."""

    def test_a_finished_timed_event_is_past(self) -> None:
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        event = {"end": _timed_end(now - timedelta(minutes=1))}

        assert is_event_past(event, now, PARIS) is True

    def test_an_event_ending_right_now_is_past(self) -> None:
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)

        assert is_event_past({"end": _timed_end(now)}, now, PARIS) is True

    def test_an_ongoing_event_is_kept(self) -> None:
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        event = {"end": _timed_end(now + timedelta(minutes=30))}

        assert is_event_past(event, now, PARIS) is False

    def test_a_naive_end_is_read_in_the_events_own_timezone(self) -> None:
        # 13:30 Paris is 11:30 UTC — already past a 12:00 UTC "now". Read as
        # naive UTC instead, it would look 90 minutes in the FUTURE and the
        # finished meeting would linger on the home page.
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        event = {"end": {"dateTime": "2026-07-25T13:30:00", "timeZone": "Europe/Paris"}}

        assert is_event_past(event, now, ZoneInfo("UTC")) is True

    def test_an_unknown_event_timezone_falls_back_to_the_users(self) -> None:
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        unknown_tz = {"end": {"dateTime": "2026-07-25T13:30:00", "timeZone": "Mars/Olympus"}}
        no_tz = {"end": {"dateTime": "2026-07-25T13:30:00"}}

        # Both resolve against the user timezone, so both reach the same verdict.
        assert is_event_past(unknown_tz, now, PARIS) == is_event_past(no_tz, now, PARIS)
        assert is_event_past(unknown_tz, now, PARIS) is True

    def test_a_naive_end_without_timezone_uses_the_user_timezone(self) -> None:
        # CalDAV (Apple) sends naive local datetimes.
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        event = {"end": {"dateTime": "2026-07-25T11:00:00"}}

        # 11:00 Paris = 09:00 UTC → already finished.
        assert is_event_past(event, now, PARIS) is True

    def test_an_all_day_event_whose_last_day_was_yesterday_is_past(self) -> None:
        # Google convention: `end.date` is the day AFTER the last day.
        now = datetime(2026, 7, 25, 9, 0, tzinfo=PARIS)
        event = {"end": {"date": "2026-07-25"}}

        assert is_event_past(event, now, PARIS) is True

    def test_an_all_day_event_running_today_is_kept(self) -> None:
        now = datetime(2026, 7, 25, 9, 0, tzinfo=PARIS)
        event = {"end": {"date": "2026-07-26"}}

        assert is_event_past(event, now, PARIS) is False

    @pytest.mark.parametrize(
        ("event", "reason"),
        [
            ({}, "no end at all"),
            ({"end": {}}, "empty end"),
            ({"end": {"dateTime": None}}, "null dateTime"),
            ({"end": {"dateTime": "not-a-date"}}, "unparseable dateTime"),
            ({"end": {"date": "not-a-date"}}, "unparseable all-day date"),
            ({"end": "2026-07-25T10:00:00Z"}, "end sent as a bare string"),
        ],
    )
    def test_never_drops_an_event_whose_end_cannot_be_read(
        self, event: dict[str, Any], reason: str
    ) -> None:
        # The documented contract: an unreadable end keeps the event visible.
        # Dropping it would hide a real meeting; showing a stale one is benign.
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)

        assert is_event_past(event, now, PARIS) is False, reason

    def test_an_all_day_date_that_also_carries_a_datetime_uses_the_datetime(self) -> None:
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        event = {
            "end": {
                "date": "2026-07-25",
                "dateTime": (now + timedelta(hours=2)).isoformat(),
            }
        }

        assert is_event_past(event, now, PARIS) is False


class TestFormatAllDay:
    """All-day events read as words, not as a placeholder 00:00."""

    def test_today_is_rendered_as_the_all_day_word_alone(self) -> None:
        today = datetime.now(PARIS).date().isoformat()

        rendered = _format_all_day(today, PARIS, "fr")

        assert rendered == "toute la journée"

    def test_another_day_keeps_the_date_and_appends_the_all_day_word(self) -> None:
        tomorrow = (datetime.now(PARIS) + timedelta(days=1)).date().isoformat()

        rendered = _format_all_day(tomorrow, PARIS, "fr")

        assert rendered.endswith("(toute la journée)")
        assert not rendered.startswith("00:00")

    def test_an_unparseable_date_keeps_the_raw_value(self) -> None:
        rendered = _format_all_day("25/07/2026", PARIS, "fr")

        assert rendered == "25/07/2026 (toute la journée)"


class TestParseFromHeader:
    """Splitting the RFC 2822 From of every mail row."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Sophie Martin <sophie@acme.com>", ("Sophie Martin", "sophie@acme.com")),
            ('"Sophie, M." <sophie@acme.com>', ("Sophie, M.", "sophie@acme.com")),
            ("<sophie@acme.com>", (None, "sophie@acme.com")),
            ("sophie@acme.com", (None, "sophie@acme.com")),
            ("Sophie Martin", ("Sophie Martin", None)),
            ("", (None, None)),
            ("   ", (None, None)),
            ("  Sophie Martin  <sophie@acme.com>  ", ("Sophie Martin", "sophie@acme.com")),
        ],
    )
    def test_splits_the_header_into_name_and_address(
        self, raw: str, expected: tuple[str | None, str | None]
    ) -> None:
        assert _parse_from_header(raw) == expected


class TestPickDominantCondition:
    """Severity first, frequency as tie-break."""

    def test_the_most_severe_condition_of_the_day_wins(self) -> None:
        # A single thunderstorm slot outranks a day of clear sky.
        assert _pick_dominant_condition(["Clear", "Clear", "Clear", "Thunderstorm"]) == (
            "Thunderstorm"
        )

    def test_frequency_breaks_a_tie_between_equal_severities(self) -> None:
        assert _pick_dominant_condition(["Clear", "Clear", "Clouds"]) in {"Clear", "Clouds"}

    def test_a_single_condition_is_returned_as_is(self) -> None:
        assert _pick_dominant_condition(["Rain"]) == "Rain"

    def test_an_empty_day_is_unknown(self) -> None:
        assert _pick_dominant_condition([]) == "Unknown"


class TestTodayMinMaxFromForecast:
    """Today's expected range, read out of the 3-hour slots."""

    def _slot(self, when: datetime, t_min: float | None, t_max: float | None) -> dict[str, Any]:
        return {
            "dt": int(when.timestamp()),
            "main": {"temp_min": t_min, "temp_max": t_max},
        }

    def test_keeps_only_todays_slots(self) -> None:
        today_noon = datetime.now(PARIS).replace(hour=12, minute=0, second=0, microsecond=0)
        tomorrow_noon = today_noon + timedelta(days=1)
        forecast = {
            "list": [
                self._slot(today_noon, 14.0, 21.0),
                self._slot(today_noon + timedelta(hours=3), 16.0, 23.0),
                self._slot(tomorrow_noon, -5.0, 40.0),
            ]
        }

        assert _today_min_max_from_forecast(forecast, PARIS) == (14.0, 23.0)

    def test_returns_none_when_no_slot_belongs_to_today(self) -> None:
        tomorrow = datetime.now(PARIS) + timedelta(days=1)
        forecast = {"list": [self._slot(tomorrow, 10.0, 20.0)]}

        assert _today_min_max_from_forecast(forecast, PARIS) == (None, None)

    @pytest.mark.parametrize("forecast", [{}, {"list": None}, {"list": []}])
    def test_returns_none_on_an_empty_forecast(self, forecast: dict[str, Any]) -> None:
        assert _today_min_max_from_forecast(forecast, PARIS) == (None, None)

    def test_skips_a_slot_with_no_timestamp_instead_of_failing(self) -> None:
        today_noon = datetime.now(PARIS).replace(hour=12, minute=0, second=0, microsecond=0)
        forecast = {
            "list": [
                {"main": {"temp_min": 1.0, "temp_max": 2.0}},
                self._slot(today_noon, 14.0, 21.0),
            ]
        }

        assert _today_min_max_from_forecast(forecast, PARIS) == (14.0, 21.0)

    def test_tolerates_a_slot_missing_one_bound(self) -> None:
        today_noon = datetime.now(PARIS).replace(hour=12, minute=0, second=0, microsecond=0)
        forecast = {"list": [self._slot(today_noon, None, 21.0)]}

        assert _today_min_max_from_forecast(forecast, PARIS) == (21.0, 21.0)


class TestFirstForecastPop:
    """Precipitation probability of the next slot, clamped to [0, 1]."""

    def test_reads_the_first_slot(self) -> None:
        assert _first_forecast_pop({"list": [{"pop": 0.42}, {"pop": 0.9}]}) == 0.42

    @pytest.mark.parametrize(("pop", "expected"), [(1.4, 1.0), (-0.2, 0.0), (0.0, 0.0), (1.0, 1.0)])
    def test_clamps_an_out_of_range_probability(self, pop: float, expected: float) -> None:
        assert _first_forecast_pop({"list": [{"pop": pop}]}) == expected

    @pytest.mark.parametrize(
        "forecast",
        [{}, {"list": []}, {"list": None}, {"list": [{}]}, {"list": [{"pop": None}]}],
    )
    def test_returns_none_when_there_is_no_probability(self, forecast: dict[str, Any]) -> None:
        assert _first_forecast_pop(forecast) is None

    def test_returns_none_for_a_non_numeric_probability(self) -> None:
        assert _first_forecast_pop({"list": [{"pop": "rainy"}]}) is None


class TestDailyAverageFromBreakdown:
    """ "moy. 14 j (12 jours)" — the average and the coverage it is based on."""

    def test_averages_only_the_days_that_carry_a_value(self) -> None:
        breakdown = [
            {"date": "2026-07-23", "value": 10},
            {"date": "2026-07-24", "value": 20},
            {"date": "2026-07-25", "value": None},
        ]

        assert daily_average_from_breakdown(breakdown, window_days=14) == (15.0, 2)

    def test_rounds_to_one_decimal(self) -> None:
        breakdown = [{"value": 1}, {"value": 2}]

        assert daily_average_from_breakdown(breakdown, window_days=7) == (1.5, 2)

    def test_counts_a_zero_day_as_data(self) -> None:
        # A day with 0 steps is measured, not missing — it must lower the average.
        breakdown = [{"value": 0}, {"value": 10}]

        assert daily_average_from_breakdown(breakdown, window_days=7) == (5.0, 2)

    @pytest.mark.parametrize("breakdown", [[], [{"value": None}], [{}]])
    def test_reports_no_data_rather_than_a_zero_average(
        self, breakdown: list[dict[str, Any]]
    ) -> None:
        assert daily_average_from_breakdown(breakdown, window_days=14) == (None, 0)


class TestExtractTodayValueFromSummary:
    """Each health kind reads its own aggregate."""

    def test_steps_read_the_total(self) -> None:
        summary = {"samples_count": 5, "total": 8421, "avg": 12}

        assert extract_today_value_from_summary(summary, kind="steps") == 8421.0

    def test_heart_rate_reads_the_average(self) -> None:
        summary = {"samples_count": 5, "total": 999, "avg": 62.5}

        assert extract_today_value_from_summary(summary, kind="heart_rate") == 62.5

    def test_an_unregistered_kind_falls_back_to_the_last_sample(self) -> None:
        summary = {"samples_count": 2, "last": 71}

        assert extract_today_value_from_summary(summary, kind="weight") == 71.0

    @pytest.mark.parametrize(
        "summary",
        [{}, {"samples_count": 0, "total": 5000}, {"samples_count": 3}],
    )
    def test_hides_the_line_when_there_is_nothing_measured_today(
        self, summary: dict[str, Any]
    ) -> None:
        assert extract_today_value_from_summary(summary, kind="steps") is None

    def test_a_non_numeric_aggregate_is_reported_as_absent(self) -> None:
        summary = {"samples_count": 3, "total": "many"}

        assert extract_today_value_from_summary(summary, kind="steps") is None

    def test_a_zero_total_is_a_real_value_not_an_absence(self) -> None:
        summary = {"samples_count": 3, "total": 0}

        assert extract_today_value_from_summary(summary, kind="steps") == 0.0
