"""Pure free/busy slot computation (lot B, 2026-08).

Turns busy intervals (from the Google freeBusy endpoint or from the
minimized start/end events projection) into free slots of a requested
duration, optionally clamped to working hours in the user's timezone.

Everything here is pure and timezone-aware — the edge cases (overlapping
busy blocks, busy crossing the window edges, multi-day working-hours
clamping) decide the answer the user gets, so they are unit-tested in
isolation (test_availability_slots.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.core.constants import AVAILABILITY_MAX_SLOTS

Interval = tuple[datetime, datetime]


def _parse_datetime(raw: Any) -> datetime | None:
    """Parse an RFC3339/ISO datetime or date; None when unparseable.

    Date-only values (all-day events) become midnight UTC — the interval
    then covers the whole day, which is the correct busy semantics.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping/adjacent intervals into a sorted disjoint list."""
    ordered = sorted((start, end) for start, end in intervals if end > start)
    merged: list[list[datetime]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def busy_intervals_from_freebusy(response: dict[str, Any]) -> list[Interval]:
    """Busy intervals from a Google freeBusy response (all calendars merged)."""
    intervals: list[Interval] = []
    for calendar in (response.get("calendars") or {}).values():
        for block in calendar.get("busy", []):
            start = _parse_datetime(block.get("start"))
            end = _parse_datetime(block.get("end"))
            if start and end and end > start:
                intervals.append((start, end))
    return intervals


def busy_intervals_from_events(events: list[dict[str, Any]]) -> list[Interval]:
    """Busy intervals from Google-shaped events (start/end only, minimized)."""
    intervals: list[Interval] = []
    for event in events:
        start_raw = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get(
            "date"
        )
        end_raw = (event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get("date")
        start = _parse_datetime(start_raw)
        end = _parse_datetime(end_raw)
        if start and end and end > start:
            intervals.append((start, end))
    return intervals


def _working_windows(
    window_start: datetime,
    window_end: datetime,
    timezone_name: str,
    start_hour: int,
    end_hour: int,
) -> list[Interval]:
    """Per-day [start_hour, end_hour] windows in the user's timezone."""
    tz = ZoneInfo(timezone_name)
    windows: list[Interval] = []
    day = window_start.astimezone(tz).date()
    last_day = window_end.astimezone(tz).date()
    while day <= last_day:
        day_start = datetime.combine(day, time(start_hour), tzinfo=tz)
        day_end = datetime.combine(day, time(end_hour), tzinfo=tz)
        clamped_start = max(day_start, window_start)
        clamped_end = min(day_end, window_end)
        if clamped_start < clamped_end:
            windows.append((clamped_start, clamped_end))
        day += timedelta(days=1)
    return windows


def find_free_slots(
    busy: list[Interval],
    window_start: datetime,
    window_end: datetime,
    duration_minutes: int,
    *,
    working_hours: tuple[int, int] | None = None,
    timezone_name: str | None = None,
    max_slots: int = AVAILABILITY_MAX_SLOTS,
) -> list[Interval]:
    """Free gaps of at least ``duration_minutes`` inside the window.

    Args:
        busy: Busy intervals (any order, may overlap or cross the window).
        window_start: Inclusive search window start (tz-aware).
        window_end: Exclusive search window end (tz-aware).
        duration_minutes: Minimum usable gap length.
        working_hours: Optional (start_hour, end_hour) clamp, applied per day.
        timezone_name: IANA timezone the working hours are expressed in
            (required when working_hours is given).
        max_slots: Hard cap on the returned slots.

    Returns:
        Sorted list of free (start, end) gaps, each at least the duration.
    """
    duration = timedelta(minutes=duration_minutes)
    if working_hours and timezone_name:
        windows = _working_windows(
            window_start, window_end, timezone_name, working_hours[0], working_hours[1]
        )
    else:
        windows = [(window_start, window_end)]

    merged_busy = merge_intervals(busy)
    slots: list[Interval] = []
    for win_start, win_end in windows:
        cursor = win_start
        for busy_start, busy_end in merged_busy:
            if busy_end <= win_start or busy_start >= win_end:
                continue
            gap_end = min(busy_start, win_end)
            if gap_end - cursor >= duration:
                slots.append((cursor, gap_end))
            cursor = max(cursor, min(busy_end, win_end))
        if win_end - cursor >= duration:
            slots.append((cursor, win_end))
        if len(slots) >= max_slots:
            break
    return slots[:max_slots]
