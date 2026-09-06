"""Turning a recurrence into the instants it fires at.

No RECURRENCE reaches this module that it could refuse: every refusable shape
was refused by :mod:`src.core.recurrence.spec` at construction. A caller error
is a different matter — :func:`occurrences` refuses a non-positive ``count``,
because silently returning nothing would read as an exhausted series.

Three invariants, each paid for by a measurement (2026-09-06):

- **The days are enumerated, never delegated to a cron.** APScheduler skips the
  day after a transition whose offset changes at local midnight — 142 runs a
  year across 73 zones, `Europe/Paris` included, silently.
- **A wall clock becomes an instant with ``fold=0``.** A time that does not
  exist lands on the first instant that does, which is the shift the previous
  engine already performed.
- **The result is ordered and de-duplicated by INSTANT.** At the spring
  transition two wall-clock times collapse onto one instant, and a later one
  can precede an earlier one (02:30 to 01:30Z, then 03:00 to 01:00Z).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule
from dateutil.rrule import weekday as rrule_weekday

from src.core.recurrence.spec import RecurrenceSpec, TimeOfDay

logger = structlog.get_logger(__name__)

#: How many CONSECUTIVE BARREN days the walker tolerates before giving up.
#:
#: Barren, not scanned: a day that yields an instant is progress, however long
#: the caller keeps asking. Measured 2026-09-06, a budget on scanned days
#: returned 3 999 of 5 000 requested occurrences and said nothing — a caller
#: cannot tell a short series from a truncated one, which is the silent-defect
#: class the impossible-date rule exists to remove.
#:
#: A day can only be barren when every one of its instants was already emitted,
#: which takes a clock change; a run of 400 of those does not exist in the tz
#: database. The guard is therefore unreachable in practice, which is exactly
#: what is asked of a guard — and it says so when it is not.
_BARREN_DAY_BUDGET = 400

#: Days of margin when fast-forwarding. A clock change can move an instant
#: across local midnight; the caller filters on the instant anyway.
_FAST_FORWARD_MARGIN_DAYS = 1


def _day_rule(spec: RecurrenceSpec) -> rrule:
    """The DAY axis of a recurrence, in naive local wall clock.

    Args:
        spec: The recurrence.

    Returns:
        A rule yielding one naive datetime per served day.
    """
    start = datetime.combine(spec.anchor_date, time(0, 0))
    if spec.freq == "once":
        return rrule(DAILY, dtstart=start, count=1)
    if spec.freq == "daily":
        return rrule(DAILY, interval=spec.interval, dtstart=start)
    if spec.freq == "weekly":
        return rrule(
            WEEKLY,
            interval=spec.interval,
            dtstart=start,
            byweekday=[day - 1 for day in sorted(spec.byweekday)],
            wkst=0,
        )
    if spec.freq == "monthly":
        if spec.nth_weekday is not None:
            nth, weekday = spec.nth_weekday
            return rrule(
                MONTHLY,
                interval=spec.interval,
                dtstart=start,
                byweekday=rrule_weekday(weekday - 1, nth),
            )
        return rrule(
            MONTHLY,
            interval=spec.interval,
            dtstart=start,
            bymonthday=sorted(spec.bymonthday),
        )
    return rrule(
        YEARLY,
        interval=spec.interval,
        dtstart=start,
        bymonth=sorted(spec.bymonth),
        bymonthday=sorted(spec.bymonthday),
    )


def _instant(day: date, moment: TimeOfDay, tz: ZoneInfo) -> datetime:
    """The UTC instant of a wall-clock moment on a local day.

    ``fold=0`` resolves a non-existent wall clock to the first instant that
    exists, and an ambiguous one to its FIRST occurrence — so the repeated hour
    of an autumn transition fires once, not twice.

    Args:
        day: The local calendar day.
        moment: The wall-clock moment.
        tz: The zone the wall clock is read in.

    Returns:
        The instant, in UTC.
    """
    wall = datetime.combine(day, time(moment.hour, moment.minute), tzinfo=tz).replace(fold=0)
    return wall.astimezone(UTC)


def _walk_days(spec: RecurrenceSpec, from_day: date | None, *, counted: bool) -> Iterator[datetime]:
    """The day rule's iterator, fast-forwarded when that is legitimate.

    Args:
        spec: The recurrence.
        from_day: Local day to skip ahead to, or ``None`` to walk from the anchor.
        counted: Whether the series ends after a number of instants. Such a
            series counts from its beginning, so it may never skip ahead — and
            it needs no fast-forward, being bounded by that very count.

    Yields:
        Naive local days, ascending.
    """
    rule = _day_rule(spec)
    # A generator, not a `return`: `dateutil` is checked with `follow_imports =
    # "skip"`, so everything it hands back is `Any`. Yielding through this
    # frame gives the caller the declared type by construction, where returning
    # it directly would need a cast that asserts what the library already does.
    days: Iterable[datetime] = (
        rule
        if counted or from_day is None
        else rule.xafter(datetime.combine(from_day, time(0, 0)), inc=True)
    )
    yield from days


def _fresh_instants(
    day: date, moments: tuple[TimeOfDay, ...], tz: ZoneInfo, seen: set[datetime]
) -> list[datetime]:
    """The instants a local day contributes that were not emitted already.

    Two wall clocks can collapse onto one instant — an autumn transition, or a
    civil day a zone deleted outright (Pacific/Apia dropped 30 December 2011).
    De-duplicating here is what keeps the series strictly increasing.

    Args:
        day: The local calendar day.
        moments: The day's wall-clock moments.
        tz: The zone they are read in.
        seen: Instants already emitted; **extended in place** with the ones
            returned, so a caller iterating days shares one memory.

    Returns:
        The new instants, ascending.
    """
    fresh: list[datetime] = []
    for instant in sorted(_instant(day, moment, tz) for moment in moments):
        if instant not in seen:
            seen.add(instant)
            fresh.append(instant)
    return fresh


def series(
    spec: RecurrenceSpec, tz: ZoneInfo, *, from_day: date | None = None
) -> Iterator[datetime]:
    """The series, ascending and de-duplicated by instant. Lazy.

    Args:
        spec: The recurrence.
        tz: The zone its wall clocks are read in.
        from_day: Skip the day rule ahead to this local day instead of walking
            it from the anchor.

    Yields:
        Every instant of the series, in order.
    """
    moments = spec.times.materialise()
    limit = spec.end.after_count if spec.end.kind == "after_count" else None
    last_day = spec.end.on_date if spec.end.kind == "on_date" else None
    seen: set[datetime] = set()
    emitted = 0
    barren = 0

    for naive_day in _walk_days(spec, from_day, counted=limit is not None):
        day = naive_day.date()
        if last_day is not None and day > last_day:
            return
        fresh = _fresh_instants(day, moments, tz, seen)
        for instant in fresh:
            yield instant
            emitted += 1
            if limit is not None and emitted >= limit:
                return
        barren = 0 if fresh else barren + 1
        if barren > _BARREN_DAY_BUDGET:
            # Never silent: a truncated series and a short one look alike from
            # outside, and this is the one place that knows which it is.
            logger.warning(
                "recurrence_series_abandoned",
                freq=spec.freq,
                interval=spec.interval,
                emitted=emitted,
                barren_days=barren,
            )
            return


def occurrences(
    spec: RecurrenceSpec, timezone: str, *, after: datetime, count: int
) -> list[datetime]:
    """The next ``count`` instants STRICTLY after ``after``.

    Strict is the single convention of this package. The engine it replaces
    mixed both: its listing included its own reference while its re-arm forced
    strictness with a microsecond.

    Args:
        spec: The recurrence.
        timezone: IANA zone its wall clocks are read in.
        after: Reference instant (UTC); the result is strictly later.
        count: How many instants to return.

    Returns:
        Up to ``count`` instants, ascending. Empty when the series is over.

    Raises:
        ValueError: If ``count`` is not positive.
    """
    if count <= 0:
        raise ValueError("count must be positive")
    tz = ZoneInfo(timezone)
    from_day = (after.astimezone(tz) - timedelta(days=_FAST_FORWARD_MARGIN_DAYS)).date()
    found: list[datetime] = []
    for instant in series(spec, tz, from_day=from_day):
        if instant > after:
            found.append(instant)
            if len(found) >= count:
                break
    return found


def next_occurrence(spec: RecurrenceSpec, timezone: str, *, after: datetime) -> datetime | None:
    """The next instant strictly after ``after``, or ``None`` when none remains.

    Args:
        spec: The recurrence.
        timezone: IANA zone.
        after: Reference instant (UTC).

    Returns:
        The instant, or ``None`` for an exhausted or past series — which a
        consumer stores as a null trigger.
    """
    found = occurrences(spec, timezone, after=after, count=1)
    return found[0] if found else None


def slots_between(
    spec: RecurrenceSpec, timezone: str, *, start: datetime, end: datetime, cap: int = 1000
) -> list[datetime]:
    """Every instant in ``[start, end)``.

    The same series :func:`occurrences` walks, by construction — a second
    implementation would be a second authority, and the weekly grid colours its
    cells by EQUALITY with these instants.

    Args:
        spec: The recurrence.
        timezone: IANA zone.
        start: Window start (UTC), included.
        end: Window end (UTC), excluded.
        cap: Most instants to return; a window larger than the caller expects
            is truncated rather than unbounded.

    Returns:
        The instants, ascending.
    """
    tz = ZoneInfo(timezone)
    from_day = (start.astimezone(tz) - timedelta(days=_FAST_FORWARD_MARGIN_DAYS)).date()
    found: list[datetime] = []
    for instant in series(spec, tz, from_day=from_day):
        if instant >= end:
            break
        if instant >= start:
            found.append(instant)
            if len(found) >= cap:
                break
    return found
