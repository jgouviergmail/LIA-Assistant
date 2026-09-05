"""
Schedule helpers for Scheduled Actions.

Uses APScheduler CronTrigger (already installed) to compute next trigger times.
No additional dependency needed (no croniter).
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from src.core.time_utils import now_utc

# ISO 8601 weekday mapping: 1=Monday..7=Sunday -> APScheduler day names
DAY_NAMES: dict[int, str] = {
    1: "mon",
    2: "tue",
    3: "wed",
    4: "thu",
    5: "fri",
    6: "sat",
    7: "sun",
}


def compute_next_trigger_utc(
    days_of_week: list[int],
    hour: int,
    minute: int,
    user_timezone: str,
    after: datetime | None = None,
) -> datetime:
    """
    Compute the next trigger time in UTC using APScheduler CronTrigger.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour of execution (0-23) in user timezone.
        minute: Minute of execution (0-59) in user timezone.
        user_timezone: IANA timezone (e.g., "Europe/Paris").
        after: Reference datetime (UTC). Defaults to now.

    Returns:
        Next trigger time in UTC (timezone-aware).

    Example:
        >>> compute_next_trigger_utc([1, 3, 5], 19, 30, "Europe/Paris")
        datetime(2026, 2, 28, 18, 30, tzinfo=UTC)  # Next Mon/Wed/Fri at 19:30 Paris
    """
    tz = ZoneInfo(user_timezone)
    trigger = _cron(days_of_week, hour, minute, tz)
    reference = after or now_utc()
    next_fire = _next_fire(trigger, days_of_week, hour, minute, tz, reference)
    if next_fire is None:
        # Should never happen with valid inputs, but handle gracefully
        raise ValueError(
            f"Could not compute next trigger for days={days_of_week}, "
            f"hour={hour}, minute={minute}, tz={user_timezone}"
        )
    return next_fire


def _cron(days_of_week: list[int], hour: int, minute: int, tz: ZoneInfo) -> CronTrigger:
    """The one place a routine's schedule becomes a trigger."""
    return CronTrigger(
        day_of_week=",".join(DAY_NAMES[d] for d in sorted(days_of_week)),
        hour=hour,
        minute=minute,
        timezone=tz,
    )


#: How far :func:`_skipped_gap_run` looks for a day the cron jumped over. The
#: schedule is weekly, so a skipped day is always within the next seven.
_GAP_LOOKAHEAD_DAYS = 7


def _skipped_gap_run(
    days_of_week: list[int],
    hour: int,
    minute: int,
    tz: ZoneInfo,
    reference: datetime,
    fired: datetime | None,
) -> datetime | None:
    """The run the cron SKIPPED because its wall-clock time fell in a midnight gap.

    APScheduler shifts a non-existent wall-clock time forward by the gap —
    02:30 on the spring-forward day fires at 03:30 — except when the gap opens
    at 00:00, where it skips the whole local day. Measured on 3.11.2 over every
    IANA zone and every 2026 transition: 2 112 slots shifted, 72 skipped, all
    72 in the 00:00-00:59 hour of the six zones that change their clocks at
    midnight (Santiago, Havana, Cairo, Beirut, …).

    The repair applies the SAME rule everywhere: a run on its own day, at the
    first instant that exists. ``fold=0`` on a non-existent wall-clock time
    resolves to the pre-transition offset, whose instant is exactly the
    post-gap time — the shift APScheduler already performs elsewhere.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Wall-clock hour in ``tz``.
        minute: Wall-clock minute.
        tz: The routine's zone.
        reference: Runs at or before this instant (UTC) do not count.
        fired: What the cron proposed; ``None`` when it proposed nothing.

    Returns:
        The earliest skipped run strictly after ``reference``, or ``None`` when
        the cron skipped nothing.
    """
    configured = set(days_of_week)
    first_day = reference.astimezone(tz).date()
    last_day = (
        fired.astimezone(tz).date() - timedelta(days=1)
        if fired is not None
        else first_day + timedelta(days=_GAP_LOOKAHEAD_DAYS)
    )
    day = first_day
    while day <= last_day:
        if day.isoweekday() in configured:
            wall_clock = datetime.combine(day, time(hour, minute), tzinfo=tz).replace(fold=0)
            instant = wall_clock.astimezone(UTC)
            # A wall-clock time that survives the round trip exists; the cron
            # handled it itself. One that does not is inside a gap.
            exists = instant.astimezone(tz).replace(tzinfo=None) == wall_clock.replace(tzinfo=None)
            if not exists and instant > reference:
                return instant
        day += timedelta(days=1)
    return None


