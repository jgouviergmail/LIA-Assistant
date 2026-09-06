"""The recurrence sentence, composed from localized clauses.

Four clauses in order — the calendar clause, the time clause, and the end
clause — assembled here and worded in :mod:`src.core.i18n_recurrence`. No
wording is ever written in this file: it is the assembly, not the vocabulary.

Day and month names come from ``core.i18n_dates``, so no day name is declared
twice in the codebase.
"""

from __future__ import annotations

from datetime import date

from src.core.i18n_recurrence import get_recurrence_part
from src.core.recurrence.spec import RecurrenceSpec, TimeOfDay


def _join(parts: list[str], language: str) -> str:
    """Join a list the way the reader's language does ("a, b et c").

    Args:
        parts: Already-worded items, in order.
        language: The reader's language.

    Returns:
        The joined list; the last separator differs from the others.
    """
    if len(parts) <= 1:
        return parts[0] if parts else ""
    separator = get_recurrence_part("list_separator", language)
    last = get_recurrence_part("list_last", language)
    return separator.join(parts[:-1]) + last + parts[-1]


def _day_numbers(days: tuple[int, ...], language: str) -> str:
    """Days of month, each carrying its language's own mark, then joined.

    German writes an ordinal point and Chinese a day classifier. Both belong
    to the NUMBER: left in the sentence template they were applied once, after
    the whole list, so two days read "Am 1 und 15." with one ordinal for two.

    Args:
        days: The days of month, in any order.
        language: The reader's language.

    Returns:
        The joined list, each item marked.
    """
    template = get_recurrence_part("day_number", language)
    return _join([template.format(day=day) for day in sorted(days)], language)


def _clock(moment: TimeOfDay) -> str:
    """A moment as `HH:MM` — digits, identical in every language."""
    return f"{moment.hour:02d}:{moment.minute:02d}"


def _format_date(day: date) -> str:
    """A calendar date as `DD/MM/YYYY`."""
    return day.strftime("%d/%m/%Y")


def _weekday_name(iso_weekday: int, language: str) -> str:
    """A weekday name, from the central table (never declared twice)."""
    from src.core.i18n_dates import get_day_name

    return get_day_name(iso_weekday - 1, language)


def _month_name(month: int, language: str) -> str:
    """A month name, from the central table."""
    from src.core.i18n_dates import get_month_name

    return get_month_name(month, language)


def _calendar_clause(spec: RecurrenceSpec, language: str) -> str:
    """Which days the recurrence serves, worded.

    Args:
        spec: The recurrence.
        language: The reader's language.

    Returns:
        The clause, without the time part.
    """
    repeated = spec.interval > 1
    if spec.freq == "once":
        return get_recurrence_part("once", language).format(date=_format_date(spec.anchor_date))
    if spec.freq == "daily":
        key = "daily_n" if repeated else "daily"
        return get_recurrence_part(key, language).format(n=spec.interval)
    if spec.freq == "weekly":
        return _weekly_clause(spec, language, repeated=repeated)
    if spec.freq == "monthly":
        return _monthly_clause(spec, language, repeated=repeated)
    # Both axes are JOINED, like the monthly clause already joins its days: a
    # yearly rule may name several months and several days, and a sentence
    # that showed only the first hid half the series while the engine fired
    # all of it (measured 2026-09-06 — "the 15th of January and July" read
    # "Tous les ans, le 15 janvier", and July arrived unannounced).
    months = _join([_month_name(month, language) for month in sorted(spec.bymonth)], language)
    days = _day_numbers(spec.bymonthday, language)
    key = "yearly_n" if repeated else "yearly"
    return get_recurrence_part(key, language).format(n=spec.interval, day=days, month=months)


#: The three day sets that deserve a phrase instead of a list. Measured on the
#: migrated rows: seven weekday names spelled out where the previous engine
#: said "Tous les jours". Anything else is genuinely irregular and enumerates.
_NAMED_DAY_SETS: tuple[tuple[frozenset[int], str], ...] = (
    (frozenset({1, 2, 3, 4, 5, 6, 7}), "weekly_all"),
    (frozenset({1, 2, 3, 4, 5}), "weekly_workdays"),
    (frozenset({6, 7}), "weekly_weekend"),
)


