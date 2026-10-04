"""Structured Places schedules; weekday prose is displayed, never used as a clock."""

from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, timedelta, timezone, tzinfo
from typing import Literal, TypeGuard
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.i18n import resolve_language
from src.core.i18n_cards import card_label
from src.core.i18n_dates import DAY_NAMES
from src.core.time_utils import convert_to_user_timezone, parse_rfc3339
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_date,
    render_kv_rows,
)
from src.domains.agents.display.components.place_dates import provider_date
from src.domains.agents.display.values import list_values, scalar_text


def place_timezone(data: Mapping[str, object]) -> tuple[tzinfo, str, bool]:
    zone = data.get("timeZone")
    name = scalar_text(data.get("place_timezone")) or (
        scalar_text(zone.get("id")) if isinstance(zone, dict) else ""
    )
    if name:
        with suppress(ZoneInfoNotFoundError, ValueError):
            return ZoneInfo(name), name, True
    offset = data.get("utc_offset_minutes", data.get("utcOffsetMinutes"))
    if isinstance(offset, int) and not isinstance(offset, bool) and -840 <= offset <= 840:
        target = timezone(timedelta(minutes=offset))
        return target, str(target), True
    return UTC, "UTC", False


def transition_time(data: Mapping[str, object], ctx: RenderContext, *, opening: bool) -> str:
    raw_key, key = (
        ("nextOpenTime", "next_open_time") if opening else ("nextCloseTime", "next_close_time")
    )
    hours = data.get("currentOpeningHours")
    value = data.get(key) or (hours.get(raw_key) if isinstance(hours, dict) else None)
    parsed = parse_rfc3339(value)
    if parsed is None:
        return ""
    zone, label, _ = place_timezone(data)
    instant = convert_to_user_timezone(parsed, zone)
    if instant is None:
        return ""
    return f"{format_date(instant, ctx.language, zone, 'full', include_time=True)} · {label}"


def _schedule(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _descriptions(value: object) -> list[str]:
    return [line for line in list_values(value) if isinstance(line, str) and line.strip()]


def hours_content(data: Mapping[str, object], ctx: RenderContext) -> str:
    current = _schedule(data, "currentOpeningHours")
    regular = _schedule(data, "regularOpeningHours")
    content = _schedule_content(current, ctx)
    regular_content = _schedule_content(regular, ctx)
    if content and regular_content and content != regular_content:
        content = _schedule_heading("current_hours", content, ctx) + _schedule_heading(
            "regular_hours", regular_content, ctx
        )
    content = content or regular_content or _legacy_hours(data)
    exceptions = _exception_dates(current, ctx)
    if not content and not exceptions:
        return ""
    _, label, known_zone = place_timezone(data)
    caption = card_label("local_hours", ctx.language) + (f" · {label}" if known_zone else "")
    return f'<p class="lia-place-hours__timezone">{escape_html(caption)}</p>{content}{exceptions}'


def _schedule_content(hours: Mapping[str, object], ctx: RenderContext) -> str:
    lines = _descriptions(hours.get("weekdayDescriptions"))
    return (
        render_kv_rows([_hour_pair(line) for line in lines]) if lines else _period_rows(hours, ctx)
    )


def _schedule_heading(
    key: Literal["current_hours", "regular_hours", "special_hours"],
    content: str,
    ctx: RenderContext,
) -> str:
    return f'<p class="lia-place-hours__heading">{escape_html(card_label(key, ctx.language))}</p>{content}'


def _legacy_hours(data: Mapping[str, object]) -> str:
    legacy = _schedule(data, "openingHours")
    lines = _descriptions(
        legacy.get("weekdayDescriptions", legacy.get("weekday_text"))
    ) or _descriptions(data.get("opening_hours"))
    return render_kv_rows([_hour_pair(line) for line in lines]) if lines else ""


def _exception_dates(hours: Mapping[str, object], ctx: RenderContext) -> str:
    dates = [
        date
        for day in list_values(hours.get("specialDays"))
        if isinstance(day, dict)
        if (date := provider_date(day.get("date"), ctx))
    ]
    if not dates:
        return ""
    return _schedule_heading(
        "special_hours", f'<p class="lia-card-text">{escape_html(", ".join(dates))}</p>', ctx
    )


def _hour_pair(line: str) -> tuple[str, str]:
    label, separator, value = line.partition(":")
    return (label.strip(), value.strip()) if separator else (line, "")


def _valid_integer(value: object, upper: int) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= upper


def _point(value: object, language: str) -> str:
    if not isinstance(value, dict):
        return ""
    day, hour, minute = value.get("day"), value.get("hour"), value.get("minute", 0)
    if not (_valid_integer(day, 6) and _valid_integer(hour, 23) and _valid_integer(minute, 59)):
        return ""
    label = (
        provider_date(value.get("date"), RenderContext(language=language))
        or DAY_NAMES[resolve_language(language)][(day + 6) % 7]
    )
    clock = f"{hour:02d}:{minute:02d}"
    partial = (
        f" ({card_label('partial_hours', language)})" if value.get("truncated") is True else ""
    )
    return f"{label} {clock}{partial}"


def _period_rows(hours: Mapping[str, object], ctx: RenderContext) -> str:
    rows: list[tuple[str, str]] = []
    for period in list_values(hours.get("periods")):
        if not isinstance(period, dict):
            continue
        start = _point(period.get("open"), ctx.language)
        end = _point(period.get("close"), ctx.language)
        if start or end:
            rows.append((start or "…", f"→ {end}" if end else "…"))
    return render_kv_rows(rows) if rows else ""


def open_status(data: Mapping[str, object]) -> bool | None:
    legacy = _schedule(data, "opening_hours")
    candidates = (
        data.get("open_now"),
        _schedule(data, "currentOpeningHours").get("openNow"),
        legacy.get("open_now"),
        data.get("is_open"),
    )
    return next((value for value in candidates if isinstance(value, bool)), None)