def _next_fire(
    trigger: CronTrigger,
    days_of_week: list[int],
    hour: int,
    minute: int,
    tz: ZoneInfo,
    reference: datetime,
) -> datetime | None:
    """The next run strictly after ``reference`` (UTC), midnight gaps repaired.

    The ONLY reader of ``CronTrigger.get_next_fire_time`` in this module: every
    public helper goes through it, so the repair cannot apply to the listing
    and not to the re-arm.
    """
    fired = trigger.get_next_fire_time(None, reference)
    fired_utc = fired.astimezone(UTC) if fired is not None else None
    skipped = _skipped_gap_run(days_of_week, hour, minute, tz, reference, fired_utc)
    return skipped if skipped is not None else fired_utc


def compute_next_triggers_utc(
    days_of_week: list[int],
    hour: int,
    minute: int,
    user_timezone: str,
    *,
    count: int,
    after: datetime | None = None,
) -> list[datetime]:
    """The next ``count`` runs, in UTC, one per local day at most.

    Same engine as :func:`compute_next_trigger_utc` — the schedule is never
    re-interpreted, here or in the browser.

    **At the daylight-saving fall-back the wall-clock time exists twice**, so
    the cron yields two distinct instants for the same local day. Listing both
    would print the same line twice, which is why occurrences are de-duplicated
    by local DAY: the model allows exactly one time per day, so a second
    instant for that day is the transition artefact, never a second run the
    user asked for.

    Callers rendering these must convert each instant with ``astimezone`` — at
    the spring-forward the wall-clock time may not exist, and only the instant
    knows the hour the run will really happen at.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour of execution (0-23) in the user's timezone.
        minute: Minute of execution (0-59).
        user_timezone: IANA timezone.
        count: How many runs to return.
        after: Reference datetime (UTC). Defaults to now.

    Returns:
        Up to ``count`` UTC instants, strictly increasing.

    Raises:
        ValueError: If ``count`` is not positive.
    """
    if count <= 0:
        raise ValueError("count must be positive")

    tz = ZoneInfo(user_timezone)
    trigger = _cron(days_of_week, hour, minute, tz)
    runs: list[datetime] = []
    seen_days: set[date] = set()
    reference = after or now_utc()

    # Bounded: the de-duplication can drop at most one occurrence per
    # transition, so a small multiple of `count` cannot loop forever.
    for _ in range(count * 3):
        if len(runs) == count:
            break
        instant = _next_fire(trigger, days_of_week, hour, minute, tz, reference)
        if instant is None:
            break
        reference = instant + timedelta(microseconds=1)
        local_day = instant.astimezone(tz).date()
        if local_day in seen_days:
            continue
        seen_days.add(local_day)
        runs.append(instant)
    return runs


