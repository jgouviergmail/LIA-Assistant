"""Generic recurrence: a stored specification, and the instants it fires at.

The single import surface for every consumer. Nothing in this package imports
``src.domains`` — the caps a consumer enforces are injected
(:class:`RecurrenceLimits`), so one engine serves a routine capped at 12 runs a
day and a reminder capped at 48.
"""

from src.core.recurrence.dictation import (
    CLOCK_PATTERN,
    DATE_PATTERN,
    NTH_WEEKDAY_PATTERN,
    REPEAT_VALUES,
    recurrence_from_parameters,
)
from src.core.recurrence.display import describe
from src.core.recurrence.engine import (
    next_occurrence,
    occurrences,
    series,
    slots_between,
)
from src.core.recurrence.schedule import (
    day_slots,
    rearm_after,
    served_slot,
    week_slots,
    week_start,
)
from src.core.recurrence.spec import (
    MAX_DAY_IN_MONTH,
    DailyTimes,
    RecurrenceError,
    RecurrenceFreq,
    RecurrenceLimits,
    RecurrenceSpec,
    SeriesEnd,
    TimeOfDay,
)

__all__ = [
    "CLOCK_PATTERN",
    "DATE_PATTERN",
    "MAX_DAY_IN_MONTH",
    "NTH_WEEKDAY_PATTERN",
    "REPEAT_VALUES",
    "DailyTimes",
    "RecurrenceError",
    "RecurrenceFreq",
    "RecurrenceLimits",
    "RecurrenceSpec",
    "SeriesEnd",
    "TimeOfDay",
    "day_slots",
    "describe",
    "next_occurrence",
    "occurrences",
    "recurrence_from_parameters",
    "rearm_after",
    "series",
    "served_slot",
    "slots_between",
    "week_slots",
    "week_start",
]
