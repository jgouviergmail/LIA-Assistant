"""What the calendar routes take and answer (ADR-369).

On the wire an all-day event's bounds are DAYS, the end exclusive (the
providers' own convention), and a timed event's are INSTANTS in UTC
(``calendar_times``). What the page sends is a WALL time and the zone it is
read in, never an offset (spec §14). A window is the account's days, its last
one included, each calendar answered on its own — its events, whether they were
cut at the published bound, how many could not be read, or the refusal that
kept it unread — so one calendar that fails never empties the others (ADR-185).
An event of a series is an OCCURRENCE: changing or deleting it reaches that
occurrence alone, unless the person asks for the whole series (``scope``). A rule is
the one every recurrence of LIA is (``core/recurrence``).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from src.core.constants import (
    WORKBENCH_CALENDAR_IDS_MAX,
    WORKBENCH_CALENDAR_NAME_MAX_CHARS,
    WORKBENCH_CALENDAR_WINDOW_MAX_DAYS,
    WORKBENCH_EVENT_ATTENDEES_MAX,
    WORKBENCH_EVENT_DESCRIPTION_MAX_CHARS,
    WORKBENCH_EVENT_LOCATION_MAX_CHARS,
    WORKBENCH_EVENT_REMINDER_MAX_MINUTES,
    WORKBENCH_EVENT_SUMMARY_MAX_CHARS,
    WORKBENCH_MAIL_QUERY_MAX_CHARS,
)
from src.core.recurrence import RecurrenceSpec
from src.domains.connectors.clients.calendar_answers import EventAnswer
from src.domains.connectors.clients.calendar_options import NO_REMINDER
from src.domains.shared.schemas import TimezoneValidatorMixin
from src.domains.workbench.calendar_times import ends_after
from src.domains.workbench.ids import ProviderId

_SUMMARY = StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=WORKBENCH_EVENT_SUMMARY_MAX_CHARS,
    pattern=r"^[^\x00-\x1f\x7f]+$",
)
Summary = Annotated[str, _SUMMARY]
# The optional ones carry the constraint on ``str | None`` (``test_annotated_metadata_guard``).
OptionalSummary = Annotated[str | None, _SUMMARY]
OptionalLocation = Annotated[
    str | None,
    StringConstraints(
        max_length=WORKBENCH_EVENT_LOCATION_MAX_CHARS, pattern=r"^[^\x00-\x1f\x7f]*$"
    ),
]
OptionalDescription = Annotated[
    str | None, StringConstraints(max_length=WORKBENCH_EVENT_DESCRIPTION_MAX_CHARS)
]
_SearchWords = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=WORKBENCH_MAIL_QUERY_MAX_CHARS,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]
#: One bound as the page sends it: a day (all-day) or a wall time ``YYYY-MM-DDTHH:MM``.
_BOUND = StringConstraints(min_length=10, max_length=19)
Bound = Annotated[str, _BOUND]
OptionalBound = Annotated[str | None, _BOUND]
_Attendees = Annotated[list[EmailStr], Field(max_length=WORKBENCH_EVENT_ATTENDEES_MAX)]
OptionalAttendees = Annotated[
    list[EmailStr] | None, Field(max_length=WORKBENCH_EVENT_ATTENDEES_MAX)
]
Response = Literal["accepted", "declined", "tentative", "needsAction"]
CalendarName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=WORKBENCH_CALENDAR_NAME_MAX_CHARS
    ),
]


class CalendarInfo(BaseModel):
    """One calendar of the account."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The provider's id of the calendar.")
    name: str = Field(description="Its name.")
    color: str | None = Field(description="Its colour as the provider keeps it (#rrggbb).")
    primary: bool = Field(description="Whether it is the account's own calendar.")
    default: bool = Field(description="Whether it is the default chosen in the settings.")
    writable: bool = Field(description="Whether events can be created and changed in it.")
    manageable: bool = Field(description="Whether the person may rename and delete it.")


class CalendarList(BaseModel):
    """The account's calendars."""

    calendars: list[CalendarInfo] = Field(description="Its calendars, as the provider lists them.")


class DayWindow(BaseModel):
    """The days a view shows."""

    model_config = ConfigDict(extra="forbid")

    start: date = Field(description="The first day shown, in the account's calendar.")
    end: date = Field(description="The LAST day shown (included).")

    @model_validator(mode="after")
    def _a_bounded_window(self) -> Self:
        days = (self.end - self.start).days + 1
        if days < 1 or days > WORKBENCH_CALENDAR_WINDOW_MAX_DAYS:
            raise ValueError(f"a window is 1 to {WORKBENCH_CALENDAR_WINDOW_MAX_DAYS} days")
        return self


