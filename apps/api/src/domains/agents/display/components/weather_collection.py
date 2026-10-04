"""Presentation-only grouping; registry items and their chronology stay intact."""

from collections.abc import Sequence
from datetime import date


def _forecast(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or value.get("type") != "forecast" or value.get("forecasts"):
        return None
    if not value.get("location") or not isinstance(value.get("date"), str):
        return None
    try:
        date.fromisoformat(value["date"])
    except ValueError:
        return None
    return value


def _same_series(left: dict[str, object], right: dict[str, object]) -> bool:
    return all(left.get(key) == right.get(key) for key in ("location", "source", "timezone"))


def prepare_weather_items(items: Sequence[object]) -> list[object]:
    result: list[object] = []
    index = 0
    while index < len(items):
        first = _forecast(items[index])
        if first is None:
            result.append(items[index])
            index += 1
            continue
        group = [first]
        index += 1
        while (
            index < len(items)
            and (next_day := _forecast(items[index])) is not None
            and _same_series(first, next_day)
        ):
            group.append(next_day)
            index += 1
        if len(group) == 1:
            result.append(first)
        else:
            result.append(
                {
                    "type": "forecast",
                    "location": first.get("location"),
                    "source": first.get("source"),
                    "timezone": first.get("timezone"),
                    "forecasts": group,
                }
            )
    return result
