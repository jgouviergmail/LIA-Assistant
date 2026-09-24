"""How the forecast tools read the ``date`` they are given (ADR-310).

The published contract is an ISO date or datetime: the manifest and the tools'
own schemas tell the model to resolve a relative expression itself, from the
current date it holds (``FORECAST_DATE_DESCRIPTION``). Two more shapes are READ
without being published, so the pipeline planner does not regress: the English
words it may emit after the semantic pivot (``today``, ``tomorrow``,
``in N days``, ``this week``) and absolute dates written in words in five
languages (« jeudi 9 avril 2026 »).

Anything else is REFUSED. Until 2026-09-23 it fell back to today in silence: a
ReAct loop that passed « demain » got today's forecast back as a success and
could only blame the service. The refusal carries the accepted format and the
person's current date, so the model can correct its own call.

Extracted from ``weather_tools.py`` (frozen by the file-size ratchet), which
imports it.
"""

from __future__ import annotations

import re
from datetime import UTC, date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.core.time_utils import now_in_timezone, parse_datetime
from src.domains.agents.tools.common import ToolErrorCode

__all__ = [
    "UnreadableDateError",
    "calculate_target_date",
    "parse_localized_date",
    "unreadable_date_result",
]

# Month name mappings for localized date parsing (FR, EN, DE, ES, IT)
_MONTH_NAMES: dict[str, int] = {
    # French
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
    # English
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    # German
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "marz": 3,
    "juni": 6,
    "juli": 7,
    "oktober": 10,
    "dezember": 12,
    # Spanish
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    # Italian
    "gennaio": 1,
    "febbraio": 2,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "settembre": 9,
    "ottobre": 10,
    "dicembre": 12,
}

# Pattern: optional day-of-week, then DD month YYYY (e.g., "jeudi 09 avril 2026", "9 avril 2026")
_LOCALIZED_DATE_PATTERN = re.compile(r"(?:\w+\s+)?(\d{1,2})\s+(\w+)\s+(\d{4})", re.IGNORECASE)
_IN_N_DAYS = re.compile(r"in\s+(\d+)\s+days?")


class UnreadableDateError(ValueError):
    """A ``date`` value the forecast tools cannot read.

    Attributes:
        reference: The value as the caller sent it.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"unreadable date reference: {reference!r}")
        self.reference = reference


def parse_localized_date(ref: str) -> date | None:
    """Parse a date written in words, like 'jeudi 09 avril 2026' or '9 April 2026'.

    Supports French, English, German, Spanish, and Italian month names, day first.

    Args:
        ref: Date string to parse.

    Returns:
        Parsed date or None if not recognized.
    """
    match = _LOCALIZED_DATE_PATTERN.match(ref.strip())
    if not match:
        return None

    day_str, month_str, year_str = match.groups()
    month = _MONTH_NAMES.get(month_str.lower())
    if month is None:
        return None

    try:
        return date(int(year_str), month, int(day_str))
    except ValueError:
        return None


def unreadable_date_result(reference: str, user_timezone: str) -> dict[str, Any]:
    """The failure a forecast tool returns for a date it cannot read.

    Technical English (ADR-256): the model corrects its own call from it, so it
    carries what the tool accepts and the person's current date — everything
    the fix needs.

    Args:
        reference: The unreadable value.
        user_timezone: The person's IANA timezone, which defines « today ».

    Returns:
        A tool result dict with ``success`` false and the INVALID_INPUT code.
    """
    today = now_in_timezone(user_timezone).date().isoformat()
    return {
        "success": False,
        "error": "invalid_date",
        "error_code": ToolErrorCode.INVALID_INPUT.value,
        "message": (
            f"date '{reference}' is not readable: pass an ISO date (YYYY-MM-DD) or an "
            f"ISO datetime, resolved from the current date; today is {today} "
            f"({user_timezone})."
        ),
    }


def calculate_target_date(
    date_ref: str | None,
    user_timezone: str,
) -> tuple[str, int, bool]:
    """Calculate the target date of a forecast request in the user's timezone.

    Args:
        date_ref: An ISO date or datetime (the published contract); an English
            relative word or a date written in words (read, never published);
            None or empty for today.
        user_timezone: User's IANA timezone (e.g., "Europe/Paris").

    Returns:
        Tuple of:
        - target_date: Date string in YYYY-MM-DD format
        - offset: Number of days from today (for API request sizing)
        - is_specific_date: True if a specific date was asked (not a range like "this week")

    Raises:
        UnreadableDateError: When ``date_ref`` is none of the above.
    """
    today_date = now_in_timezone(user_timezone).date()

    if not date_ref:
        return today_date.isoformat(), 0, False

    ref = date_ref.strip()
    ref_lower = ref.lower()

    # ISO date/datetime: "2026-01-22", "2026-01-22T14:00:00+01:00", "2026-01-22T14:00:00Z"
    parsed_dt = parse_datetime(ref)
    if parsed_dt is not None:
        try:
            parsed_local = parsed_dt.astimezone(ZoneInfo(user_timezone))
        except KeyError, ValueError:
            parsed_local = parsed_dt.astimezone(UTC)
        target_date = parsed_local.date()
        return target_date.isoformat(), max(0, (target_date - today_date).days), True

    # English words the pipeline planner may emit after the semantic pivot.
    if ref_lower in ("today", "now"):
        return today_date.isoformat(), 0, True
    if ref_lower == "tomorrow":
        return (today_date + timedelta(days=1)).isoformat(), 1, True
    if ref_lower in ("after tomorrow", "day after tomorrow"):
        return (today_date + timedelta(days=2)).isoformat(), 2, True
    days_match = _IN_N_DAYS.search(ref_lower)
    if days_match:
        days = int(days_match.group(1))
        return (today_date + timedelta(days=days)).isoformat(), days, True
    # Week references: today, NOT specific (show the full window)
    if "week" in ref_lower:
        return today_date.isoformat(), 0, False

    # Dates written in words: "jeudi 09 avril 2026", "9 avril 2026", "9 April 2026".
    parsed_localized = parse_localized_date(ref)
    if parsed_localized is not None:
        return parsed_localized.isoformat(), max(0, (parsed_localized - today_date).days), True

    # A value nobody can read is refused, never guessed as today (ADR-310).
    raise UnreadableDateError(ref)
