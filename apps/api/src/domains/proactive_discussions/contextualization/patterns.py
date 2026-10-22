"""Qualify positive schedule evidence without inventing attendance, disease or absence."""

from calendar import monthrange
from datetime import datetime
from itertools import pairwise
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, StrictBool, StrictInt

from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    DiscussionValue,
    SourceSnapshot,
    evidence_identity,
)

Frequency = Literal["daily", "weekly", "monthly", "yearly", "unknown"]


class ContextPattern(DiscussionValue):
    """What the evidence establishes about a recurrence, and nothing it does not.

    ``basis`` is declared (a native recurrence), observed (a regular civil rhythm
    over complete coverage), possible (a rhythm without full coverage) or
    insufficient; completion is never established from a schedule.
    """

    basis: Literal["declared", "observed", "possible", "insufficient"]
    frequency: Frequency = "unknown"
    interval: Annotated[StrictInt | None, Field(ge=1)] = None
    count: Annotated[StrictInt, Field(ge=0)]
    history_complete: StrictBool = False
    completion: Literal["not_established"] = "not_established"


def _declared(item: DiscussionEvidence) -> tuple[Frequency, int] | None:
    if item.native_recurrence is not None:
        native_frequencies: dict[str, Frequency] = {
            "daily": "daily",
            "weekly": "weekly",
            "absoluteMonthly": "monthly",
            "relativeMonthly": "monthly",
            "absoluteYearly": "yearly",
            "relativeYearly": "yearly",
        }
        return (
            native_frequencies[item.native_recurrence.pattern.type],
            item.native_recurrence.pattern.interval,
        )
    if item.recurrence_spec is not None and item.recurrence_spec.freq != "once":
        return item.recurrence_spec.freq, item.recurrence_spec.interval
    if item.recurrence_rule is None:
        return None
    text = item.recurrence_rule.removeprefix("RRULE:")
    pairs = [part.split("=", 1) for part in text.split(";")]
    if any(len(pair) != 2 for pair in pairs):
        return None
    values = dict(pairs)
    frequencies: dict[str, Frequency] = {
        "DAILY": "daily",
        "WEEKLY": "weekly",
        "MONTHLY": "monthly",
        "YEARLY": "yearly",
    }
    frequency = frequencies.get(values.get("FREQ", ""))
    raw_interval = values.get("INTERVAL", "1")
    if frequency is None or not raw_interval.isascii() or not raw_interval.isdigit():
        return None
    interval = int(raw_interval)
    return (frequency, interval) if 1 <= interval <= 1000 else None


def _distinct(items: tuple[DiscussionEvidence, ...]) -> tuple[DiscussionEvidence, ...]:
    distinct: dict[str, DiscussionEvidence] = {}
    for item in items:
        if item.occurrence_state == "cancelled":
            continue
        key = evidence_identity(item)
        previous = distinct.get(key)
        if (
            previous is not None
            and previous.observed_at == item.observed_at
            and previous.version != item.version
        ):
            raise ValueError("ambiguous occurrence versions")
        if previous is None or item.observed_at >= previous.observed_at:
            distinct[key] = item
    return tuple(distinct.values())


def _moment(item: DiscussionEvidence, zone: ZoneInfo) -> datetime | None:
    if item.planned_date is not None:
        return datetime.combine(item.planned_date, datetime.min.time(), zone)
    if item.occurred_at is not None:
        return item.occurred_at.astimezone(zone)
    return None


def _civil_frequency(moments: tuple[datetime, ...]) -> tuple[Frequency, int]:
    months = [
        second.year * 12 + second.month - first.year * 12 - first.month
        for first, second in pairwise(moments)
    ]
    near_days = all(
        abs(second.day - first.day) <= 3
        or (
            first.day == monthrange(first.year, first.month)[1]
            and second.day == monthrange(second.year, second.month)[1]
        )
        for first, second in pairwise(moments)
    )
    if len(set(months)) == 1 and months[0] > 0 and near_days:
        return ("yearly", months[0] // 12) if months[0] % 12 == 0 else ("monthly", months[0])
    days = [(second.date() - first.date()).days for first, second in pairwise(moments)]
    if len(set(days)) == 1 and days[0] > 0:
        return ("weekly", days[0] // 7) if days[0] % 7 == 0 else ("daily", days[0])
    return "unknown", 1


def _covered(
    items: tuple[DiscussionEvidence, ...],
    moments: tuple[datetime, ...],
    coverage: tuple[SourceSnapshot, ...],
) -> bool:
    references = {item.reference for item in items}
    return any(
        snapshot.complete
        and snapshot.coverage_kind == "occurrences"
        and snapshot.window_start <= moments[0]
        and snapshot.window_end > moments[-1]
        and references <= {item.reference for item in snapshot.items}
        for snapshot in coverage
    )


def qualify_pattern(
    items: tuple[DiscussionEvidence, ...], *, coverage: tuple[SourceSnapshot, ...], timezone: str
) -> ContextPattern:
    """Qualify the recurrence a set of occurrences establishes.

    Cancelled occurrences are ignored and duplicates merged. One native or rule
    declaration makes the pattern declared; otherwise at least three dated
    occurrences of one subject with a constant civil interval make it observed when
    a complete read covers them all, possible when not.

    Args:
        items: The occurrences.
        coverage: The source pages read, for completeness.
        timezone: The person's timezone, in which civil intervals are measured.

    Returns:
        The qualified pattern.

    Raises:
        ValueError: Two versions of one occurrence were read at the same instant.
    """
    unique = _distinct(items)
    insufficient = ContextPattern(basis="insufficient", count=len(unique))
    subjects = {item.subject_id for item in unique if item.subject_id is not None}
    if not unique or len(subjects) > 1:
        return insufficient
    declarations = {declaration for item in unique if (declaration := _declared(item)) is not None}
    if len(declarations) == 1:
        frequency, interval = next(iter(declarations))
        return ContextPattern(
            basis="declared", frequency=frequency, interval=interval, count=len(unique)
        )
    return _observed_pattern(unique, coverage=coverage, timezone=timezone)


def _observed_pattern(
    unique: tuple[DiscussionEvidence, ...], *, coverage: tuple[SourceSnapshot, ...], timezone: str
) -> ContextPattern:
    insufficient = ContextPattern(basis="insufficient", count=len(unique))
    zone = ZoneInfo(timezone)
    moments = tuple(
        sorted(moment for item in unique if (moment := _moment(item, zone)) is not None)
    )
    if len(moments) < 3:
        return insufficient
    frequency, interval = _civil_frequency(moments)
    if frequency == "unknown":
        return insufficient
    complete = _covered(unique, moments, coverage)
    known_subject = all(item.subject_id is not None for item in unique)
    return ContextPattern(
        basis="observed" if complete and known_subject else "possible",
        frequency=frequency,
        interval=interval,
        count=len(unique),
        history_complete=complete,
    )
