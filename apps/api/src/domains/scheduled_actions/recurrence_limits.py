"""What a routine's schedule may ask — the operator's settings, read in ONE place.

A routine runs the full agent pipeline on every occurrence, so the shortest step
and the most runs a day are the OPERATOR's decision
(``SCHEDULED_ACTIONS_MIN_STEP_MINUTES``, ``SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY``,
ADR-268 amendment 2026-10-30). Every door that validates or publishes a routine's
schedule reads them here: the creation rule (``service.validate_routine_creation``),
the update schema, the chat tool and its manifest, and the list the form reads.
Before, two constants and a copy of them typed into the form said the same thing in
two places — and only a code change could move them.
"""

from __future__ import annotations

from src.core.config import settings
from src.core.constants import RECURRENCE_ROUTINE_MAX_SERIES_COUNT
from src.core.recurrence import RecurrenceLimits


def routine_recurrence_limits() -> RecurrenceLimits:
    """A routine's limits as the settings define them now.

    Returns:
        The caps every routine door enforces, and the list publishes.
    """
    return RecurrenceLimits(
        max_times_per_day=settings.scheduled_actions_max_times_per_day,
        min_step_minutes=settings.scheduled_actions_min_step_minutes,
        max_series_count=RECURRENCE_ROUTINE_MAX_SERIES_COUNT,
    )