class EventWindowQuery(DayWindow):
    """The calendars and the days a view shows."""

    calendar_ids: list[ProviderId] = Field(
        min_length=1, max_length=WORKBENCH_CALENDAR_IDS_MAX, description="The calendars shown."
    )


class Attendee(BaseModel):
    """Someone invited, and what they answered."""

    model_config = ConfigDict(frozen=True)

    email: str = Field(description="Their address.")
    name: str | None = Field(description="Their name, when the provider gives one.")
    response: Response = Field(description="What they answered.")


class CalendarEvent(BaseModel):
    """One event as a view draws it."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The event's id — an OCCURRENCE's own id within a series.")
    calendar_id: str = Field(description="Its calendar.")
    summary: str = Field(description="Its title (may be empty at the provider).")
    all_day: bool = Field(description="Whether its bounds are days.")
    start: str = Field(description="A day (all-day) or an instant in UTC (RFC 3339).")
    end: str = Field(description="A day, EXCLUSIVE (all-day), or an instant in UTC.")
    location: str | None = Field(description="Where it takes place.")
    recurring: bool = Field(description="Whether it is an occurrence of a series.")
    conference_url: str | None = Field(description="Its video call's link (Meet, Teams).")


class EventDetail(CalendarEvent):
    """One event, whole."""

    description: str | None = Field(description="Its notes, as the provider keeps them.")
    attendees: list[Attendee] = Field(description="Who is invited, and what they answered.")
    organizer: str | None = Field(description="Who organises it (an address).")
    link: str | None = Field(description="The event at its provider, when it has a page.")
    reminder_minutes: int | None = Field(
        description="Its own reminder, in minutes before; None when it has none of its own."
    )
    busy: bool = Field(description="Whether its time shows as taken.")
    private: bool = Field(description="Whether its details stay private.")
    zone: str | None = Field(
        description="The zone it was set in (IANA); None when the provider says none, or UTC."
    )
    my_response: Response | None = Field(
        description="What the person answered; None for an event with nothing for them to answer."
    )


class EventInvitationAnswer(BaseModel):
    """The person's answer to an invitation."""

    model_config = ConfigDict(extra="forbid")

    calendar_id: ProviderId = Field(description="The event's calendar.")
    event_id: ProviderId = Field(description="The event, an occurrence's own id within a series.")
    response: EventAnswer = Field(description="The answer: the organiser is told.")


class EventMove(BaseModel):
    """An event going to another calendar."""

    model_config = ConfigDict(extra="forbid")

    calendar_id: ProviderId = Field(description="The calendar it is in.")
    event_id: ProviderId = Field(description="The event.")
    destination_id: ProviderId = Field(description="The calendar it goes to.")

    @model_validator(mode="after")
    def _goes_somewhere_else(self) -> Self:
        if self.destination_id == self.calendar_id:
            raise ValueError("an event moves to another calendar")
        return self


class NewCalendar(BaseModel):
    """A calendar to create, once per submission."""

    model_config = ConfigDict(extra="forbid")

    name: CalendarName = Field(description="Its name.")
    idempotency_key: UUID = Field(description="One key per submission (a replay creates nothing).")


class CalendarRename(BaseModel):
    """A calendar's new name."""

    model_config = ConfigDict(extra="forbid")

    calendar_id: ProviderId = Field(description="The calendar.")
    name: CalendarName = Field(description="Its new name.")


class EventSearchQuery(BaseModel):
    """Words looked for in the calendars shown."""

    model_config = ConfigDict(extra="forbid")

    q: _SearchWords = Field(description="The person's words.")
    calendar_ids: list[ProviderId] = Field(
        min_length=1,
        max_length=WORKBENCH_CALENDAR_IDS_MAX,
        description="The calendars asked.",
    )


class EventSearch(BaseModel):
    """What a search found, in time order."""

    events: list[CalendarEvent] = Field(description="The events found, the earliest first.")
    truncated: bool = Field(description="True when more were found than are shown.")
    failed: list[str] = Field(description="The calendars that could not be read.")


class CalendarWindow(BaseModel):
    """One calendar's events over the window — or why it could not be read."""

    calendar_id: str = Field(description="The calendar.")
    events: list[CalendarEvent] = Field(description="Its events, in order.")
    truncated: bool = Field(
        description="Cut at the published bound (workbench_calendar_window_max_events)."
    )
    skipped: int = Field(ge=0, description="Events whose times could not be read.")
    error: str | None = Field(description="The refusal that kept this calendar unread.")


class EventsWindow(BaseModel):
    """Every calendar of a view over its window."""

    calendars: list[CalendarWindow] = Field(description="One entry per calendar asked.")


