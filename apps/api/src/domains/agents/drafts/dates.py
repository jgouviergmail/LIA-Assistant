"""How a draft card writes a moment: a datetime in the person's zone, a date as itself.

An all-day event (ADR-369) carries DATES. Formatted as an instant, « 2026-11-03 »
is midnight UTC, which is the previous evening in New York: the card would show
the wrong day. A date is not an instant — it is shown as written, never moved by
a timezone, and without a time of day.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

from src.core.time_utils import format_datetime_for_display
from src.domains.connectors.clients.normalizers.all_day import calendar_date, inclusive_last_day

#: A calendar day, as the calendar clients write an all-day bound.
_DATE_ONLY: Final = re.compile(r"\d{4}-\d{2}-\d{2}")


def draft_datetime_formatter(user_timezone: str, user_language: str) -> Callable[[str | None], str]:
    """The formatter a draft card renders its moments with.

    Args:
        user_timezone: The person's IANA timezone, for datetimes.
        user_language: The card's language.

    Returns:
        A function turning an ISO date or datetime into the card's text ("" for none).
    """

    def format_dt(value: str | None) -> str:
        if not value:
            return ""
        if _DATE_ONLY.fullmatch(value.strip()):
            return format_datetime_for_display(value, "UTC", user_language, include_time=False)
        return format_datetime_for_display(value, user_timezone, user_language, include_time=True)

    return format_dt


def shown_end(value: str) -> str:
    """The end a card shows: an all-day end is EXCLUSIVE, so its last day is shown.

    A date-only end only ever comes from an all-day event (the clients read and
    write its end the day after its last day); a datetime end is shown as is.
    """
    if not value or not _DATE_ONLY.fullmatch(value.strip()):
        return value
    return inclusive_last_day(calendar_date(value)).isoformat()


__all__ = ["draft_datetime_formatter", "shown_end"]
