"""A repeating event from the screen (ADR-369, lot 10).

The rule of a series and what reaches it are the client's (``clients/event_recurrence``): the screen
and the assistant read one. Here a rule nobody can make a series of is told as a refusal.
"""

from __future__ import annotations

from datetime import date

from src.core.recurrence import RecurrenceError, RecurrenceSpec
from src.domains.connectors.clients.event_recurrence import (
    EventStartOutsideSeriesError,
    RecurrenceNotHeldError,
    anchored_spec,
)
from src.domains.workbench.errors import EVENT_START_OUTSIDE_SERIES, INVALID_REQUEST, refuse


def spec_from(spec: RecurrenceSpec, start_day: date, zone: str) -> RecurrenceSpec:
    """A rule as the event's own, or its refusal.

    Args:
        spec: The rule as the page sent it.
        start_day: The event's first day.
        zone: The zone it is read in.

    Returns:
        The rule, anchored.

    Raises:
        BaseAPIException: ``invalid_request`` for a rule no series can be made of;
            ``event_start_outside_series`` for a first day the rule does not serve.
    """
    try:
        return anchored_spec(spec, start_day, zone)
    except EventStartOutsideSeriesError:
        refuse(EVENT_START_OUTSIDE_SERIES)
    except RecurrenceError, RecurrenceNotHeldError:
        refuse(INVALID_REQUEST)


__all__ = ["spec_from"]