#: Minutes before the event; ``NO_REMINDER`` takes the reminder off.
OptionalReminder = Annotated[
    int | None, Field(ge=NO_REMINDER, le=WORKBENCH_EVENT_REMINDER_MAX_MINUTES)
]


#: How far a change reaches: an occurrence alone, or the whole series.
EventScope = Literal["occurrence", "series"]


class _Timed(TimezoneValidatorMixin, BaseModel):
    """Bounds as the page sends them, judged in their zone."""

    model_config = ConfigDict(extra="forbid")

    start: OptionalBound = None
    end: OptionalBound = None
    all_day: bool | None = None
    timezone: str | None = Field(default=None, description="The zone the wall times are read in.")

    def _check_bounds(self, *, required: bool) -> None:
        if (self.start is None) != (self.end is None):
            raise ValueError("a start and an end go together")
        if self.start is None or self.end is None:
            if required:
                raise ValueError("an event has a start and an end")
            if self.all_day is not None:
                raise ValueError("switching all-day carries both bounds")
            return
        if self.all_day is None:
            raise ValueError("bounds say whether they are days (all_day)")
        if not self.all_day and self.timezone is None:
            raise ValueError("a wall time is read in a zone")
        zone = ZoneInfo(self.timezone or "UTC")
        if not ends_after(self.start, self.end, zone, all_day=bool(self.all_day)):
            raise ValueError("an event ends after it starts")


class NewEvent(_Timed):
    """An event to create; its key is the provider's own idempotency."""

    calendar_id: ProviderId = Field(description="The calendar it goes in.")
    summary: Summary = Field(description="Its title.")
    start: Bound = Field(description="A day (all-day) or a wall time YYYY-MM-DDTHH:MM.")
    end: Bound = Field(description="A day, EXCLUSIVE (all-day), or a wall time.")
    all_day: bool = Field(default=False, description="Whether its bounds are days.")
    location: OptionalLocation = Field(default=None, description="Where it takes place.")
    description: OptionalDescription = Field(default=None, description="Its notes.")
    attendees: _Attendees = Field(default_factory=list, description="Who is invited.")
    conference: bool = Field(
        default=False, description="Attach a video call (where the provider can)."
    )
    reminder_minutes: OptionalReminder = Field(
        default=None, description="A reminder this long before; left out, the calendar's own."
    )
    busy: bool | None = Field(default=None, description="Whether its time shows as taken.")
    private: bool | None = Field(default=None, description="Whether its details stay private.")
    recurrence: RecurrenceSpec | None = Field(
        default=None, description="When it happens again, from its own first day."
    )
    idempotency_key: UUID = Field(description="One key per form: the provider creates it once.")

    @model_validator(mode="after")
    def _bounds(self) -> Self:
        self._check_bounds(required=True)
        return self


class EventChange(_Timed):
    """What changes on one event — an occurrence alone; a field left out is kept."""

    calendar_id: ProviderId = Field(description="The event's calendar.")
    event_id: ProviderId = Field(description="The event — an occurrence's own id.")
    summary: OptionalSummary = Field(default=None, description="A new title.")
    start: OptionalBound = Field(default=None, description="A new start (with ``end``).")
    end: OptionalBound = Field(default=None, description="A new end (with ``start``).")
    all_day: bool | None = Field(
        default=None, description="Switch to or from all-day (both bounds given)."
    )
    location: OptionalLocation = Field(default=None, description="A new place ('' clears it).")
    description: OptionalDescription = Field(default=None, description="New notes ('' clears).")
    attendees: OptionalAttendees = Field(default=None, description="The new list of invitees.")
    reminder_minutes: OptionalReminder = Field(
        default=None, description="A new reminder; -1 takes it off, left out it is kept."
    )
    busy: bool | None = Field(default=None, description="Whether its time shows as taken.")
    private: bool | None = Field(default=None, description="Whether its details stay private.")
    conference: bool = Field(
        default=False, description="Adds a video call, where the provider has one."
    )
    notify: bool | None = Field(
        default=None,
        description="Tell the attendees (where the provider lets the page choose; else refused).",
    )
    scope: EventScope = Field(default="occurrence", description="This occurrence, or its series.")
    recurrence: RecurrenceSpec | None = Field(
        default=None, description="A new rule for the whole series."
    )

    @model_validator(mode="after")
    def _a_change(self) -> Self:
        self._check_bounds(required=False)
        if self.recurrence is not None and (self.scope != "series" or self.timezone is None):
            raise ValueError("a rule belongs to a whole series, read in a zone")
        named = (
            self.summary,
            self.start,
            self.location,
            self.description,
            self.attendees,
            self.reminder_minutes,
            self.busy,
            self.private,
            True if self.conference else None,
            self.recurrence,
        )
        if all(value is None for value in named):
            raise ValueError("a change names at least one field")
        return self
