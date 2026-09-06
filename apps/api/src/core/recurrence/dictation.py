"""From what a reader SAYS to the recurrence it means.

A `RecurrenceSpec` is a nested shape — two axes, a mode inside one of them, an
end rule inside the other. That shape is right for storage and wrong for a
model: the catalogue publishes parameters, and its compaction flattens a
referenced sub-model to `{"type": "string"}` (measured 2026-09-06), so a tool
declaring the spec directly would announce a contract the validator refuses.

So the SPOKEN surface is flat — one named parameter per question a person
answers — and this module is the ONE place that turns it into a spec. The
stored vocabulary stays unique; this is a projection, in the same sense the
`relative_trigger` mini-language already is.

Everything here is arithmetic. What a model does with a sentence is measured
separately (`scripts/recurrence/measure_transcription.py`), because that half
needs a provider key and this half must never.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from pydantic import ValidationError

from src.core.recurrence.spec import (
    SELECTORS_READ_BY,
    DailyTimes,
    RecurrenceError,
    RecurrenceFreq,
    RecurrenceSpec,
    SeriesEnd,
    TimeOfDay,
)

#: The vocabulary a tool exposes. Kept here, beside the translation, so a
#: manifest and a tool signature cannot drift from what this accepts.
REPEAT_VALUES: tuple[str, ...] = ("once", "daily", "weekly", "monthly", "yearly")

#: `<nth>:<ISO weekday>` — "2:2" is the second Tuesday. `-1` is the last one.
NTH_WEEKDAY_PATTERN = r"^(-1|[1-5]):([1-7])$"

#: `HH:MM` on a 24-hour clock. Published as-is by the manifest, so what the
#: planner is told to produce is literally what this accepts (ADR-184).
CLOCK_PATTERN = r"^([01]?\d|2[0-3]):([0-5]\d)$"

#: `YYYY-MM-DD`.
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

#: The spoken name of each stored selector. A refusal must speak the words the
#: reader used — the model relays this sentence to a person, and `bymonthday`
#: names nothing they ever said.
SPOKEN_NAME_OF: dict[str, str] = {
    "byweekday": "weekdays",
    "bymonthday": "month_days",
    "bymonth": "months",
    "nth_weekday": "nth_weekday",
}

_CLOCK = re.compile(CLOCK_PATTERN)
_DATE = re.compile(DATE_PATTERN)


def _moment(spoken: str) -> TimeOfDay:
    """One `HH:MM`, or a refusal that names what could not be read.

    Args:
        spoken: The clock as the caller wrote it.

    Returns:
        The moment.

    Raises:
        RecurrenceError: When it is not a 24-hour clock.
    """
    match = _CLOCK.match(spoken.strip())
    if match is None:
        raise RecurrenceError(f"{spoken!r} is not a time of day; use HH:MM on a 24-hour clock")
    return TimeOfDay(hour=int(match.group(1)), minute=int(match.group(2)))


def _day(spoken: str, *, field: str) -> date:
    """One `YYYY-MM-DD`, or a refusal that names the field and the value.

    Args:
        spoken: The date as the caller wrote it.
        field: The parameter it came from, for the message.

    Returns:
        The date.

    Raises:
        RecurrenceError: When it is not an ISO date.
    """
    text = spoken.strip()
    if not _DATE.match(text):
        raise RecurrenceError(f"{field} must be a date as YYYY-MM-DD, got {spoken!r}")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:  # a well-shaped impossible date, e.g. 2026-02-30
        raise RecurrenceError(f"{field}: {exc}") from exc


def _times_of(
    times: Sequence[str] | None,
    every_minutes: int | None,
    window_start: str | None,
    window_end: str | None,
) -> DailyTimes:
    """The moments of a served day, from either of the two ways to say them.

    Args:
        times: Explicit clocks.
        every_minutes: A step, in minutes.
        window_start: First clock of the stepped window.
        window_end: Last clock of the stepped window.

    Returns:
        The moments, as the spec stores them.

    Raises:
        RecurrenceError: When both ways are used, when neither is, or when the
            stepped one is missing a bound.
    """
    stepped = every_minutes is not None
    if stepped and times:
        raise RecurrenceError("say the times explicitly OR a step within a window, not both")
    if stepped:
        if window_start is None or window_end is None:
            raise RecurrenceError("a step needs its window: give window_start and window_end")
        return DailyTimes(
            mode="every",
            step_minutes=every_minutes,
            start=_moment(window_start),
            end=_moment(window_end),
        )
    if not times:
        raise RecurrenceError("a schedule needs at least one time of day")
    return DailyTimes(mode="at", at=tuple(_moment(t) for t in times))


def _end_of(until_date: str | None, max_occurrences: int | None) -> SeriesEnd:
    """Where the series stops, from either of the two ways to say it.

    Args:
        until_date: The LAST local day, included.
        max_occurrences: How many INSTANTS the series holds.

    Returns:
        The end rule.

    Raises:
        RecurrenceError: When both are given — they can disagree, and nothing
            could say which one the reader meant.
    """
    if until_date is not None and max_occurrences is not None:
        raise RecurrenceError("say when the series ends OR how many times it runs, not both")
    if until_date is not None:
        return SeriesEnd(kind="on_date", on_date=_day(until_date, field="until_date"))
    if max_occurrences is not None:
        return SeriesEnd(kind="after_count", after_count=max_occurrences)
    return SeriesEnd()


def _nth_of(nth_weekday: str | None) -> tuple[int, int] | None:
    """`"2:2"` as (nth, ISO weekday), or a refusal naming the shape.

    Args:
        nth_weekday: The spoken form.

    Returns:
        The pair, or None when nothing was said.

    Raises:
        RecurrenceError: When the shape is not `<nth>:<weekday>`.
    """
    if nth_weekday is None:
        return None
    match = re.match(NTH_WEEKDAY_PATTERN, nth_weekday.strip())
    if match is None:
        raise RecurrenceError(
            f"nth_weekday must be '<nth>:<weekday>' with nth in -1 or 1..5 and "
            f"weekday in 1..7 (1=Monday), got {nth_weekday!r}"
        )
    return int(match.group(1)), int(match.group(2))


def _repaired_frequency(
    repeat: str,
    weekdays: Sequence[int] | None,
    month_days: Sequence[int] | None,
    months: Sequence[int] | None,
    nth: tuple[int, int] | None,
    repeat_every: int,
) -> str:
    """The frequency a plausible transcription MEANT, when that is certain.

    Two rewordings are exact identities rather than guesses, and both are what
    a model most naturally answers:

    - "every weekday at 8" as `daily` + `weekdays`. At `repeat_every=1` a
      daily rule restricted to named days IS the weekly rule on those days.
    - "the 15th of January and July" as `monthly` + `months`. At
      `repeat_every=1` a monthly rule restricted to named months IS the
      yearly rule on them.

    An interval breaks both identities — one period in three is not one week
    in three — so a repair is only offered at `repeat_every=1`; anything else
    falls through and is refused rather than guessed.

    Args:
        repeat: The frequency as spoken.
        weekdays: ISO weekdays.
        month_days: Days of month.
        months: Months.
        nth: The nth-weekday pair.
        repeat_every: One period out of N.

    Returns:
        The frequency to build with — the spoken one, unless an exact
        identity says otherwise.
    """
    if repeat_every != 1:
        return repeat
    if repeat == "daily" and weekdays and not (month_days or months or nth):
        return "weekly"
    if repeat == "monthly" and months and month_days and nth is None:
        return "yearly"
    return repeat


def _check_unread_selector(
    repeat: str,
    weekdays: Sequence[int] | None,
    month_days: Sequence[int] | None,
    months: Sequence[int] | None,
    nth: tuple[int, int] | None,
) -> None:
    """Refuse a selector this frequency would never read.

    The spec refuses these too — that is the invariant, and it holds for every
    writer including the REST API. This says the same thing in the words the
    reader used, because a model has to relay it to a person, and because
    Pydantic would otherwise wrap the refusal into a `ValidationError` naming
    fields nobody typed.

    Args:
        repeat: The frequency, already repaired where an identity applied.
        weekdays: ISO weekdays.
        month_days: Days of month.
        months: Months.
        nth: The nth-weekday pair.

    Raises:
        RecurrenceError: When a selector foreign to this frequency was given.
    """
    read = SELECTORS_READ_BY[repeat]
    given = {
        field
        for field, value in (
            ("byweekday", weekdays),
            ("bymonthday", month_days),
            ("bymonth", months),
            ("nth_weekday", nth),
        )
        if value
    }
    unread = sorted(SPOKEN_NAME_OF[field] for field in given - read)
    if not unread:
        return
    accepted = sorted(SPOKEN_NAME_OF[field] for field in read)
    raise RecurrenceError(
        f"a {repeat} schedule does not use {', '.join(unread)}; "
        f"it uses {', '.join(accepted) if accepted else 'no day selector'}"
    )


def _check_selector(
    repeat: str,
    weekdays: Sequence[int] | None,
    month_days: Sequence[int] | None,
    months: Sequence[int] | None,
    nth: tuple[int, int] | None,
) -> None:
    """Refuse a frequency whose day selector is missing or doubled.

    The spec refuses these too, but its messages speak of fields; these speak
    of what the reader said, which is what the model has to relay.

    Args:
        repeat: The frequency.
        weekdays: ISO weekdays.
        month_days: Days of month.
        months: Months.
        nth: The nth-weekday pair.

    Raises:
        RecurrenceError: When the combination cannot fire.
    """
    if repeat == "weekly" and not weekdays:
        raise RecurrenceError("a weekly schedule needs at least one weekday")
    if repeat == "monthly" and not (month_days or nth):
        raise RecurrenceError("a monthly schedule needs a day of month, or an nth weekday")
    if repeat == "monthly" and month_days and nth:
        raise RecurrenceError("a monthly schedule takes a day of month OR an nth weekday, not both")
    if repeat == "yearly" and not (months and month_days):
        raise RecurrenceError("a yearly schedule needs a month and a day of month")


def _readable(error: ValidationError) -> str:
    """A Pydantic failure as one sentence a model can relay to a person.

    The structural refusals are raised inside validators, so Pydantic wraps
    them; its own rendering names internal fields and appends a documentation
    URL, and an error payload returned to a model must carry neither.

    Args:
        error: What Pydantic raised.

    Returns:
        The refusal messages, joined; never empty.
    """
    messages = []
    for detail in error.errors():
        text = str(detail.get("msg", "")).removeprefix("Value error, ").strip()
        if text and text not in messages:
            messages.append(text)
    return "; ".join(messages) or "this schedule cannot fire"


def recurrence_from_parameters(
    *,
    repeat: str,
    today: date,
    times: Sequence[str] | None = None,
    repeat_every: int = 1,
    weekdays: Sequence[int] | None = None,
    month_days: Sequence[int] | None = None,
    months: Sequence[int] | None = None,
    nth_weekday: str | None = None,
    every_minutes: int | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    until_date: str | None = None,
    max_occurrences: int | None = None,
    starting_on: str | None = None,
) -> RecurrenceSpec:
    """The recurrence a spoken schedule means.

    The ONE translation from the flat vocabulary a tool exposes to the spec
    every other layer reads. Selector VALUES are handed over as spoken — the
    spec folds duplicates and sorts them, so this never does it twice — but
    the frequency is first repaired where a reworded transcription means
    exactly one thing (:func:`_repaired_frequency`), and a selector the
    resulting frequency would never read is refused in the reader's own
    words rather than dropped in silence.

    Args:
        repeat: `once`, `daily`, `weekly`, `monthly` or `yearly`.
        today: The reader's local today — the anchor when none is given, and
            passed in rather than read here so this module stays a pure
            function of its arguments.
        times: Explicit clocks, `HH:MM`.
        repeat_every: One period out of N (2 = every other week).
        weekdays: ISO weekdays, 1=Monday..7=Sunday.
        month_days: 1..31, or -1 for the last day.
        months: 1..12.
        nth_weekday: `<nth>:<weekday>`, e.g. `2:2` for the second Tuesday.
        every_minutes: A step inside a window, instead of explicit times.
        window_start: First clock of that window.
        window_end: Last clock of that window.
        until_date: The LAST local day the series serves.
        max_occurrences: How many instants the series holds.
        starting_on: The day the series starts; also the phase when
            `repeat_every` is greater than one.

    Returns:
        The recurrence.

    Raises:
        RecurrenceError: For any combination that could never fire, with a
            message written for the model to relay to the reader.
    """
    if repeat not in REPEAT_VALUES:
        raise RecurrenceError(
            f"{repeat!r} is not a frequency; use one of {', '.join(REPEAT_VALUES)}"
        )

    nth = _nth_of(nth_weekday)
    repeat = _repaired_frequency(repeat, weekdays, month_days, months, nth, repeat_every)
    _check_selector(repeat, weekdays, month_days, months, nth)
    _check_unread_selector(repeat, weekdays, month_days, months, nth)

    # ONE exception leaves this function, as the contract above says. The
    # structural refusals are raised inside Pydantic validators and come back
    # wrapped; a caller catching the documented type would otherwise miss
    # them, which is what let "the 31st of February" walk through both tools'
    # error handling and raise instead of answering (measured 2026-09-06).
    try:
        return RecurrenceSpec(
            freq=cast_freq(repeat),
            interval=repeat_every,
            anchor_date=_day(starting_on, field="starting_on") if starting_on else today,
            byweekday=tuple(weekdays or ()),
            bymonthday=tuple(month_days or ()),
            bymonth=tuple(months or ()),
            nth_weekday=nth,
            times=_times_of(times, every_minutes, window_start, window_end),
            end=_end_of(until_date, max_occurrences),
        )
    except ValidationError as exc:
        raise RecurrenceError(_readable(exc)) from exc


def cast_freq(repeat: str) -> RecurrenceFreq:
    """Narrow a validated string to the spec's own type.

    Args:
        repeat: A value already checked against `REPEAT_VALUES`.

    Returns:
        The same value, typed.
    """
    match repeat:
        case "once" | "daily" | "weekly" | "monthly" | "yearly":
            return repeat
        case _:  # pragma: no cover - guarded by the caller
            raise RecurrenceError(f"{repeat!r} is not a frequency")
