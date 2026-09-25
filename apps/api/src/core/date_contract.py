"""The one contract of a date a tool is given (ADR-310, ADR-318).

ADR-310 found a forecast tool serving TODAY's weather for « demain » as a
success: the tool fell back in silence on a value it could not read, and the
loop could only blame the service. The rule since then is that a tool never
replaces a value it cannot read — it refuses it, with the accepted format and
the person's current date, everything the model needs to correct its own call.

That refusal and the reading it answers used to live in the weather module. The
calculation, activity and gallery tools take dates too (ADR-318), so the
contract lives here, once:

- :data:`ISO_MOMENT_DESCRIPTION` is the wording a manifest AND a ``@tool``
  signature publish — the ReAct loop binds the schema, never the manifest, so
  one constant must reach both (ADR-310);
- :func:`read_moment` reads ISO 8601 and nothing else, and keeps a date a date:
  « how many days » and « how many hours » are different questions;
- :func:`unreadable_date_message` is the refusal every such tool returns;
- :func:`period_bounds` turns two optional values into a period, a day being a
  WHOLE day (from its local midnight to the next one).

In ``core`` beside ``tool_outcome`` for the same reason: several packages read
it and none of them should own it.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Final

from src.core.time_utils import now_in_timezone

__all__ = [
    "ISO_MOMENT_DESCRIPTION",
    "InvertedPeriodError",
    "UnreadableDateError",
    "period_bounds",
    "read_moment",
    "unreadable_date_message",
]

#: The wording of a tool parameter that carries a date or a datetime.
ISO_MOMENT_DESCRIPTION: Final = (
    "An ISO date (YYYY-MM-DD) or ISO datetime (YYYY-MM-DDTHH:MM, with or without an "
    "offset; without one it is read in the user's timezone). Resolve a relative "
    "expression yourself from the current date before passing it."
)


class InvertedPeriodError(ValueError):
    """A period whose end does not come after its start."""


class UnreadableDateError(ValueError):
    """A date value a tool cannot read.

    Attributes:
        reference: The value as the caller sent it, stripped.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"unreadable date reference: {reference!r}")
        self.reference = reference


def read_moment(reference: str, zone: tzinfo) -> date | datetime:
    """Read an ISO date or datetime, and nothing else.

    Args:
        reference: What the model passed.
        zone: Where a datetime written without an offset is read — the
            person's timezone, or the one the call names.

    Returns:
        A ``date`` for a date, an AWARE ``datetime`` for a datetime.

    Raises:
        UnreadableDateError: For anything that is not ISO 8601 — a relative
            word, a local spelling, an impossible day.
    """
    text = reference.strip()
    if not text:
        raise UnreadableDateError(text)
    # A date is tried first: ``datetime.fromisoformat`` accepts it too, at
    # midnight, and a date must stay a date. Not a date: try a datetime below.
    with suppress(ValueError):
        return date.fromisoformat(text)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as error:
        raise UnreadableDateError(text) from error
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=zone)


def unreadable_date_message(reference: str, user_timezone: str) -> str:
    """The refusal a tool returns for a date it cannot read.

    Technical English (ADR-256): the model corrects its own call from it, so it
    carries what the tool accepts and the person's current date.

    Args:
        reference: The unreadable value.
        user_timezone: The person's IANA timezone, which defines « today ».

    Returns:
        The message.
    """
    today = now_in_timezone(user_timezone).date().isoformat()
    return (
        f"date '{reference}' is not readable: pass an ISO date (YYYY-MM-DD) or an "
        f"ISO datetime, resolved from the current date; today is {today} "
        f"({user_timezone})."
    )


def _start_of(moment: date | datetime, zone: tzinfo) -> datetime:
    if isinstance(moment, datetime):
        return moment
    return datetime.combine(moment, time(), tzinfo=zone)


def _end_of(moment: date | datetime, zone: tzinfo) -> datetime:
    """The EXCLUSIVE end: a date ends at the next local midnight, a datetime is an instant."""
    if isinstance(moment, datetime):
        return moment
    return datetime.combine(moment + timedelta(days=1), time(), tzinfo=zone)


def period_bounds(
    start: str | None,
    end: str | None,
    zone: tzinfo,
    *,
    now: datetime,
    default_days: int | None,
) -> tuple[datetime | None, datetime | None]:
    """Turn two optional ISO values into a half-open period ``[since, until)``.

    A date is a WHOLE day in ``zone``: « from the 21st to the 22nd » covers both
    days, and « on the 21st » is one day. A datetime is taken as the instant it
    names.

    Args:
        start: First day or instant, inclusive; None when not given.
        end: Last day (inclusive) or instant (exclusive); None when not given.
        zone: Where dates and offset-less datetimes are read.
        now: The current instant.
        default_days: The window looked back when a bound is missing — the end
            defaults to ``now`` and the start to that many days before the end.
            None leaves a missing bound open.

    Returns:
        ``(since, until)``, either possibly None when ``default_days`` is None.

    Raises:
        UnreadableDateError: A bound that is not ISO 8601.
        InvertedPeriodError: A period that ends before it starts.
    """
    until = (
        _end_of(read_moment(end, zone), zone)
        if end is not None and end.strip()
        else (now if default_days is not None else None)
    )
    since = (
        _start_of(read_moment(start, zone), zone)
        if start is not None and start.strip()
        else (until - timedelta(days=default_days) if until and default_days is not None else None)
    )
    if since is not None and until is not None and since >= until:
        raise InvertedPeriodError(f"the period ends ({until.isoformat()}) before it starts")
    return since, until
