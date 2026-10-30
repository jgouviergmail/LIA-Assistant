"""The 3-hour forecast folded into the card's daily strip — what it keeps and what it leaves out.

A slot is the provider's data: one without a time, one past the strip's horizon, one
whose timestamp or temperature is unreadable is left out, never guessed; a day left
without any readable temperature is not drawn.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.daily_strip import aggregate_daily_forecast

pytestmark = pytest.mark.unit

_TZ = ZoneInfo("UTC")


def _slot(at: datetime, **main: Any) -> dict[str, Any]:
    return {"dt": int(at.timestamp()), "main": main, "weather": [{"main": "Clouds"}]}


def _today_noon() -> datetime:
    return datetime.now(_TZ).replace(hour=12, minute=0, second=0, microsecond=0)


def test_unreadable_slots_are_left_out_and_readable_ones_kept() -> None:
    noon = _today_noon()
    forecast = {
        "list": [
            {"main": {"temp": 30.0}},  # no time
            {"dt": "not-a-number", "main": {"temp": 30.0}},  # unreadable time
            _slot(noon, temp_min=4.0, temp_max="warm", temp=None),  # one unreadable value
            _slot(noon + timedelta(hours=3), temp=9.5),
        ]
    }

    days = aggregate_daily_forecast(forecast, _TZ, 2)

    assert [(day.temp_min_c, day.temp_max_c) for day in days] == [(4.0, 9.5)]
    assert days[0].condition_code == "Clouds"


def test_a_slot_past_the_horizon_is_left_out() -> None:
    noon = _today_noon()
    forecast = {"list": [_slot(noon, temp=5.0), _slot(noon + timedelta(days=3), temp=20.0)]}

    days = aggregate_daily_forecast(forecast, _TZ, 2)

    assert [day.date_iso for day in days] == [noon.date().isoformat()]


def test_a_day_with_no_readable_temperature_is_not_drawn() -> None:
    noon = _today_noon()
    forecast = {
        "list": [
            _slot(noon, temp="n/a"),
            _slot(noon + timedelta(days=1), temp=7.0),
        ]
    }

    days = aggregate_daily_forecast(forecast, _TZ, 2)

    assert [day.date_iso for day in days] == [(noon + timedelta(days=1)).date().isoformat()]
