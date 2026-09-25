"""The two parameters every lookup tool reads the same way (ADR-318).

A result ceiling and a period, read here for the memory, journal, activity and
generated-files lookups alike: a parameter spelled in each tool is a parameter
that comes to be read in several ways.

- :func:`bounded_count` — ``max_results`` clamped into ``[1, ceiling]``, the
  ceiling when omitted: an out-of-bounds number is REPAIRED, never refused,
  because the ceiling is published and what is mechanically repairable is
  repaired (ADR-184).
- :func:`read_period` — two optional ISO values read by the date contract
  (``core/date_contract``); an unreadable value is refused with the ADR-310
  wording, an inverted period with its own, both typed.
"""

from __future__ import annotations

from datetime import datetime, tzinfo

from src.core.date_contract import (
    InvertedPeriodError,
    UnreadableDateError,
    period_bounds,
    unreadable_date_message,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput

__all__ = ["bounded_count", "read_period"]


def bounded_count(requested: int | None, ceiling: int) -> int:
    """How many results a lookup returns.

    Args:
        requested: What the model asked for, or None.
        ceiling: The published maximum.

    Returns:
        ``requested`` clamped into ``[1, ceiling]``; the ceiling when omitted.
    """
    return ceiling if requested is None else max(1, min(int(requested), ceiling))


def read_period(
    start: str | None,
    end: str | None,
    zone: tzinfo,
    *,
    now: datetime,
    default_days: int | None,
) -> tuple[datetime | None, datetime | None] | UnifiedToolOutput:
    """A period from two optional ISO values, or the typed refusal to return.

    Args:
        start: First day or instant, inclusive.
        end: Last day (inclusive) or instant (exclusive).
        zone: The person's timezone, where days are read.
        now: The current instant.
        default_days: The window a missing bound defaults to, or None to leave
            it open.

    Returns:
        ``(since, until)``, or the refusal the tool returns as is.
    """
    try:
        return period_bounds(start, end, zone, now=now, default_days=default_days)
    except UnreadableDateError as error:
        return UnifiedToolOutput.failure(
            message=unreadable_date_message(error.reference, str(zone)),
            error_code=ToolErrorCode.INVALID_INPUT.value,
        )
    except InvertedPeriodError:
        return UnifiedToolOutput.failure(
            message="The period ends before it starts: pass start_date before end_date.",
            error_code=ToolErrorCode.INVALID_PARAM_VALUE.value,
        )
