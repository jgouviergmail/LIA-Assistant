"""A task's due date is a DAY, whatever the provider keeps (ADR-369).

Google Tasks keeps a date: the time part of its RFC 3339 ``due`` is discarded
(``2026-11-03T00:00:00.000Z`` is the 3rd, in every zone — converting it to a
zone west of Greenwich would show the 2nd). Microsoft To Do keeps the INSTANT
of local midnight, which Graph answers in UTC (midnight in Paris is 23:00 UTC
the day before, 22:00 in summer): the day is that instant read in the account's
zone, and a day is written as its midnight there, a DST night included.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from src.domains.connectors.models import ConnectorType

#: Providers whose due date is a date (the time part is the provider's noise).
_DATE_ONLY = frozenset({ConnectorType.GOOGLE_TASKS})


def due_for_provider(provider: ConnectorType, day: date, zone: ZoneInfo) -> str:
    """The value a provider's client is given for ``day``.

    Args:
        provider: The tasks provider.
        day: The day the task is due.
        zone: The account's zone.

    Returns:
        Google: the day at midnight UTC (RFC 3339); To Do: the UTC instant of
        the day's midnight in ``zone``, as Graph's ``dateTime`` (no offset —
        the client names the zone, UTC).
    """
    if provider in _DATE_ONLY:
        return f"{day.isoformat()}T00:00:00.000Z"
    midnight = datetime.combine(day, time(), tzinfo=zone).astimezone(UTC)
    return midnight.strftime("%Y-%m-%dT%H:%M:%S")


def due_from_provider(provider: ConnectorType, raw: str | None, zone: ZoneInfo) -> date | None:
    """The day a provider's ``due`` names, or None without a readable one.

    Args:
        provider: The tasks provider.
        raw: The ``due`` the client answered (RFC 3339).
        zone: The account's zone.

    Returns:
        The day, or None.
    """
    if not raw:
        return None
    try:
        if provider in _DATE_ONLY:
            return date.fromisoformat(raw[:10])
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(zone).date()