def compute_next_trigger_after_execution(
    days_of_week: list[int],
    hour: int,
    minute: int,
    user_timezone: str,
    *,
    executed_at: datetime,
    now: datetime | None = None,
) -> datetime:
    """Re-arm a routine that has just run, without running it twice tonight.

    ``compute_next_trigger_utc(after=now)`` is correct 364 days a year and
    wrong on one: at the fall-back the wall-clock time exists twice, so "the
    next run after now" is the SAME local time an hour later, and the routine
    fires a second time. Measured against APScheduler 3.11 over the 2026
    transitions of seven zones: 54 double runs, and the affected hour depends
    on the zone (Santiago is hit at 23:00, not at 2 a.m.).

    The rule is the model's own: exactly one time per day means at most one run
    per LOCAL DAY. Everything outside the repeated hour is untouched —
    verified by differential simulation, 15 036 re-arm scenarios, zero
    divergence beyond the 54 defective ones.

    ``max(executed_at, now)`` guards the other direction: a late tick must not
    schedule a run that has already passed.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour of execution (0-23) in the user's timezone.
        minute: Minute of execution (0-59).
        user_timezone: IANA timezone.
        executed_at: The due time of the run that just happened (UTC).
        now: Current time (UTC). Defaults to now.

    Returns:
        The next run, strictly after ``executed_at``, on a later local day.

    Raises:
        ValueError: If no future run can be computed.
    """
    tz = ZoneInfo(user_timezone)
    trigger = _cron(days_of_week, hour, minute, tz)
    executed_day = executed_at.astimezone(tz).date()

    start = max(executed_at, now or now_utc()) + timedelta(microseconds=1)
    fired = _next_fire(trigger, days_of_week, hour, minute, tz, start)
    if fired is not None and fired.astimezone(tz).date() == executed_day:
        # The repeated hour: skip to the start of the next local day.
        tomorrow = datetime.combine(executed_day + timedelta(days=1), time(0, 0), tzinfo=tz)
        fired = _next_fire(trigger, days_of_week, hour, minute, tz, tomorrow.astimezone(UTC))

    if fired is None:
        raise ValueError(
            f"Could not re-arm days={days_of_week}, hour={hour}, "
            f"minute={minute}, tz={user_timezone}"
        )
    return fired


def compute_rearm_trigger(
    days_of_week: list[int],
    hour: int,
    minute: int,
    user_timezone: str,
    *,
    due_at: datetime,
    now: datetime | None = None,
) -> datetime:
    """Re-arm a routine after a tick, scheduled OR manual.

    The two cases must not be conflated, and the executor runs the same code
    for both (``execute_single_action`` serves the scheduler and the "run now"
    button):

    - **A due slot was consumed** (``due_at <= now``): that local day is
      served, so :func:`compute_next_trigger_after_execution` applies and the
      fall-back cannot fire the routine twice.
    - **Nothing was due** (manual run ahead of schedule): no slot was consumed.
      Applying the local-day rule here would DROP the upcoming run — testing a
      08:00 routine at 07:00 would push it to tomorrow. The plain "next after
      now" is correct, exactly as before.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour of execution (0-23) in the user's timezone.
        minute: Minute of execution (0-59).
        user_timezone: IANA timezone.
        due_at: The routine's pending due time when the tick started.
        now: Current time (UTC). Defaults to now.

    Returns:
        The next run in UTC.
    """
    reference = now or now_utc()
    if due_at <= reference:
        return compute_next_trigger_after_execution(
            days_of_week, hour, minute, user_timezone, executed_at=due_at, now=reference
        )
    return compute_next_trigger_utc(days_of_week, hour, minute, user_timezone, after=reference)


def week_start(tz: ZoneInfo, *, now: datetime | None = None) -> date:
    """The local Monday of the ISO week containing ``now``.

    Args:
        tz: The routine's zone — the week is the ROUTINE's week, not the
            server's, which may still be on Sunday when Auckland is on Monday.
        now: Reference instant (UTC). Defaults to now.

    Returns:
        The Monday, as a local calendar date.
    """
    local_today = (now or now_utc()).astimezone(tz).date()
    return local_today - timedelta(days=local_today.isoweekday() - 1)


def _local_day_start(day: date, tz: ZoneInfo) -> datetime:
    """The instant just BEFORE local midnight of ``day``, so a 00:00 slot counts."""
    midnight = datetime.combine(day, time(0, 0), tzinfo=tz).replace(fold=0)
    return midnight.astimezone(UTC) - timedelta(microseconds=1)


def week_slots(
    days_of_week: list[int],
    hour: int,
    minute: int,
    user_timezone: str,
    *,
    now: datetime | None = None,
) -> list[datetime]:
    """The instants a routine fires at during the ISO week containing ``now``.

    Past days included: the weekly timeline colours every cell of the current
    week, the ones already served and the ones still to come, and it colours
    them by EQUALITY with a run's ``slot_at`` — so these must be the very
    instants the executor armed, produced by the same engine and the same
    de-duplication (:func:`compute_next_triggers_utc`).

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour of execution (0-23) in the user's timezone.
        minute: Minute of execution (0-59).
        user_timezone: IANA timezone.
        now: Reference instant (UTC). Defaults to now.

    Returns:
        One UTC instant per configured day of the week, strictly increasing.
    """
    tz = ZoneInfo(user_timezone)
    monday = week_start(tz, now=now)
    next_monday = monday + timedelta(days=7)
    runs = compute_next_triggers_utc(
        days_of_week, hour, minute, user_timezone, count=7, after=_local_day_start(monday, tz)
    )
    return [run for run in runs if run.astimezone(tz).date() < next_monday]


