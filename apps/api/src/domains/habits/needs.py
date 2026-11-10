"""Recurring needs — what a person keeps asking LIA for, never a locked hour (ADR-375).

A need is a domain asked on enough distinct days of the observation window,
spread over more than one week and still asked recently. The hour is a
DESCRIPTOR: the median and the part of the day describe the need, the first
quartile pre-fills the routine a proposal would create. None of them decides
whether the need exists — the owner's reorientation of 2026-11-06 (« hors de
question d'attendre la même demande à la même heure ») replaced ADR-214's
circular-concentration lock, which a single off-hour ask per week defeated.

Everything here is pure and I/O-free: per-day local hours in, a ``Need`` out.
The thresholds come from settings and are calibrated by
``scripts/habits/measure_proposals.py``.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from typing import Any, Literal

PartOfDay = Literal["morning", "afternoon", "evening", "night"]
Cadence = Literal["daily", "weekdays", "weekly"]

#: Payload version of a ``recurring_request`` row since ADR-375 (v1 carried
#: the lock: ``shape`` and ``trigger_hour``).
NEED_PAYLOAD_VERSION = 2

#: The weekday count below which « working days only » is not yet claimed.
_WEEKDAYS_MIN_DAYS = 5


@dataclass(frozen=True, slots=True)
class NeedThresholds:
    """The bars a need is held to — read once from settings."""

    window_days: int
    min_days: int
    min_weeks: int
    recent_days: int
    automate_share: float
    automate_min_days: int
    weekly_min_same_dow: int
    weekly_dow_fraction: float
    weekend_tolerance: int
    part_share: float

    @classmethod
    def from_settings(cls, settings: Any) -> NeedThresholds:
        """Read every bar from a settings view.

        Args:
            settings: The application settings (or a test view of them).

        Returns:
            The thresholds.
        """
        return cls(
            window_days=int(settings.recurrence_window_days),
            min_days=int(settings.recurrence_min_distinct_days),
            min_weeks=int(settings.recurrence_need_min_weeks),
            recent_days=int(settings.recurrence_need_recent_days),
            automate_share=float(settings.recurrence_automate_share),
            automate_min_days=int(settings.recurrence_automate_min_days),
            weekly_min_same_dow=int(settings.recurrence_weekly_min_same_dow),
            weekly_dow_fraction=float(settings.recurrence_weekly_dow_fraction),
            weekend_tolerance=int(settings.recurrence_weekend_tolerance),
            part_share=float(settings.recurrence_part_of_day_share),
        )


@dataclass(frozen=True, slots=True)
class Need:
    """One recurring need, described.

    Attributes:
        domain: The registered domain asked for.
        cadence: ``weekly`` (one weekday holds the days), ``weekdays`` (working
            days only) or ``daily``.
        weekday: 0=Monday..6=Sunday for a weekly need, else None.
        usual_hour: Median local hour of the asks, read across midnight
            (descriptor).
        prefill_hour: First quartile rounded down to a quarter hour — the hour
            a routine would be READY by, before the person usually asks.
        part_of_day: Where most asks fall, or ``any`` when none dominates.
        distinct_days: Days with an ask inside the window.
        active_days: Days the person used LIA inside the window (never fewer
            than ``distinct_days``).
        occurrences: Asks inside the window (one per clock hour and day).
        at_automation_bar: Whether the need is steady enough to propose
            automating it.
        last_day: The latest day with an ask.
    """

    domain: str
    cadence: Cadence
    weekday: int | None
    usual_hour: float
    prefill_hour: float
    part_of_day: PartOfDay | Literal["any"]
    distinct_days: int
    active_days: int
    occurrences: int
    at_automation_bar: bool
    last_day: date


def part_of_day(hour: float) -> PartOfDay:
    """The part of the day a local hour belongs to.

    Args:
        hour: Local hour, fractional.

    Returns:
        ``morning`` [5, 12), ``afternoon`` [12, 18), ``evening`` [18, 23),
        ``night`` otherwise.
    """
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def _unwrapped(hours: Sequence[float]) -> list[float]:
    """The hours on a line that does not cut the person's asks in two.

    The clock wraps: read on a plain line, asks at 23:30 and 00:30 are
    twenty-three hours apart and their median falls at noon. The line starts
    after the WIDEST empty arc between asks instead, so asks either side of
    midnight stay neighbours; a value past 24 is read modulo 24.

    Args:
        hours: Local hours (at least one).

    Returns:
        The hours in ascending order on that line.
    """
    ordered = sorted(hours)
    if len(ordered) < 2:
        return ordered
    widest, start = max(
        (later - earlier, index + 1) for index, (earlier, later) in enumerate(pairwise(ordered))
    )
    if ordered[0] + 24 - ordered[-1] >= widest:
        return ordered
    return ordered[start:] + [hour + 24 for hour in ordered[:start]]


def median_hour(hours: Sequence[float]) -> float:
    """The median local hour of a set of asks, read across midnight.

    Args:
        hours: Local hours (at least one).

    Returns:
        The median, in [0, 24).
    """
    return float(statistics.median(_unwrapped(hours))) % 24


def prefill_hour(hours: Sequence[float]) -> float:
    """The hour a routine should be ready by: the first quartile, on a quarter.

    Args:
        hours: Every ask's local hour (at least one).

    Returns:
        The first quartile (inclusive interpolation, read across midnight),
        rounded DOWN to the quarter hour.
    """
    line = _unwrapped(hours)
    first_quartile = (
        line[0] if len(line) < 2 else statistics.quantiles(line, n=4, method="inclusive")[0]
    )
    return (math.floor(first_quartile * 4) / 4) % 24


def _dominant_part(hours: Sequence[float], share: float) -> PartOfDay | Literal["any"]:
    parts = Counter(part_of_day(hour) for hour in hours)
    part, count = parts.most_common(1)[0]
    return part if count / len(hours) >= share else "any"


def _cadence(days: Sequence[date], thresholds: NeedThresholds) -> tuple[Cadence, int | None]:
    weekday, count = Counter(day.weekday() for day in days).most_common(1)[0]
    if (
        count >= thresholds.weekly_min_same_dow
        and count / len(days) >= thresholds.weekly_dow_fraction
    ):
        return "weekly", weekday
    weekend_days = sum(1 for day in days if day.weekday() >= 5)
    if len(days) >= _WEEKDAYS_MIN_DAYS and weekend_days <= thresholds.weekend_tolerance:
        return "weekdays", None
    return "daily", None


def detect_need(
    domain: str,
    days: Mapping[date, Sequence[float]],
    *,
    active_days: int,
    today: date,
    thresholds: NeedThresholds,
) -> Need | None:
    """Describe the recurring need behind a domain's asks — or say there is none.

    Args:
        domain: The registered domain.
        days: Per local day, the hours it was asked at (any span; the window is
            applied here).
        active_days: Days the person used LIA inside the same window.
        today: The person's local date (window anchor).
        thresholds: The bars.

    Returns:
        The need, or None when the asks are too few, too bunched in one week,
        or no longer recent.
    """
    start = today - timedelta(days=thresholds.window_days)
    in_window = {day: list(hours) for day, hours in days.items() if start < day <= today and hours}
    if len(in_window) < thresholds.min_days:
        return None
    ordered = sorted(in_window)
    if len({day.isocalendar()[:2] for day in ordered}) < thresholds.min_weeks:
        return None
    if ordered[-1] < today - timedelta(days=thresholds.recent_days):
        return None

    hours = [hour for day in ordered for hour in in_window[day]]
    cadence, weekday = _cadence(ordered, thresholds)
    active = max(active_days, len(ordered))
    at_bar = cadence == "weekly" or (
        len(ordered) >= thresholds.automate_min_days
        and len(ordered) / active >= thresholds.automate_share
    )
    return Need(
        domain=domain,
        cadence=cadence,
        weekday=weekday,
        usual_hour=median_hour(hours),
        prefill_hour=prefill_hour(hours),
        part_of_day=_dominant_part(hours, thresholds.part_share),
        distinct_days=len(ordered),
        active_days=active,
        occurrences=len(hours),
        at_automation_bar=at_bar,
        last_day=ordered[-1],
    )


def need_payload(need: Need, *, usual_intent: str | None) -> dict[str, Any]:
    """The ``recurring_request`` row payload of a need — ONE builder for every writer.

    Args:
        need: The detected need.
        usual_intent: The ledger's dominant request descriptor, when recorded.
            Absent from the payload otherwise — never a placeholder the panel
            would have to translate.

    Returns:
        The versioned, JSON-safe payload.
    """
    payload: dict[str, Any] = {
        "version": NEED_PAYLOAD_VERSION,
        "domain": need.domain,
        "cadence": need.cadence,
        "weekday": need.weekday,
        "usual_hour": round(need.usual_hour, 2),
        "prefill_hour": need.prefill_hour,
        "part_of_day": need.part_of_day,
        "distinct_days": need.distinct_days,
        "active_days": need.active_days,
        "occurrences": need.occurrences,
        "at_automation_bar": need.at_automation_bar,
        "last_day": need.last_day.isoformat(),
    }
    if usual_intent:
        payload["usual_intent"] = usual_intent
    return payload
