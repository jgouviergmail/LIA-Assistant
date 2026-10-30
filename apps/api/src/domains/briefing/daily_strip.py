"""The weather card's daily strip: one emoji vocabulary, two sources of days.

The strip is today and the next days, each with its low, its high and the most
severe condition of the day. A provider serving its own daily summaries (W1b,
``GoogleWeatherClient.get_daily_summaries``) gives the days directly; the others
are aggregated from their 3-hour forecast slots. Both pick the day's icon the same
way, so the strip keeps one meaning whatever the source.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.domains.briefing.schemas import DailyForecastItem

# Map OpenWeatherMap "main" condition codes to a single emoji.
# Reference: https://openweathermap.org/weather-conditions
WEATHER_EMOJI_MAP: dict[str, str] = {
    "Clear": "☀️",
    "Clouds": "☁️",
    "Rain": "🌧️",
    "Drizzle": "🌦️",
    "Thunderstorm": "⛈️",
    "Snow": "❄️",
    "Mist": "🌫️",
    "Smoke": "🌫️",
    "Haze": "🌫️",
    "Dust": "🌫️",
    "Fog": "🌫️",
    "Sand": "🌫️",
    "Ash": "🌫️",
    "Squall": "🌬️",
    "Tornado": "🌪️",
}
WEATHER_EMOJI_DEFAULT = "🌤️"


# Conditions ranked by "severity" — when a day has a mix, we surface the more
# notable one as the daily icon (rain dominates over clear, etc.).
_CONDITION_SEVERITY: dict[str, int] = {
    "Thunderstorm": 100,
    "Tornado": 100,
    "Snow": 90,
    "Rain": 80,
    "Drizzle": 70,
    "Squall": 60,
    "Fog": 50,
    "Mist": 50,
    "Haze": 50,
    "Smoke": 50,
    "Dust": 50,
    "Sand": 50,
    "Ash": 50,
    "Clouds": 30,
    "Clear": 10,
}


def pick_dominant_condition(condition_codes: list[str]) -> str:
    """Pick the most representative condition code for a day.

    Rule: the condition with the highest severity score wins. If two conditions
    tie (e.g. all "Clear"), the most frequent one wins (mode).
    """
    if not condition_codes:
        return "Unknown"
    # Count occurrences
    counts: dict[str, int] = {}
    for code in condition_codes:
        counts[code] = counts.get(code, 0) + 1
    # Sort by (severity desc, count desc) and take the first
    return max(
        counts.keys(),
        key=lambda c: (_CONDITION_SEVERITY.get(c, 20), counts[c]),
    )


def daily_items_from_summaries(
    summaries: list[dict[str, Any]], daily_forecast_days: int
) -> list[DailyForecastItem]:
    """The provider's own daily summaries as strip items (today + next N days).

    The condition is picked as the slot aggregation picks it — the most severe of the
    day's and the night's — so the strip's icon keeps one meaning whatever the source.
    """
    items: list[DailyForecastItem] = []
    for summary in summaries[:daily_forecast_days]:
        condition = pick_dominant_condition(list(summary["conditions"]))
        items.append(
            DailyForecastItem(
                date_iso=summary["date"],
                temp_min_c=round(float(summary["temp_min"]), 1),
                temp_max_c=round(float(summary["temp_max"]), 1),
                condition_code=condition,
                icon_emoji=WEATHER_EMOJI_MAP.get(condition, WEATHER_EMOJI_DEFAULT),
            )
        )
    return items


def aggregate_daily_forecast(
    forecast: dict[str, Any],
    user_tz: ZoneInfo,
    daily_forecast_days: int,
) -> list[DailyForecastItem]:
    """Aggregate the 3-h forecast slots into per-day summaries (today + next N days).

    For each day:
    - temp_min / temp_max = min and max across all slots of that day
    - condition_code = dominant condition (severity-weighted, then frequency)
    - icon_emoji from WEATHER_EMOJI_MAP

    Days with too few slots (e.g. last day with only 1 slot late at night) are
    still surfaced — the user benefits from any signal beyond today.
    """
    today_local = datetime.now(user_tz).date()
    horizon_end = today_local.toordinal() + (daily_forecast_days - 1)

    by_day: dict[str, dict[str, Any]] = {}
    for entry in forecast.get("list", []) or []:
        try:
            ts = entry.get("dt")
            if ts is None:
                continue
            slot_local = datetime.fromtimestamp(int(ts), tz=user_tz)
            slot_date = slot_local.date()
            if slot_date.toordinal() > horizon_end:
                continue
            date_key = slot_date.isoformat()
        except ValueError, TypeError, OSError:
            continue

        bucket = by_day.setdefault(date_key, {"temps": [], "conditions": [], "date_obj": slot_date})

        slot_main = entry.get("main", {}) or {}
        for key in ("temp_min", "temp_max", "temp"):
            val = slot_main.get(key)
            if val is not None:
                with suppress(TypeError, ValueError):
                    bucket["temps"].append(float(val))

        weather_arr = entry.get("weather", []) or []
        if weather_arr:
            code = weather_arr[0].get("main")
            if code:
                bucket["conditions"].append(str(code))

    items: list[DailyForecastItem] = []
    for date_key in sorted(by_day.keys()):
        bucket = by_day[date_key]
        if not bucket["temps"]:
            continue
        condition = pick_dominant_condition(bucket["conditions"])
        items.append(
            DailyForecastItem(
                date_iso=date_key,
                temp_min_c=round(min(bucket["temps"]), 1),
                temp_max_c=round(max(bucket["temps"]), 1),
                condition_code=condition,
                icon_emoji=WEATHER_EMOJI_MAP.get(condition, WEATHER_EMOJI_DEFAULT),
            )
        )
    return items[:daily_forecast_days]
