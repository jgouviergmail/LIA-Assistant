"""A rule a tool call dictates, read at the tool (ADR-369, lot 10, D2).

A rule is dictated in the words every recurrence of LIA is (``registry/recurrence_parameters``,
``core/recurrence/dictation``) and anchored on the event's own first day; a rule that day does
not belong to is refused with the reason, so the model corrects its own call. Beside the
calendar tools because the refusal is theirs to hand back: ``calendar/event_series`` holds what
the manifests read, and the catalogue must load without the tool layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Final

from src.core.recurrence import (
    RecurrenceError,
    describe_calendar,
    recurrence_from_parameters,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.mailbox_draft_base import refusal
from src.domains.connectors.clients.event_recurrence import (
    EventStartOutsideSeriesError,
    RecurrenceNotHeldError,
    anchored_spec,
)

#: A time the rule never reads: the event has its own.
_ANY_TIME: Final = ["12:00"]


def _first_day(start: str) -> date:
    return datetime.fromisoformat(start).date() if "T" in start else date.fromisoformat(start)


def _days_said(source: Mapping[str, Any], day: date) -> dict[str, Any]:
    """The days of a rule: what was said, else the event's own, as « every week » means."""
    repeat = source.get("repeat")
    weekdays, month_days = source.get("weekdays"), source.get("month_days")
    months, nth = source.get("months"), source.get("nth_weekday")
    if repeat == "weekly" and not weekdays:
        weekdays = [day.isoweekday()]
    if repeat == "monthly" and not month_days and not nth:
        month_days = [day.day]
    if repeat == "yearly" and not months:
        months, month_days = [day.month], month_days or [day.day]
    return {"weekdays": weekdays, "month_days": month_days, "months": months, "nth_weekday": nth}


def read_recurrence(
    source: Mapping[str, Any], start: str, zone: str, language: str
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    """A rule a tool call dictates, anchored on its event.

    Args:
        source: The tool's arguments.
        start: The event's start, as the draft holds it.
        zone: The event's zone.
        language: The person's, for the card.

    Returns:
        The rule as plain data, its sentence, and the refusal to hand back; all None when the
        call dictates no series.
    """
    repeat = source.get("repeat")
    if not repeat or repeat == "once":
        return None, None, None
    day = _first_day(start)
    try:
        spec = recurrence_from_parameters(
            repeat=repeat,
            today=day,
            times=_ANY_TIME,
            repeat_every=source.get("repeat_every") or 1,
            **_days_said(source, day),
            until_date=source.get("until_date"),
            max_occurrences=source.get("max_occurrences"),
            starting_on=day.isoformat(),
        )
        anchored = anchored_spec(spec, day, zone)
    except EventStartOutsideSeriesError:
        return (
            None,
            None,
            refusal(
                ToolErrorCode.INVALID_INPUT,
                "the event's first day is not one the rule serves: move the start or the days.",
            ),
        )
    except (RecurrenceError, RecurrenceNotHeldError) as error:
        return None, None, refusal(ToolErrorCode.INVALID_INPUT, str(error))
    return anchored.model_dump(mode="json"), describe_calendar(anchored, language), None


__all__ = ["read_recurrence"]
