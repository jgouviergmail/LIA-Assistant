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
person's current date, so the model can correct its own call — the wording and
the exception live in ``core/date_contract`` since ADR-318, shared with every
tool that takes a date.

Extracted from ``weather_tools.py`` (frozen by the file-size ratchet), which
imports it.
"""

from __future__ import annotations

import re
from datetime import UTC, date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.core.date_contract import UnreadableDateError, unreadable_date_message
from src.core.date_quotes import parse_localized_date
from src.core.time_utils import now_in_timezone, parse_datetime
from src.domains.agents.tools.common import ToolErrorCode

_IN_N_DAYS = re.compile(r"in\s+(\d+)\s+days?")

__all__ = [
    "calculate_target_date",
    "parse_localized_date",
    "unreadable_date_result",
]


def _civil_date_reference(reference: str) -> date | None:
    """An ISO calendar date has no timezone and must not shift to another day."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reference):
        return None
    try:
        return date.fromisoformat(reference)
    except ValueError:
        return None


def _instant_date_reference(reference: str, user_timezone: str) -> date | None:
    """An offset datetime chooses its day after conversion to the user's zone."""
    parsed = parse_datetime(reference)
    if parsed is None:
        return None
    try:
        localized = parsed.astimezone(ZoneInfo(user_timezone))
    except KeyError, ValueError:
        localized = parsed.astimezone(UTC)
    return localized.date()


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
    return {
        "success": False,
        "error": "invalid_date",
        "error_code": ToolErrorCode.INVALID_INPUT.value,
        "message": unreadable_date_message(reference, user_timezone),
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
    target_date = _civil_date_reference(ref) or _instant_date_reference(ref, user_timezone)
    if target_date is not None:
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


def forecast_window_days(requested: int | None, *, is_specific_date: bool, max_days: int) -> int:
    """How many consecutive days a daily forecast returns, from its target date.

    An omitted count is the target day alone when a specific date was asked,
    and the whole published window otherwise. An explicit count is honoured —
    it used to be replaced by 1 whenever it equalled the default, so "the next
    five days" from today came back as one day (2026-10-11) — and bounded to
    ``[1, max_days]``: the ReAct loop reaches the tool without the planner's
    clamp, and a bound is repaired, never rejected (ADR-184).

    Args:
        requested: The caller's ``days``, or None when omitted.
        is_specific_date: Whether a specific target date was asked.
        max_days: The published window (``WEATHER_FORECAST_MAX_DAYS``).

    Returns:
        The number of days to return.
    """
    if requested is None:
        return 1 if is_specific_date else max_days
    return max(1, min(requested, max_days))