def local_day_slot(
    days_of_week: list[int],
    hour: int,
    minute: int,
    user_timezone: str,
    *,
    day: date,
) -> datetime | None:
    """The instant a routine fires at on ONE local day, or ``None`` if it does not.

    Same engine and same reference shape as :func:`week_slots` (the instant
    before local midnight), so the two agree on every day — including the
    repeated hour of the fall-back, where both keep the FIRST occurrence.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour of execution (0-23) in the user's timezone.
        minute: Minute of execution (0-59).
        user_timezone: IANA timezone.
        day: The local calendar day.

    Returns:
        The UTC instant, or ``None`` when ``day`` is not a configured weekday.
    """
    tz = ZoneInfo(user_timezone)
    runs = compute_next_triggers_utc(
        days_of_week, hour, minute, user_timezone, count=1, after=_local_day_start(day, tz)
    )
    if not runs or runs[0].astimezone(tz).date() != day:
        return None
    return runs[0]


def served_slot(
    days_of_week: list[int],
    hour: int,
    minute: int,
    user_timezone: str,
    *,
    due_at: datetime,
    now: datetime,
) -> datetime | None:
    """Which slot a run that starts now serves — the cell it will colour.

    A DUE run (``due_at <= now``, the same test :func:`compute_rearm_trigger`
    applies) serves its due instant. A MANUAL run serves the day's slot only
    when that slot has already passed: a "Test now" at 07:00 of an 08:00
    routine is a rehearsal, not the day's execution, and a test on a day the
    routine does not run serves nothing.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour of execution (0-23) in the user's timezone.
        minute: Minute of execution (0-59).
        user_timezone: IANA timezone.
        due_at: The routine's pending due instant when the run started (UTC).
        now: When the run started (UTC).

    Returns:
        The served UTC instant, or ``None`` for a rehearsal.
    """
    if due_at <= now:
        return due_at
    tz = ZoneInfo(user_timezone)
    slot = local_day_slot(days_of_week, hour, minute, user_timezone, day=now.astimezone(tz).date())
    if slot is None or slot > now:
        return None
    return slot


def validate_days_of_week(days: list[int]) -> bool:
    """Validate that days_of_week contains valid ISO weekday numbers."""
    return bool(days) and all(1 <= d <= 7 for d in days) and len(days) == len(set(days))


def format_schedule_display(
    days_of_week: list[int],
    hour: int,
    minute: int,
    language: str = "fr",
) -> str:
    """
    Format schedule for human-readable display.

    Args:
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        hour: Hour (0-23).
        minute: Minute (0-59).
        language: Language code for day names.

    Returns:
        Human-readable schedule string.

    Example:
        >>> format_schedule_display([1, 3, 5], 19, 30, "fr")
        "Lun, Mer, Ven à 19:30"
    """
    from src.core.i18n_automation import get_schedule_day_set
    from src.core.i18n_dates import get_day_name_short, get_time_connector

    sorted_days = sorted(days_of_week)

    # The three sets worth a phrase; anything else is listed day by day.
    if sorted_days == [1, 2, 3, 4, 5, 6, 7]:
        days_str = get_schedule_day_set("every_day", language)
    elif sorted_days == [1, 2, 3, 4, 5]:
        days_str = get_schedule_day_set("weekdays", language)
    elif sorted_days == [6, 7]:
        days_str = get_schedule_day_set("weekend", language)
    else:
        # 0-indexed on Monday there, ISO (1..7) here. The abbreviations are
        # declared per language rather than truncated: "Mittwoch"[:3] is "Mit",
        # and German writes "Mi".
        days_str = ", ".join(get_day_name_short(d - 1, language) for d in sorted_days)

    connector = get_time_connector(language)
    separator = f" {connector} " if connector else " "
    return f"{days_str}{separator}{hour:02d}:{minute:02d}"
