"""Date arithmetic the model must not do in its head (ADR-318).

Dates are a measured weak point (ADR-310): a model counts the days to a
deadline, names the weekday of a date or adds « ten working days » from memory
of a calendar it does not hold. This engine answers six questions exactly, from
ISO values the model resolved itself (``core/date_contract``):

- ``now`` — the current moment in a timezone;
- ``difference`` — days, weeks and calendar months/years between two moments,
  and the ELAPSED time when a time of day is involved (real time: noon to noon
  across a clock change is 25 hours);
- ``add`` — a date plus or minus an amount of a unit; a month that has no such
  day clamps to its last day and SAYS so;
- ``weekday`` — the weekday, ISO week and day of the year of a date;
- ``business_days`` — Monday to Friday between two dates, both included
  (public holidays are NOT excluded, and the answer says it);
- ``convert_timezone`` — a moment read in one zone, shown in another.

Two rules: a date stays a date (a question in days is not answered in hours),
and a value nobody can read propagates as :class:`UnreadableDateError` for the
tool to word with the ADR-310 refusal — the engine never guesses. The weekday
names are English on purpose: the payload is technical English (ADR-256) and
the model words the answer in the person's language.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final, Literal, get_args
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from src.core.date_contract import read_moment

__all__ = [
    "DATE_OPERATIONS",
    "DATE_UNITS",
    "DateAnswer",
    "DateArithmeticError",
    "DateFailure",
    "DateOperation",
    "DateRequest",
    "DateUnit",
    "answer_date_request",
]

DateOperation = Literal["now", "difference", "add", "weekday", "business_days", "convert_timezone"]
DateUnit = Literal["years", "months", "weeks", "days", "business_days", "hours", "minutes"]
DateFailure = Literal["missing_parameter", "invalid_parameter", "unknown_timezone", "out_of_range"]

#: The questions the engine answers, published by the manifest and the schema.
DATE_OPERATIONS: Final[tuple[str, ...]] = get_args(DateOperation)
#: The units ``add`` accepts, published likewise.
DATE_UNITS: Final[tuple[str, ...]] = get_args(DateUnit)

_WEEKDAYS: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_SATURDAY: Final = 5
_WORKING_DAYS_PER_WEEK: Final = 5
_DAYS_PER_WEEK: Final = 7
_MINUTES_PER_HOUR: Final = 60
_TIMEZONE_EXAMPLES: Final = "Europe/Paris, America/New_York or Asia/Tokyo"
#: How much of a refused value a refusal echoes back.
_ECHO_MAX_CHARS: Final = 64

_Moment = date | datetime


class DateArithmeticError(ValueError):
    """A date question the engine refuses, with a reason the model can act on.

    Attributes:
        reason: A bounded code.
    """

    def __init__(self, reason: DateFailure, message: str) -> None:
        super().__init__(message)
        self.reason: DateFailure = reason


@dataclass(frozen=True)
class DateRequest:
    """One date question, as the tool received it.

    Attributes:
        operation: One of :data:`DATE_OPERATIONS`.
        date: The moment the question is about; the current date (or instant,
            for ``convert_timezone``) when omitted.
        other_date: The second moment of ``difference`` and ``business_days``.
        amount: How much ``add`` adds (negative subtracts).
        unit: One of :data:`DATE_UNITS`, for ``add``.
        timezone: Where values without an offset are read, and the zone
            ``now`` reports; the person's timezone when omitted.
        to_timezone: The target zone of ``convert_timezone``.
    """

    operation: str
    date: str | None = None
    other_date: str | None = None
    amount: int | None = None
    unit: str | None = None
    timezone: str | None = None
    to_timezone: str | None = None


@dataclass(frozen=True)
class DateAnswer:
    """The answer: one sentence for the model, and the facts behind it."""

    summary: str
    facts: dict[str, object]


@dataclass(frozen=True)
class _Question:
    """A request with its zone resolved and its clock fixed."""

    request: DateRequest
    zone: ZoneInfo
    now: datetime

    def moment(self) -> _Moment:
        """``date``, or today in the zone when it was omitted."""
        if not (self.request.date or "").strip():
            return self.now.astimezone(self.zone).date()
        return read_moment(str(self.request.date), self.zone)

    def other_moment(self) -> _Moment:
        """``other_date``, required."""
        return read_moment(_required(self.request.other_date, "other_date", self), self.zone)


def _missing(name: str, question: _Question) -> DateArithmeticError:
    return DateArithmeticError(
        "missing_parameter", f"The '{question.request.operation}' operation needs '{name}'."
    )


def _required(value: str | None, name: str, question: _Question) -> str:
    if value is None or not str(value).strip():
        raise _missing(name, question)
    return str(value)


def _named_zone(name: str) -> ZoneInfo:
    """An IANA zone, or a refusal naming the accepted form.

    ``OSError`` is a refusal too: a name longer than the filesystem allows is
    looked up as a path and fails there (measured on Linux and Windows), with a
    message that would carry a path of the server — never echoed.
    """
    key = name.strip()
    try:
        return ZoneInfo(key)
    except (KeyError, ValueError, OSError) as error:
        raise DateArithmeticError(
            "unknown_timezone",
            f"Unknown timezone '{key[:_ECHO_MAX_CHARS]}': pass an IANA name such as "
            f"{_TIMEZONE_EXAMPLES}.",
        ) from error


def _text(moment: _Moment) -> str:
    if isinstance(moment, datetime):
        return moment.isoformat(timespec="seconds")
    return moment.isoformat()


def _local_day(moment: _Moment, zone: ZoneInfo) -> date:
    return moment.astimezone(zone).date() if isinstance(moment, datetime) else moment


def _instant(moment: _Moment, zone: ZoneInfo) -> datetime:
    if isinstance(moment, datetime):
        return moment
    return datetime.combine(moment, time(), tzinfo=zone)


def _zone_label(moment: datetime) -> str:
    key = getattr(moment.tzinfo, "key", None)
    return str(key) if key else moment.strftime("UTC%z")


def _plural(count: int, unit: str) -> str:
    return f"{count} {unit}" + ("" if abs(count) == 1 else "s")


# ---------------------------------------------------------------------------
# now / weekday / convert_timezone
# ---------------------------------------------------------------------------


def _now(question: _Question) -> DateAnswer:
    local = question.now.astimezone(question.zone)
    weekday = _WEEKDAYS[local.weekday()]
    week = local.isocalendar().week
    return DateAnswer(
        summary=f"It is {_text(local)} ({weekday}, ISO week {week}) in {question.zone.key}.",
        facts={
            "result": _text(local),
            "date": local.date().isoformat(),
            "weekday": weekday,
            "iso_week": week,
            "timezone": question.zone.key,
        },
    )


def _weekday(question: _Question) -> DateAnswer:
    day = _local_day(question.moment(), question.zone)
    name = _WEEKDAYS[day.weekday()]
    iso = day.isocalendar()
    day_of_year = day.timetuple().tm_yday
    return DateAnswer(
        summary=(
            f"{day.isoformat()} is a {name} (ISO week {iso.week} of {iso.year}, "
            f"day {day_of_year} of the year)."
        ),
        facts={
            "date": day.isoformat(),
            "result": name,
            "weekday": name,
            "iso_week": iso.week,
            "iso_year": iso.year,
            "day_of_year": day_of_year,
            "is_weekend": day.weekday() >= _SATURDAY,
        },
    )


def _convert_timezone(question: _Question) -> DateAnswer:
    target = _named_zone(_required(question.request.to_timezone, "to_timezone", question))
    if (question.request.date or "").strip():
        moment = question.moment()
        if not isinstance(moment, datetime):
            raise DateArithmeticError(
                "invalid_parameter",
                "convert_timezone needs a time: pass an ISO datetime (YYYY-MM-DDTHH:MM).",
            )
        source = moment
    else:
        source = question.now.astimezone(question.zone)
    converted = source.astimezone(target)
    weekday = _WEEKDAYS[converted.weekday()]
    return DateAnswer(
        summary=(
            f"{_text(source)} ({_zone_label(source)}) is {_text(converted)} "
            f"({target.key}, {weekday})."
        ),
        facts={
            "from": _text(source),
            "from_timezone": _zone_label(source),
            "result": _text(converted),
            "to_timezone": target.key,
            "weekday": weekday,
        },
    )


# ---------------------------------------------------------------------------
# difference / business_days
# ---------------------------------------------------------------------------


def _calendar_point(moment: _Moment, zone: ZoneInfo, *, with_time: bool) -> _Moment:
    """The wall-clock value calendar months are counted on."""
    if not with_time:
        return _local_day(moment, zone)
    return _instant(moment, zone).astimezone(zone).replace(tzinfo=None)


def _duration(first: _Moment, second: _Moment, zone: ZoneInfo) -> dict[str, int]:
    """Real elapsed time — an absolute difference, never a wall-clock one.

    Both ends go to UTC first: Python subtracts two datetimes that share one
    ``tzinfo`` object on their WALL clocks, so noon to noon across a clock
    change read 24 hours where 25 went by (measured).
    """
    end = _instant(second, zone).astimezone(UTC)
    seconds = (end - _instant(first, zone).astimezone(UTC)).total_seconds()
    sign = -1 if seconds < 0 else 1
    total_minutes = int(abs(seconds) // _MINUTES_PER_HOUR)
    hours, minutes = divmod(total_minutes, _MINUTES_PER_HOUR)
    return {"hours": sign * hours, "minutes": sign * minutes, "total_minutes": sign * total_minutes}


def _elapsed_text(duration: dict[str, int]) -> str:
    """Elapsed time as text, its sign carried even under one hour."""
    sign = "-" if duration["total_minutes"] < 0 else ""
    return f"{sign}{abs(duration['hours'])} h {abs(duration['minutes'])} min"


def _difference(question: _Question) -> DateAnswer:
    first, second = question.moment(), question.other_moment()
    zone = question.zone
    with_time = isinstance(first, datetime) or isinstance(second, datetime)
    days = (_local_day(second, zone) - _local_day(first, zone)).days
    sign = -1 if days < 0 else 1
    weeks, rest = divmod(abs(days), _DAYS_PER_WEEK)
    delta = relativedelta(
        _calendar_point(second, zone, with_time=with_time),
        _calendar_point(first, zone, with_time=with_time),
    )
    calendar = {"years": delta.years, "months": delta.months, "days": delta.days}
    facts: dict[str, object] = {
        "from": _text(first),
        "to": _text(second),
        "result": _plural(days, "day"),
        "days": days,
        "weeks": {"weeks": sign * weeks, "days": sign * rest},
        "calendar": calendar,
    }
    if not with_time:
        summary = (
            f"From {_text(first)} to {_text(second)}: {_plural(days, 'day')} "
            f"({_plural(sign * weeks, 'week')} and {_plural(sign * rest, 'day')}; "
            f"{_plural(delta.years, 'year')}, {_plural(delta.months, 'month')} and "
            f"{_plural(delta.days, 'day')})."
        )
        return DateAnswer(summary=summary, facts=facts)
    # With a time of day the ELAPSED time is the answer, and the calendar
    # breakdown carries the hours: 23:00 to 01:00 is two hours, on dates one
    # day apart — « 1 day » beside « 0 days » read as a contradiction.
    calendar["hours"] = delta.hours
    calendar["minutes"] = delta.minutes
    duration = _duration(first, second, zone)
    elapsed = _elapsed_text(duration)
    facts["duration"] = duration
    facts["result"] = elapsed
    summary = (
        f"From {_text(first)} to {_text(second)}: {elapsed} elapsed "
        f"({duration['total_minutes']} minutes); calendar: {_plural(delta.years, 'year')}, "
        f"{_plural(delta.months, 'month')}, {_plural(delta.days, 'day')}, "
        f"{_plural(delta.hours, 'hour')} and {_plural(delta.minutes, 'minute')}; the dates "
        f"are {_plural(abs(days), 'day')} apart."
    )
    return DateAnswer(summary=summary, facts=facts)


def _count_business_days(first: date, second: date) -> int:
    """Monday to Friday between two dates, both included — in constant time."""
    sign = 1
    if second < first:
        first, second, sign = second, first, -1
    weeks, extra = divmod((second - first).days + 1, _DAYS_PER_WEEK)
    remainder = sum(
        1 for offset in range(extra) if (first.weekday() + offset) % _DAYS_PER_WEEK < _SATURDAY
    )
    return sign * (weeks * _WORKING_DAYS_PER_WEEK + remainder)


def _business_days(question: _Question) -> DateAnswer:
    zone = question.zone
    first = _local_day(question.moment(), zone)
    second = _local_day(question.other_moment(), zone)
    count = _count_business_days(first, second)
    calendar_days = abs((second - first).days) + 1
    return DateAnswer(
        summary=(
            f"From {first.isoformat()} to {second.isoformat()}, both included: "
            f"{_plural(count, 'business day')} (Monday to Friday) out of "
            f"{_plural(calendar_days, 'calendar day')}; public holidays are not excluded."
        ),
        facts={
            "from": first.isoformat(),
            "to": second.isoformat(),
            "result": str(count),
            "business_days": count,
            "calendar_days": calendar_days,
            "public_holidays_excluded": False,
        },
    )


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

_FIXED_STEPS: Final[dict[str, Callable[[int], timedelta]]] = {
    "weeks": lambda amount: timedelta(weeks=amount),
    "days": lambda amount: timedelta(days=amount),
}
_ELAPSED_STEPS: Final[dict[str, Callable[[int], timedelta]]] = {
    "hours": lambda amount: timedelta(hours=amount),
    "minutes": lambda amount: timedelta(minutes=amount),
}


def _add_business_days(start: _Moment, count: int) -> _Moment:
    """Move ``count`` working days, the start excluded (a spreadsheet's WORKDAY).

    Whole weeks are jumped at once, so a huge count costs nothing and ends in an
    overflow rather than a loop; only the last four days are walked. A weekend
    start is first moved to the working day it borders, which is what makes the
    jump land on the right weekday.
    """
    if count == 0:
        return start
    step = 1 if count > 0 else -1
    day = start
    while day.weekday() >= _SATURDAY:
        day -= timedelta(days=step)
    weeks, remaining = divmod(abs(count), _WORKING_DAYS_PER_WEEK)
    day += timedelta(weeks=step * weeks)
    while remaining:
        day += timedelta(days=step)
        if day.weekday() < _SATURDAY:
            remaining -= 1
    return day


def _shift(base: _Moment, amount: int, unit: str, zone: ZoneInfo) -> tuple[_Moment, bool]:
    """The shifted moment, and whether a day the month lacks was clamped."""
    if unit in ("years", "months"):
        step = relativedelta(years=amount) if unit == "years" else relativedelta(months=amount)
        shifted: _Moment = base + step
        return shifted, shifted.day != base.day
    fixed = _FIXED_STEPS.get(unit)
    if fixed is not None:
        return base + fixed(amount), False
    if unit == "business_days":
        return _add_business_days(base, amount), False
    instant = _instant(base, zone)
    # Elapsed time is added to the INSTANT, so two hours are two real hours
    # even across a clock change; the result is shown back in the same zone.
    return (instant.astimezone(UTC) + _ELAPSED_STEPS[unit](amount)).astimezone(
        instant.tzinfo
    ), False


def _add(question: _Question) -> DateAnswer:
    request = question.request
    if request.amount is None:
        raise _missing("amount", question)
    unit = _required(request.unit, "unit", question).strip()
    if unit not in DATE_UNITS:
        raise DateArithmeticError(
            "invalid_parameter", f"Unknown unit '{unit}'. Accepted: {', '.join(DATE_UNITS)}."
        )
    amount = int(request.amount)
    base = question.moment()
    try:
        result, clamped = _shift(base, amount, unit, question.zone)
    except (OverflowError, ValueError) as error:
        raise DateArithmeticError(
            "out_of_range", "The result falls outside the calendar (years 1 to 9999)."
        ) from error
    weekday = _WEEKDAYS[result.weekday()]
    sign = "+" if amount >= 0 else "-"
    summary = f"{_text(base)} {sign} {abs(amount)} {unit} = {_text(result)} ({weekday})."
    if clamped:
        summary += " The month has no such day: the date was moved to its last day."
    return DateAnswer(
        summary=summary,
        facts={
            "from": _text(base),
            "amount": amount,
            "unit": unit,
            "result": _text(result),
            "weekday": weekday,
            "day_clamped": clamped,
        },
    )


_HANDLERS: Final[dict[str, Callable[[_Question], DateAnswer]]] = {
    "now": _now,
    "difference": _difference,
    "add": _add,
    "weekday": _weekday,
    "business_days": _business_days,
    "convert_timezone": _convert_timezone,
}


def answer_date_request(request: DateRequest, *, user_zone: ZoneInfo, now: datetime) -> DateAnswer:
    """Answer one date question.

    Args:
        request: The question.
        user_zone: The person's timezone — where values without an offset are
            read unless the request names another zone.
        now: The current instant (aware), injected so « today » is testable.

    Returns:
        The answer; its facts always carry ``operation`` and ``result``.

    Raises:
        DateArithmeticError: A missing or invalid parameter, an unknown zone,
            a result outside the calendar.
        UnreadableDateError: A date value that is not ISO 8601 — worded by the
            tool with the ADR-310 refusal.
    """
    handler = _HANDLERS.get(request.operation)
    if handler is None:
        raise DateArithmeticError(
            "invalid_parameter",
            f"Unknown operation '{request.operation}'. Accepted: {', '.join(DATE_OPERATIONS)}.",
        )
    timezone = (request.timezone or "").strip()
    zone = _named_zone(timezone) if timezone else user_zone
    answer = handler(_Question(request=request, zone=zone, now=now))
    return DateAnswer(
        summary=answer.summary, facts={"operation": request.operation, **answer.facts}
    )
