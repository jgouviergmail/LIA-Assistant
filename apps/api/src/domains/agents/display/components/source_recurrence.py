"""Describe supported Graph schedules through the existing recurrence vocabulary.

Unknown or richer schedules retain their supplied rule text in the details; this
display adapter never runs, rewrites or schedules a provider recurrence.
"""

import json
from collections.abc import Mapping
from contextlib import suppress
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from src.core.i18n_cards import card_label
from src.core.i18n_dates import get_day_name
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.core.recurrence import RecurrenceSpec, describe, describe_calendar
from src.core.time_utils import parse_provider_datetime
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_full_date,
    render_d_item,
)
from src.domains.agents.display.components.card_content import render_text_content
from src.domains.agents.display.components.mcp_details import MCPDisplaySnapshot
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import list_values
from src.domains.connectors.clients.normalizers.microsoft_recurrence import GRAPH_RECURRENCE_FIELDS

_DAYS = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}
_FREQUENCIES = {
    "daily": "daily",
    "weekly": "weekly",
    "absoluteMonthly": "monthly",
    "relativeMonthly": "monthly",
    "absoluteYearly": "yearly",
}
_INDEX = {"first": 1, "second": 2, "third": 3, "fourth": 4, "last": -1}


def _graph_selectors(pattern: Mapping[str, object], kind: str) -> dict[str, object]:
    if kind == "weekly":
        return {
            "byweekday": [
                _DAYS.get(day, 0) if isinstance(day, str) else 0
                for day in list_values(pattern.get("daysOfWeek"))
            ]
        }
    if kind == "relativeMonthly":
        days = list_values(pattern.get("daysOfWeek"))
        return (
            {
                "nth_weekday": [
                    _INDEX.get(index, 0) if isinstance(index := pattern.get("index"), str) else 0,
                    _DAYS.get(days[0], 0) if isinstance(days[0], str) else 0,
                ]
            }
            if len(days) == 1
            else {"nth_weekday": [0, 0]}
        )
    if kind in ("absoluteMonthly", "absoluteYearly"):
        return {
            "bymonthday": [pattern.get("dayOfMonth")],
            **({"bymonth": [pattern.get("month")]} if kind == "absoluteYearly" else {}),
        }
    return {}


def _graph_description(value: Mapping[str, object], start: object, language: str) -> str:
    pattern, span = value.get("pattern"), value.get("range")
    if not isinstance(pattern, dict) or not isinstance(span, dict):
        return ""
    kind = pattern.get("type")
    if not isinstance(kind, str) or kind not in _FREQUENCIES:
        return ""
    if len(list_values(pattern.get("daysOfWeek"))) > 7:
        return ""
    if isinstance(pattern.get("interval"), bool):
        return ""
    end = _graph_end(span)
    if end is None:
        return ""
    times, zone, all_day = _graph_clock(start, span)
    if not times:
        return ""
    try:
        spec = RecurrenceSpec.model_validate(
            {
                "freq": _FREQUENCIES[kind],
                "interval": pattern.get("interval", 1),
                "anchor_date": span.get("startDate"),
                "times": {"at": times},
                "end": end,
                **_graph_selectors(pattern, kind),
            }
        )
        sentence = describe_calendar(spec, language) if all_day else describe(spec, language)
        return sentence + (f" ({zone})" if zone and not all_day else "")
    except ValidationError:
        return ""


def _graph_end(span: Mapping[str, object]) -> dict[str, object] | None:
    if span.get("type") == "noEnd":
        return {"kind": "never"}
    if span.get("type") == "endDate":
        return {"kind": "on_date", "on_date": span.get("endDate")}
    if span.get("type") == "numbered":
        return {"kind": "after_count", "after_count": span.get("numberOfOccurrences")}
    return None


def _graph_clock(
    start: object, span: Mapping[str, object]
) -> tuple[list[dict[str, int]], str, bool]:
    if not isinstance(start, dict):
        return [], "", False
    if "date" in start:
        # Validation scaffold only: the calendar-only descriptor never displays,
        # stores or executes this placeholder clock for a whole-day event.
        return [{"hour": 0, "minute": 0}], "", True
    instant = parse_provider_datetime(start)
    supplied_zone = span.get("recurrenceTimeZone") or start.get("timeZone")
    zone = supplied_zone if isinstance(supplied_zone, str) else ""
    if instant is None:
        return [], zone, False
    if zone:
        try:
            instant = instant.astimezone(ZoneInfo(zone))
        except ValueError, ZoneInfoNotFoundError:
            return [], zone, False
    return [{"hour": instant.hour, "minute": instant.minute}], zone, False


def render_source_recurrence(value: object, start: object, ctx: RenderContext) -> str:
    if not value:
        return ""
    label = V3Messages.get_recurring_event(ctx.language)
    if isinstance(value, dict):
        sentence = _graph_description(value, start, ctx.language)
        if sentence:
            return render_d_item(Icons.DATE_RANGE, escape_html(sentence)) + _graph_boundaries(
                value, ctx
            )
        # Only the recurrence's declared schema is a source schedule, not arbitrary provider trees.
        source = {
            key: _source_fields(item, fields)
            for key, fields in GRAPH_RECURRENCE_FIELDS.items()
            if isinstance((item := value.get(key)), dict)
        }
        snapshot = MCPDisplaySnapshot(ctx.language)
        text = json.dumps(snapshot.project(source), ensure_ascii=False, indent=2) if source else ""
    else:
        snapshot = MCPDisplaySnapshot(ctx.language)
        rules = snapshot.project([rule for rule in list_values(value) if isinstance(rule, str)])
        text = (
            "\n".join(rule for rule in rules if isinstance(rule, str))
            if isinstance(rules, list)
            else ""
        )
    return (
        render_d_item(Icons.DATE_RANGE, escape_html(label))
        + render_text_content(text)
        + snapshot.notice()
        if text
        else ""
    )


def _graph_boundaries(value: Mapping[str, object], ctx: RenderContext) -> str:
    pattern, span = value.get("pattern"), value.get("range")
    if not isinstance(pattern, dict) or not isinstance(span, dict):
        return ""
    rows: list[str] = []
    anchor = span.get("startDate")
    if isinstance(anchor, str):
        with suppress(ValueError):
            day = date.fromisoformat(anchor)
            rows.append(
                card_label("start", ctx.language)
                + label_separator(ctx.language)
                + format_full_date(day.isoformat(), ctx.language, "UTC")
            )
    week_start = pattern.get("firstDayOfWeek")
    if isinstance(week_start, str) and week_start in _DAYS:
        rows.append(
            card_label("week_start", ctx.language)
            + label_separator(ctx.language)
            + get_day_name(_DAYS[week_start] - 1, ctx.language)
        )
    return "".join(render_d_item(Icons.DATE_RANGE, escape_html(row)) for row in rows)


def _source_fields(value: Mapping[str, object], fields: tuple[str, ...]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in fields:
        item = value.get(key)
        if isinstance(item, str | int | float | bool) or item is None:
            if key in value:
                result[key] = item
        elif isinstance(item, list):
            result[key] = [entry for entry in item if isinstance(entry, str)]
    return result
