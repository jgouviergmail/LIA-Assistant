"""What the assistant says of an event beyond its time (ADR-369, lot 5, D2).

Beside the calendar manifests, not among the tools, as ``event_times``: the manifest reads
its wording here. These are what the « Tools » form says of an event, a reminder, free or
busy, private, and the call added to an event that exists.

Each parameter's wording is ONE constant read by the planner's manifest and the tool's own
schema: the ReAct loop binds the schema and never sees the manifest (ADR-310).

``readable_options`` is the one reading of what a model wrote, whichever the door: a tool's
arguments or a card changed in words (``hitl/draft_modifier``). What it cannot read is
dropped, and an option nobody said keeps what the event has: nothing lands on an event
that the person did not ask for.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from src.core.constants import WORKBENCH_EVENT_REMINDER_MAX_MINUTES
from src.domains.agents.calendar.event_series import spec_of
from src.domains.agents.registry.catalogue import ParameterConstraint, ParameterSchema
from src.domains.connectors.clients.calendar_options import NO_REMINDER, EventOptions

REMINDER_MINUTES_DESCRIPTION: Final = (
    "The event's reminder, in minutes before it starts: 0 when it starts, "
    f"{NO_REMINDER} for no reminder at all. Omit it to keep the calendar's own."
)
BUSY_DESCRIPTION: Final = "False shows the time as free, true as busy. Omit it to keep it."
PRIVATE_DESCRIPTION: Final = (
    "True keeps the event's details from those who see the calendar, false makes it ordinary "
    "again. Omit it to keep it."
)
ADD_CONFERENCE_UPDATE_DESCRIPTION: Final = (
    "True adds a video-call link (Meet or Teams by provider) to an event that has none. "
    "Unsupported on Apple calendars (the event is changed without a link)."
)

#: The fields an option lands on, in every draft that holds them.
EVENT_OPTION_FIELDS: Final = ("reminder_minutes", "busy", "private")
_SWITCHES: Final = ("busy", "private")
_WRITTEN_SWITCHES: Final[dict[str, bool]] = {"true": True, "false": False}

#: The options as the planner reads them, for the two tools that write an event.
EVENT_OPTION_PARAMETERS: Final = (
    ParameterSchema(
        name="reminder_minutes",
        type="integer",
        required=False,
        description=REMINDER_MINUTES_DESCRIPTION,
        constraints=[
            ParameterConstraint(kind="minimum", value=NO_REMINDER),
            ParameterConstraint(kind="maximum", value=WORKBENCH_EVENT_REMINDER_MAX_MINUTES),
        ],
    ),
    ParameterSchema(name="busy", type="boolean", required=False, description=BUSY_DESCRIPTION),
    ParameterSchema(
        name="private", type="boolean", required=False, description=PRIVATE_DESCRIPTION
    ),
)


def readable_options(source: Mapping[str, Any]) -> dict[str, Any]:
    """The options a source says, each one read.

    Args:
        source: A tool's arguments or a draft's content.

    Returns:
        Only what is said and readable; a reminder repaired within its bounds (ADR-184).
    """
    read: dict[str, Any] = {}
    minutes = _minutes(source.get("reminder_minutes"))
    if minutes is not None:
        read["reminder_minutes"] = minutes
    for name in _SWITCHES:
        switch = _switch(source.get(name))
        if switch is not None:
            read[name] = switch
    return read


def readable_changes(modified: Mapping[str, Any]) -> dict[str, Any]:
    """What a card changed in words may hold: the options read, the rest as it came."""
    kept = {
        key: value
        for key, value in modified.items()
        if key not in EVENT_OPTION_FIELDS and key != "add_conference"
    }
    call = _switch(modified.get("add_conference"))
    if call is not None:
        kept["add_conference"] = call
    return {**kept, **readable_options(modified)}


def event_options(draft: Mapping[str, Any]) -> EventOptions | None:
    """What a draft asks of the client; None when it says nothing."""
    read = readable_options(draft)
    recurrence = spec_of(draft)
    if not read and recurrence is None:
        return None
    return EventOptions(
        **read,
        recurrence=recurrence,
        zone=str(draft.get("timezone") or "UTC"),
        all_day=bool(draft.get("all_day")),
    )


def _minutes(value: object) -> int | None:
    """A number of minutes within its bounds; what nobody can read is no reminder asked."""
    if isinstance(value, str) and value.strip().removeprefix("-").isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(NO_REMINDER, min(value, WORKBENCH_EVENT_REMINDER_MAX_MINUTES))


def _switch(value: object) -> bool | None:
    """A boolean, or the word for one: a model told to write a field may quote it."""
    if isinstance(value, bool):
        return value
    return _WRITTEN_SWITCHES.get(value.strip().lower()) if isinstance(value, str) else None


__all__ = [
    "ADD_CONFERENCE_UPDATE_DESCRIPTION",
    "BUSY_DESCRIPTION",
    "EVENT_OPTION_FIELDS",
    "EVENT_OPTION_PARAMETERS",
    "NO_REMINDER",
    "PRIVATE_DESCRIPTION",
    "REMINDER_MINUTES_DESCRIPTION",
    "event_options",
    "readable_changes",
    "readable_options",
]
