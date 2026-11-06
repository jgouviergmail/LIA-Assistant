"""What an event says beyond its time, on every calendar (ADR-369, lot 5).

A reminder, whether its time shows as busy, whether it is private. Google's words are
the vocabulary the normalisers speak (``transparency``, ``visibility``), and each other
provider is translated to them. An option left out is kept: a provider's own default is
nobody's to overwrite by accident. A reminder is ONE alarm before the event: a provider
that keeps several is read by its earliest and written with one. A recurrence rides here
too (lot 10): it says when the event happens again, in each provider's words.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

from src.core.recurrence import RecurrenceSpec
from src.domains.connectors.clients.event_recurrence import graph_recurrence, rrule_of

#: « No reminder », as a request says it: None keeps what the event has.
NO_REMINDER: Final = -1
_ALARM_TEXT: Final = "Reminder"


@dataclass(frozen=True, slots=True)
class EventOptions:
    """What an event is asked to say; None keeps what it has.

    Attributes:
        reminder_minutes: Minutes before it starts, or ``NO_REMINDER``.
        busy: Whether its time shows as taken.
        private: Whether its details are kept from those who see the calendar.
        recurrence: When it happens again.
        zone: The zone a recurrence is read in.
        all_day: The event is all-day: a recurrence's end is a day.
    """

    reminder_minutes: int | None = None
    busy: bool | None = None
    private: bool | None = None
    recurrence: RecurrenceSpec | None = None
    zone: str = "UTC"
    all_day: bool = False


def google_options(options: EventOptions) -> dict[str, Any]:
    """The fields of a Google event the options write."""
    body: dict[str, Any] = {}
    if options.reminder_minutes is not None:
        overrides = (
            []
            if options.reminder_minutes == NO_REMINDER
            else [{"method": "popup", "minutes": options.reminder_minutes}]
        )
        body["reminders"] = {"useDefault": False, "overrides": overrides}
    if options.busy is not None:
        body["transparency"] = "opaque" if options.busy else "transparent"
    if options.private is not None:
        body["visibility"] = "private" if options.private else "default"
    if options.recurrence is not None:
        body["recurrence"] = [
            rrule_of(options.recurrence, zone=options.zone, all_day=options.all_day)
        ]
    return body


def graph_options(options: EventOptions) -> dict[str, Any]:
    """The fields of a Graph event the options write."""
    body: dict[str, Any] = {}
    if options.reminder_minutes == NO_REMINDER:
        body["isReminderOn"] = False
    elif options.reminder_minutes is not None:
        body["isReminderOn"] = True
        body["reminderMinutesBeforeStart"] = options.reminder_minutes
    if options.busy is not None:
        body["showAs"] = "busy" if options.busy else "free"
    if options.private is not None:
        body["sensitivity"] = "private" if options.private else "normal"
    if options.recurrence is not None:
        body["recurrence"] = graph_recurrence(options.recurrence, zone=options.zone)
    return body


def apply_ical_options(vevent: Any, options: EventOptions) -> None:
    """Writes the options on a ``VEVENT``.

    Args:
        vevent: The event, as ``vobject`` holds it.
        options: What it is asked to say.
    """
    if options.reminder_minutes is not None:
        _write_alarm(vevent, options.reminder_minutes)
    if options.busy is not None:
        _replace(vevent, "transp", "OPAQUE" if options.busy else "TRANSPARENT")
    if options.private is not None:
        _replace(vevent, "class", "PRIVATE" if options.private else "PUBLIC")
    if options.recurrence is not None:
        rule = rrule_of(options.recurrence, zone=options.zone, all_day=options.all_day)
        _replace(vevent, "rrule", rule.removeprefix("RRULE:"))


def ical_options(vevent: Any) -> dict[str, Any]:
    """What a ``VEVENT`` says, in the normalisers' vocabulary; only what it does say."""
    read: dict[str, Any] = {}
    minutes = [_minutes_before(alarm) for alarm in getattr(vevent, "valarm_list", None) or ()]
    known = [value for value in minutes if value is not None]
    if known:
        read["reminderMinutes"] = max(known)
    transp = _text_of(vevent, "transp")
    if transp is not None:
        read["transparency"] = "transparent" if transp == "TRANSPARENT" else "opaque"
    visibility = _text_of(vevent, "class")
    if visibility is not None:
        read["visibility"] = "private" if visibility == "PRIVATE" else "default"
    return read


def _text_of(vevent: Any, name: str) -> str | None:
    """A property's text, whatever its case; None when the event does not say."""
    value = getattr(getattr(vevent, name, None), "value", None)
    return value.upper() if isinstance(value, str) else None


def _write_alarm(vevent: Any, minutes: int) -> None:
    """One alarm before the event, or none."""
    while hasattr(vevent, "valarm"):
        vevent.remove(vevent.valarm)
    if minutes == NO_REMINDER:
        return
    alarm = vevent.add("valarm")
    alarm.add("action").value = "DISPLAY"
    alarm.add("description").value = _ALARM_TEXT
    alarm.add("trigger").value = timedelta(minutes=-minutes)


def _minutes_before(alarm: Any) -> int | None:
    """How long before the event an alarm rings; None for one set at an instant."""
    trigger = getattr(getattr(alarm, "trigger", None), "value", None)
    if not isinstance(trigger, timedelta):
        return None
    return max(0, int(-trigger.total_seconds() // 60))


def _replace(vevent: Any, name: str, value: str) -> None:
    while hasattr(vevent, name):
        vevent.remove(getattr(vevent, name))
    vevent.add(name).value = value


__all__ = [
    "NO_REMINDER",
    "EventOptions",
    "apply_ical_options",
    "google_options",
    "graph_options",
    "ical_options",
]
