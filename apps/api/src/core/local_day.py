"""A person's calendar day, as instants (ADR-148 amendment 2026-11-14).

A local day is not 24 hours: 29 March lasts 23 in Paris, 25 October 25. Both
bounds of a day window are therefore built from the CALENDAR, never by adding
a day to an instant (measured: doing so counted 48 routine slots where 46
exist). One door for every reader that cuts time at the person's midnight —
the routine schedule, the health readers.

Standard library only: ``core/recurrence`` reads it and must load with no
configuration at all (``test_no_domain_import``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

__all__ = ["local_day_bounds", "local_midnight", "local_today"]


def local_midnight(day: date, zone: ZoneInfo) -> datetime:
    """The instant local midnight of ``day`` happens at.

    Where a zone's clocks skip or repeat midnight, the earlier reading is
    taken (``fold=0``), the one a calendar shows.

    Args:
        day: The local calendar day.
        zone: The zone.

    Returns:
        The UTC instant of that local midnight.
    """
    return datetime.combine(day, datetime.min.time(), tzinfo=zone).replace(fold=0).astimezone(UTC)


def local_today(now: datetime, zone: ZoneInfo) -> date:
    """The calendar day ``now`` falls on where the person lives.

    Args:
        now: An aware instant.
        zone: The person's zone.

    Returns:
        The local calendar date.
    """
    return now.astimezone(zone).date()


def local_day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """The half-open instant window ``[start, end)`` of one local day.

    Args:
        day: The local calendar day.
        zone: The zone.

    Returns:
        The UTC instants of that day's midnight and of the next one.
    """
    return local_midnight(day, zone), local_midnight(day + timedelta(days=1), zone)
