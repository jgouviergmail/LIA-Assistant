"""A routine's schedule caps in tests: the defaults, and the operator's settings pinned.

The two caps are the OPERATOR's (``SCHEDULED_ACTIONS_MIN_STEP_MINUTES``,
``SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY``), and on a developer's machine the task
runner injects the root ``.env`` into the test process — so a test asserting
what a routine may NOT ask must state the caps it asserts against, or it reads
whatever that developer chose for their own instance.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.core.constants import (
    RECURRENCE_ROUTINE_MAX_SERIES_COUNT,
    SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_DEFAULT,
    SCHEDULED_ACTIONS_MIN_STEP_MINUTES_DEFAULT,
)
from src.core.recurrence import RecurrenceLimits

#: What a routine may ask when the operator set nothing.
DEFAULT_ROUTINE_LIMITS = RecurrenceLimits(
    max_times_per_day=SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_DEFAULT,
    min_step_minutes=SCHEDULED_ACTIONS_MIN_STEP_MINUTES_DEFAULT,
    max_series_count=RECURRENCE_ROUTINE_MAX_SERIES_COUNT,
)


def pin_routine_caps(
    monkeypatch: pytest.MonkeyPatch,
    *,
    min_step_minutes: int = SCHEDULED_ACTIONS_MIN_STEP_MINUTES_DEFAULT,
    max_times_per_day: int = SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_DEFAULT,
) -> None:
    """Set the operator's routine caps for one test, whatever the ``.env`` says.

    Args:
        monkeypatch: The test's monkeypatch, which restores both on teardown.
        min_step_minutes: Smallest step of a schedule at a regular interval.
        max_times_per_day: Most moments one day of a schedule may carry.
    """
    monkeypatch.setattr(settings, "scheduled_actions_min_step_minutes", min_step_minutes)
    monkeypatch.setattr(settings, "scheduled_actions_max_times_per_day", max_times_per_day)
