"""A task's due date is a DAY, whatever the provider keeps (ADR-369).

Google Tasks keeps a date: the time part of its RFC 3339 ``due`` is discarded
(``2026-11-03T00:00:00.000Z`` is the 3rd, in every zone — converting it to a
zone west of Greenwich would show the 2nd). Microsoft To Do keeps the instant
of midnight in the zone it is GIVEN, and answers it in UTC: measured on Graph
(2026-11-07), given UTC it keeps the UTC date, which made a day written as its
UTC instant the day before east of Greenwich. So a day is written as its
midnight on the account's wall, the zone named, and read back as its instant
in that zone — both through ``core/task_due``, the door every reader of a
task's day shares (the home's card, the heartbeat, the radio, the assistant).
"""

from __future__ import annotations

from datetime import date
from typing import NamedTuple
from zoneinfo import ZoneInfo

from src.core.task_due import due_day, todo_due
from src.domains.connectors.models import ConnectorType

#: Providers whose due date is a date (the time part is the provider's noise).
_DATE_ONLY = frozenset({ConnectorType.GOOGLE_TASKS})


class ProviderDue(NamedTuple):
    """What a client is given for a day: the value, and the zone it is a wall time in."""

    value: str
    zone: str | None


def due_for_provider(provider: ConnectorType, day: date, zone: ZoneInfo) -> ProviderDue:
    """What a provider's client is given for ``day``.

    Args:
        provider: The tasks provider.
        day: The day the task is due.
        zone: The account's zone.

    Returns:
        Google: the day at midnight UTC (RFC 3339), no zone; To Do: the day's
        midnight on the account's wall, and that zone's name.
    """
    if provider in _DATE_ONLY:
        return ProviderDue(f"{day.isoformat()}T00:00:00.000Z", None)
    wall, name = todo_due(day, zone)
    return ProviderDue(wall, name)


def due_from_provider(provider: ConnectorType, raw: str | None, zone: ZoneInfo) -> date | None:
    """The day a provider's ``due`` names, or None without a readable one.

    Args:
        provider: The tasks provider.
        raw: The ``due`` the client answered (RFC 3339).
        zone: The account's zone.

    Returns:
        The day, or None.
    """
    return due_day(raw, todo=provider not in _DATE_ONLY, zone=zone)