def _weekly_clause(spec: RecurrenceSpec, language: str, *, repeated: bool) -> str:
    """The weekly clause: a named set when there is one, a day list otherwise.

    Args:
        spec: The recurrence (``freq == "weekly"``).
        language: The reader's language.
        repeated: Whether the interval exceeds one.

    Returns:
        The clause.
    """
    chosen = frozenset(spec.byweekday)
    for days, key in _NAMED_DAY_SETS:
        if chosen == days:
            return get_recurrence_part(f"{key}_n" if repeated else key, language).format(
                n=spec.interval
            )
    listed = _join([_weekday_name(day, language) for day in sorted(spec.byweekday)], language)
    key = "weekly_n" if repeated else "weekly"
    return get_recurrence_part(key, language).format(n=spec.interval, days=listed)


def _monthly_clause(spec: RecurrenceSpec, language: str, *, repeated: bool) -> str:
    """The monthly clause: a day of month, the last day, or an nth weekday.

    Args:
        spec: The recurrence (``freq == "monthly"``).
        language: The reader's language.
        repeated: Whether the interval exceeds one.

    Returns:
        The clause.
    """
    if spec.nth_weekday is not None:
        nth, weekday = spec.nth_weekday
        nth_word = get_recurrence_part("nth_last" if nth == -1 else f"nth_{nth}", language)
        key = "monthly_nth_n" if repeated else "monthly_nth"
        return get_recurrence_part(key, language).format(
            n=spec.interval, nth=nth_word, weekday=_weekday_name(weekday, language)
        )
    if spec.bymonthday == (-1,):
        key = "monthly_last_n" if repeated else "monthly_last"
        return get_recurrence_part(key, language).format(n=spec.interval)
    days = _day_numbers(spec.bymonthday, language)
    key = "monthly_day_n" if repeated else "monthly_day"
    return get_recurrence_part(key, language).format(n=spec.interval, day=days)


def _time_clause(spec: RecurrenceSpec, language: str) -> str:
    """The moments of a served day, worded.

    Args:
        spec: The recurrence.
        language: The reader's language.

    Returns:
        The clause.
    """
    if spec.times.mode == "every":
        step = spec.times.step_minutes
        start = spec.times.start
        end = spec.times.end
        assert step is not None and start is not None and end is not None
        if step % 60 == 0:
            worded_step = get_recurrence_part("step_hours", language).format(n=step // 60)
        else:
            worded_step = get_recurrence_part("step_minutes", language).format(n=step)
        return get_recurrence_part("every_step", language).format(
            step=worded_step, **{"from": _clock(start), "to": _clock(end)}
        )
    moments = _join([_clock(m) for m in spec.times.materialise()], language)
    return get_recurrence_part("at_times", language).format(times=moments)


def _end_clause(spec: RecurrenceSpec, language: str) -> str:
    """When the series stops, worded; empty when it never does.

    Args:
        spec: The recurrence.
        language: The reader's language.

    Returns:
        The clause, or an empty string.
    """
    if spec.end.kind == "on_date" and spec.end.on_date is not None:
        return get_recurrence_part("end_on_date", language).format(
            date=_format_date(spec.end.on_date)
        )
    if spec.end.kind == "after_count" and spec.end.after_count is not None:
        return get_recurrence_part("end_after_count", language).format(n=spec.end.after_count)
    return ""


def describe(spec: RecurrenceSpec, language: str) -> str:
    """The recurrence as one sentence, in the reader's language.

    Args:
        spec: The recurrence.
        language: Any raw locale — normalized downstream.

    Returns:
        A sentence such as "Toutes les 2 semaines, le mardi, à 09:00".
    """
    calendar = _calendar_clause(spec, language)
    times = _time_clause(spec, language)
    ending = _end_clause(spec, language)
    join = get_recurrence_part("clause_join", language)
    tight = get_recurrence_part("clause_join_tight", language)

    # "Every day at 08:00" is ONE phrase; everything else is a sequence of
    # clauses and takes the separator. The test is the TIME clause, not the
    # calendar one: measured 2026-09-06, keying it on the calendar produced
    # "Tous les jours toutes les 2 h" with no comma. Both separators are
    # localized — Chinese joins with a full-width comma and no space.
    # Only the EVERY-DAY shape joins tightly: "Tous les jours à 08:00" reads as
    # one phrase, while "En semaine" and "Le week-end" are circumstantial and
    # take the separator, like every selector clause.
    every_day = spec.freq == "daily" or (
        spec.freq == "weekly" and frozenset(spec.byweekday) == _NAMED_DAY_SETS[0][0]
    )
    one_phrase = every_day and spec.interval == 1 and spec.times.mode == "at"
    sentence = f"{calendar}{tight if one_phrase else join}{times}" if times else calendar
    if ending:
        sentence = f"{sentence}{join}{ending}"
    return sentence
