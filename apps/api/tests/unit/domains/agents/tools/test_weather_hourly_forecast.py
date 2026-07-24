"""Unit tests for the hourly (3-hour-step) weather forecast tool.

Covers the B1 fix (2026-07-23): the tool now honors ``date`` — it targets a
specific day within the free-tier 5-day / 3-hour window and filters to that
day's slots, instead of silently dropping ``date`` and returning a rolling
window from now (which made "quel temps le 25 ?" answer "I don't have that day").

Threshold values (max forecast days) are read from settings, never hardcoded.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.core.config import get_settings
from src.domains.agents.tools import weather_tools
from src.domains.agents.tools.weather_formatting import (
    _entry_local_date,
    _format_hourly_response,
)
from src.domains.agents.tools.weather_tools import _get_hourly_forecast_tool_impl

PARIS = "Europe/Paris"


def _entry_at_local(local_iso: str, tz: str = PARIS, temp: float = 20.0) -> dict:
    """Build a fake OWM 3-hour entry at a given LOCAL wall-clock time."""
    local = datetime.fromisoformat(local_iso).replace(tzinfo=ZoneInfo(tz))
    return {
        "dt": int(local.timestamp()),
        "dt_txt": local.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "main": {"temp": temp, "feels_like": temp, "humidity": 60},
        "wind": {"speed": 3.0},
        "weather": [{"description": "clear sky", "icon": "01d"}],
        "pop": 0.2,
    }


class TestEntryLocalDate:
    """The slot->local-date projection (UTC unix ts -> user calendar date)."""

    def test_maps_utc_timestamp_to_local_date(self):
        # 23:00 UTC on the 24th is 01:00 local (Paris, +2 in summer) on the 25th.
        entry = {"dt": int(datetime(2026, 7, 24, 23, 0, tzinfo=UTC).timestamp())}
        assert _entry_local_date(entry, PARIS) == "2026-07-25"
        assert _entry_local_date(entry, "UTC") == "2026-07-24"

    def test_invalid_timezone_falls_back_to_utc(self):
        entry = {"dt": int(datetime(2026, 7, 24, 23, 0, tzinfo=UTC).timestamp())}
        assert _entry_local_date(entry, "Not/AZone") == "2026-07-24"

    def test_missing_dt_uses_dt_txt_date_part(self):
        assert _entry_local_date({"dt_txt": "2026-07-25 12:00:00"}, PARIS) == "2026-07-25"

    def test_missing_everything_returns_empty(self):
        assert _entry_local_date({}, PARIS) == ""


class TestFormatHourlyResponseTargetDate:
    """Filtering behavior of the formatter with/without a target day."""

    def test_target_date_keeps_only_that_local_day(self):
        forecast = {
            "list": [
                _entry_at_local("2026-07-24T21:00"),  # local 24th
                _entry_at_local("2026-07-25T00:00"),  # local 25th
                _entry_at_local("2026-07-25T12:00"),  # local 25th
                _entry_at_local("2026-07-25T21:00"),  # local 25th
                _entry_at_local("2026-07-26T00:00"),  # local 26th
            ],
            "city": {"name": "Paris", "country": "FR"},
        }
        result = _format_hourly_response(
            forecast,
            "Paris",
            "FR",
            entries_needed=999,
            units="metric",
            target_date="2026-07-25",
            user_timezone=PARIS,
        )
        assert result["success"] is True
        assert result["data"]["forecast_entries"] == 3
        # Every returned slot projects to the requested local day.
        for slot in result["data"]["hourly"]:
            local = datetime.fromtimestamp(slot["datetime"], tz=ZoneInfo(PARIS))
            assert local.date().isoformat() == "2026-07-25"

    def test_no_target_date_keeps_sliding_window(self):
        forecast = {
            "list": [_entry_at_local(f"2026-07-2{d}T12:00") for d in range(3, 8)],
        }
        result = _format_hourly_response(
            forecast,
            "Paris",
            "FR",
            entries_needed=2,
            units="metric",
        )
        # No target_date -> first `entries_needed` entries only (rolling window).
        assert result["data"]["forecast_entries"] == 2

    def test_formatter_is_pure_and_reports_zero_when_no_slot_matches(self):
        """The FORMATTER stays pure: it reports 0 slots, no policy decision.

        Turning that into an explicit failure is the TOOL's responsibility — see
        TestExecuteNoSlotsForDate, which pins the user-facing contract. (An earlier
        version of this suite asserted the tool's empty success as if correct,
        enshrining the very "no weather" symptom the tool exists to fix.)
        """
        forecast = {"list": [_entry_at_local("2026-07-24T12:00")]}
        result = _format_hourly_response(
            forecast,
            "Paris",
            "FR",
            entries_needed=8,
            units="metric",
            target_date="2026-07-25",
            user_timezone=PARIS,
        )
        assert result["success"] is True
        assert result["data"]["forecast_entries"] == 0


class TestExecuteBeyondForecast:
    """A day beyond the free-tier window fails honestly, not silently."""

    async def test_far_future_date_returns_explicit_error(self):
        max_days = get_settings().weather_forecast_max_days
        far = (datetime.now(UTC).date() + timedelta(days=max_days + 3)).isoformat()
        # runtime=None -> timezone stays UTC, no client/geocode needed (guard is
        # evaluated before location resolution).
        result = await _get_hourly_forecast_tool_impl.execute_api_call(
            AsyncMock(),
            uuid4(),
            date=far,
            runtime=None,
            language="fr",
        )
        assert result["success"] is False
        assert result["error"] == "date_beyond_forecast"
        assert isinstance(result["message"], str) and result["message"]

    async def test_within_window_date_does_not_trigger_beyond_guard(self):
        max_days = get_settings().weather_forecast_max_days
        within = (datetime.now(UTC).date() + timedelta(days=max_days)).isoformat()
        # Anchor the synthetic payload at LOCAL MIDNIGHT of the target day rather
        # than "now + 3h steps": the latter only reaches day+max_days when the
        # wall clock is past 03:00 UTC, so the test went red between 00:00 and
        # 02:59 UTC (measured — 3 hours out of 24 on a UTC CI runner).
        day_start = datetime.fromisoformat(f"{within}T00:00:00+00:00")
        entries = [
            {
                "dt": int((day_start + timedelta(hours=3 * i)).timestamp()),
                "dt_txt": "x",
                "main": {"temp": 20.0, "feels_like": 20.0, "humidity": 50},
                "wind": {"speed": 1.0},
                "weather": [{"description": "clear", "icon": "01d"}],
                "pop": 0.0,
            }
            for i in range(8)
        ]
        fake_client = AsyncMock()
        fake_client.get_forecast = AsyncMock(
            return_value={"list": entries, "city": {"name": "Paris", "country": "FR"}}
        )
        with patch.object(
            weather_tools,
            "_geocode_with_city_fallback",
            new=AsyncMock(return_value=(48.85, 2.35, "Paris", "FR")),
        ):
            result = await _get_hourly_forecast_tool_impl.execute_api_call(
                fake_client,
                uuid4(),
                location="Paris",
                date=within,
                runtime=None,
                units="metric",
            )
        assert result["success"] is True


class TestLocalWallClock:
    """Slot times are rendered on the USER's clock, never in UTC.

    Prod defect (2026-07-23): the day was filtered in local time but every slot
    kept OpenWeatherMap's UTC ``dt_txt``, so a Paris user asking for the 25th got
    "22:00" for a slot at 00:00 local and "10:00" for one at 12:00 — a 2-hour lie
    in the LLM summary and in the weather card, on the very tool meant to fix
    misquoted times.
    """

    def test_datetime_text_is_local_not_utc(self):
        forecast = {
            "list": [_entry_at_local("2026-07-25T00:00"), _entry_at_local("2026-07-25T12:00")],
            "city": {"name": "Paris", "country": "FR"},
        }
        result = _format_hourly_response(
            forecast,
            "Paris",
            "FR",
            entries_needed=99,
            units="metric",
            target_date="2026-07-25",
            user_timezone=PARIS,
        )
        texts = [slot["datetime_text"] for slot in result["data"]["hourly"]]
        assert texts == ["2026-07-25 00:00:00", "2026-07-25 12:00:00"]

    def test_datetime_text_matches_the_epoch_it_ships_with(self):
        """The rendered text and the raw epoch must denote the same instant."""
        forecast = {"list": [_entry_at_local("2026-07-25T12:00")]}
        result = _format_hourly_response(
            forecast, "Paris", "FR", entries_needed=8, units="metric", user_timezone=PARIS
        )
        slot = result["data"]["hourly"][0]
        expected = datetime.fromtimestamp(slot["datetime"], tz=ZoneInfo(PARIS))
        assert slot["datetime_text"] == expected.strftime("%Y-%m-%d %H:%M:%S")

    def test_unknown_timezone_falls_back_to_utc_rendering(self):
        forecast = {"list": [_entry_at_local("2026-07-25T12:00")]}
        result = _format_hourly_response(
            forecast, "Paris", "FR", entries_needed=8, units="metric", user_timezone="Not/AZone"
        )
        # 12:00 Paris (UTC+2 in July) -> 10:00 UTC when the zone cannot be parsed.
        assert result["data"]["hourly"][0]["datetime_text"] == "2026-07-25 10:00:00"


class TestExecuteHonorsDate:
    """End-to-end: a specific-day request filters the impl output to that day."""

    async def test_specific_date_filters_to_that_day_and_sizes_window(self):
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        # ~3.5 days of 3-hour slots starting from "now".
        entries = []
        t = now
        for _ in range(3 * 8 + 4):
            entries.append(
                {
                    "dt": int(t.timestamp()),
                    "dt_txt": t.strftime("%Y-%m-%d %H:%M:%S"),
                    "main": {"temp": 22.0, "feels_like": 22.0, "humidity": 55},
                    "wind": {"speed": 2.5},
                    "weather": [{"description": "clear sky", "icon": "01d"}],
                    "pop": 0.0,
                }
            )
            t += timedelta(hours=3)

        fake_client = AsyncMock()
        fake_client.get_forecast = AsyncMock(
            return_value={"list": entries, "city": {"name": "Paris", "country": "FR"}}
        )

        target = (now.date() + timedelta(days=2)).isoformat()
        with patch.object(
            weather_tools,
            "_geocode_with_city_fallback",
            new=AsyncMock(return_value=(48.85, 2.35, "Paris", "FR")),
        ):
            result = await _get_hourly_forecast_tool_impl.execute_api_call(
                fake_client,
                uuid4(),
                location="Paris",
                date=target,
                runtime=None,
                units="metric",
            )

        assert result["success"] is True
        returned = result["data"]["hourly"]
        # Only the target day's slots, and strictly fewer than the full list.
        assert returned
        assert len(returned) < len(entries)
        for slot in returned:
            d = datetime.fromtimestamp(slot["datetime"], tz=UTC).date().isoformat()
            assert d == target

        # Window sized to reach through the target day: (offset + 2) * 8, capped.
        max_entries = get_settings().weather_forecast_max_days * 8
        expected_cnt = min((2 + 2) * 8, max_entries)
        assert fake_client.get_forecast.await_args.kwargs["cnt"] == expected_cnt

    async def test_no_date_keeps_rolling_window(self):
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        entries = [
            {
                "dt": int((now + timedelta(hours=3 * i)).timestamp()),
                "dt_txt": (now + timedelta(hours=3 * i)).strftime("%Y-%m-%d %H:%M:%S"),
                "main": {"temp": 18.0, "feels_like": 18.0, "humidity": 70},
                "wind": {"speed": 4.0},
                "weather": [{"description": "clouds", "icon": "03d"}],
                "pop": 0.3,
            }
            for i in range(16)
        ]
        fake_client = AsyncMock()
        fake_client.get_forecast = AsyncMock(
            return_value={"list": entries, "city": {"name": "Paris", "country": "FR"}}
        )
        with patch.object(
            weather_tools,
            "_geocode_with_city_fallback",
            new=AsyncMock(return_value=(48.85, 2.35, "Paris", "FR")),
        ):
            result = await _get_hourly_forecast_tool_impl.execute_api_call(
                fake_client,
                uuid4(),
                location="Paris",
                hours=12,
                runtime=None,
                units="metric",
            )
        assert result["success"] is True
        # hours=12 -> 12//3 + 1 = 5 slots requested and returned (sliding window).
        assert fake_client.get_forecast.await_args.kwargs["cnt"] == 5
        assert result["data"]["forecast_entries"] == 5


class TestRegistryResponse:
    """The registry item and the LLM summary describe the day actually covered."""

    def _result(self, language: str = "fr") -> dict:
        forecast = {
            "list": [_entry_at_local(f"2026-07-25T{h:02d}:00") for h in (0, 3, 6, 9, 12)],
            "city": {"name": "Paris", "country": "FR"},
        }
        formatted = _format_hourly_response(
            forecast,
            "Paris",
            "FR",
            entries_needed=99,
            units="metric",
            target_date="2026-07-25",
            user_timezone=PARIS,
        )
        formatted["data"]["date"] = "2026-07-25"
        formatted[_get_hourly_forecast_tool_impl._LANGUAGE_RESULT_KEY] = language
        return formatted

    def test_registry_item_is_stamped_with_the_covered_day(self):
        """Not `today`: a future-day request produced an item dated now (prod bug)."""
        out = _get_hourly_forecast_tool_impl.format_registry_response(self._result())
        item = next(iter(out.registry_updates.values()))
        assert item.payload["date"] == "2026-07-25"
        assert item.payload["date"] != datetime.now(UTC).strftime("%Y-%m-%d")

    def test_same_day_and_place_yields_a_stable_item_id(self):
        """Re-asking is idempotent: the item is replaced, not accumulated."""
        first = _get_hourly_forecast_tool_impl.format_registry_response(self._result())
        second = _get_hourly_forecast_tool_impl.format_registry_response(self._result())
        assert list(first.registry_updates) == list(second.registry_updates)

    def test_summary_is_localized_and_quotes_local_times(self):
        fr = _get_hourly_forecast_tool_impl.format_registry_response(self._result("fr")).message
        en = _get_hourly_forecast_tool_impl.format_registry_response(self._result("en")).message
        assert fr != en, "summary must follow the user's language, not be hardcoded French"
        assert "Prévisions" in fr and "forecast" in en.lower()
        # Times handed to the LLM are the user's wall clock. The four previewed
        # slots are 00:00/03:00/06:00/09:00 local — their UTC twins (22:00 the
        # day before, 01:00, 04:00, 07:00) must not appear.
        assert "- 00:00:" in fr and "- 09:00:" in fr
        assert "22:00" not in fr

    def test_summary_reports_the_truncated_slot_count(self):
        message = _get_hourly_forecast_tool_impl.format_registry_response(self._result()).message
        # 5 slots, 4 previewed -> 1 explicitly reported as omitted.
        assert "1" in message.rsplit("\n", 1)[-1]


class TestExecuteNoSlotsForDate:
    """A day inside the window but absent from the payload must fail explicitly.

    Reachable when WEATHER_FORECAST_MAX_DAYS is lowered, at the far edge of the
    window, or with a far-offset timezone. An empty success would read to the
    response LLM as "no weather" — the exact symptom this tool exists to fix.
    """

    async def _run(self, language: str) -> dict:
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        # Provider returns only the next couple of slots: the requested day is absent.
        entries = [
            {
                "dt": int((now + timedelta(hours=3 * i)).timestamp()),
                "dt_txt": (now + timedelta(hours=3 * i)).strftime("%Y-%m-%d %H:%M:%S"),
                "main": {"temp": 19.0, "feels_like": 19.0, "humidity": 60},
                "wind": {"speed": 2.0},
                "weather": [{"description": "clear", "icon": "01d"}],
                "pop": 0.0,
            }
            for i in range(2)
        ]
        fake_client = AsyncMock()
        fake_client.get_forecast = AsyncMock(
            return_value={"list": entries, "city": {"name": "Paris", "country": "FR"}}
        )
        # Within the forecast window (so the beyond-limit guard must NOT fire).
        target = (now.date() + timedelta(days=3)).isoformat()
        assert 3 <= get_settings().weather_forecast_max_days
        with patch.object(
            weather_tools,
            "_geocode_with_city_fallback",
            new=AsyncMock(return_value=(48.85, 2.35, "Paris", "FR")),
        ):
            result = await _get_hourly_forecast_tool_impl.execute_api_call(
                fake_client,
                uuid4(),
                location="Paris",
                date=target,
                runtime=None,
                units="metric",
                language=language,
            )
        result["_target"] = target
        return result

    async def test_returns_explicit_error_not_empty_success(self):
        result = await self._run("fr")
        assert result["success"] is False
        assert result["error"] == "no_slots_for_date"
        # Distinct from the beyond-window guard: that message would contradict
        # itself here (the day IS inside the window).
        assert result["error"] != "date_beyond_forecast"
        assert result["_target"] in result["message"]

    async def test_message_is_localized(self):
        fr = await self._run("fr")
        en = await self._run("en")
        assert fr["message"] != en["message"]
        assert "prévision" in fr["message"].lower()
        assert "forecast" in en["message"].lower()
