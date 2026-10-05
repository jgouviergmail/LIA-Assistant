"""The listener's own material as facts: their DAY, and their personal CORNER.

Two kinds of personal material, decided by the SOURCE, never by a fact's words, and
told by the listener's JOURNAL in the edition of the moment (ADR-324 decision 41):

- the DAY — appointments, reminders, tasks, open commitments, tickets waiting on
  them, birthdays, unread mail (and the weather, neutral) — what every edition
  voices as the day ahead;
- the CORNER — health, meetings and their decisions, the notifications LIA sent,
  people to get back to, knowledge spaces, kept answers, the conversation under
  way — the things to note, which the morning and the evening editions add; the
  noon's stays with the day, so a short edition never becomes a catch-all.

The sources the Today Briefing already reads (agenda, reminders, tasks, open
commitments, birthdays, unread mails, health, weather) are read from ITS sections,
never from a second reader of each connector: one answer to « what does this
person's day hold », one cache, one consultation register (a cache hit is not a
consultation, ADR-263). The others are read by the radio's own readers and handed
in as drafts. This module turns them into facts:

- only a section whose status is OK speaks — an ERROR section may carry a STALE payload,
  and the radio does not voice yesterday's state as today's;
- a source the person switched off for the radio stays silent;
- each source is bounded (the writer reads a day, not an inbox);
- every personal fact is marked PERSONAL — only the host may say it — and health
  SENSITIVE; the weather is public (it belongs to the neutral material);
- figures are written the way a line will say them (a temperature rounded to the
  degree, a probability in percent), so the verifier finds in the fact the number the
  voice speaks;
- every fact carries a key for the anti-repeat ledger (the record's own id when the
  provider sent one, a digest of its words otherwise).

Pure: the bundle and the drafts are inputs (the caller reads them).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, NamedTuple

from src.domains.briefing.constants import SECTION_FOR_YOU
from src.domains.briefing.schemas import (
    AgendaData,
    BirthdaysData,
    CardsBundle,
    CardSection,
    CardStatus,
    ForYouData,
    HealthData,
    MailsData,
    RemindersData,
    TasksData,
    WeatherData,
)
from src.domains.radio.constants import FACT_KEY_MAX_CHARS, FACT_TEXT_MAX_CHARS
from src.domains.radio.facts import FactKind, RadioFact, Sensitivity
from src.domains.shared.commercial_content import is_commercial_content


class PersonalSource(StrEnum):
    """A source of the listener's material the person may switch off for the radio."""

    AGENDA = "agenda"
    REMINDERS = "reminders"
    TASKS = "tasks"
    COMMITMENTS = "commitments"
    TICKETS = "tickets"
    BIRTHDAYS = "birthdays"
    MAILS = "mails"
    SENT_MAILS = "sent_mails"
    #: What LIA did for the listener today — the effect register (decision 41, lot 4b).
    ACTIONS = "actions"
    WEATHER = "weather"
    HEALTH = "health"
    MEETINGS = "meetings"
    NOTIFICATIONS = "notifications"
    RELATIONS = "relations"
    SPACES = "spaces"
    BOOKMARKS = "bookmarks"
    CONVERSATION = "conversation"


#: The sources of the personal corner (the things to note); every other one makes the day.
CORNER_SOURCES: Final[frozenset[PersonalSource]] = frozenset(
    {
        PersonalSource.HEALTH,
        PersonalSource.MEETINGS,
        PersonalSource.NOTIFICATIONS,
        PersonalSource.RELATIONS,
        PersonalSource.SPACES,
        PersonalSource.BOOKMARKS,
        PersonalSource.CONVERSATION,
    }
)

#: The sources whose facts are public — the neutral material the opening and the
#: sign-off voice. The only ones read while the listener is in company.
NEUTRAL_SOURCES: Final[frozenset[PersonalSource]] = frozenset({PersonalSource.WEATHER})


class JournalPart(StrEnum):
    """The part of the journal a fact belongs to (ADR-324 decision 41).

    The DAY and the CORNER are decided by a fact's SOURCE; what was DONE and what lies
    AHEAD are read by readers of their own, and each of their drafts names its part.
    """

    DAY = "day"
    CORNER = "corner"
    DONE = "done"
    AHEAD = "ahead"


def default_part(source: PersonalSource) -> JournalPart:
    """The part a draft of ``source`` joins when it names none."""
    return JournalPart.CORNER if source in CORNER_SOURCES else JournalPart.DAY


#: The most facts one source offers a segment — per part of the journal it fills.
MAX_PER_SOURCE: Final[dict[PersonalSource, int]] = {
    PersonalSource.AGENDA: 6,
    PersonalSource.REMINDERS: 5,
    PersonalSource.TASKS: 5,
    PersonalSource.COMMITMENTS: 4,
    PersonalSource.TICKETS: 5,
    PersonalSource.BIRTHDAYS: 3,
    PersonalSource.MAILS: 5,
    PersonalSource.SENT_MAILS: 5,
    PersonalSource.ACTIONS: 4,
    PersonalSource.WEATHER: 1,
    PersonalSource.HEALTH: 2,
    PersonalSource.MEETINGS: 2,
    PersonalSource.NOTIFICATIONS: 3,
    PersonalSource.RELATIONS: 2,
    PersonalSource.SPACES: 2,
    PersonalSource.BOOKMARKS: 2,
    PersonalSource.CONVERSATION: 1,
}


class PersonalDraft(NamedTuple):
    """A fact before it is numbered: what it is, its words, its ledger key, who may say it,
    and the part of the journal it fills (``None``: the one its source decides)."""

    kind: FactKind
    text: str
    key: str
    sensitivity: Sensitivity
    part: JournalPart | None = None


def digest(*parts: str) -> str:
    """A stable ledger key for a record the provider sent no id for."""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]


def _payload[T](section: CardSection, kind: type[T]) -> T | None:
    return (
        section.data if section.status is CardStatus.OK and isinstance(section.data, kind) else None
    )


def _agenda(data: AgendaData) -> Iterator[PersonalDraft]:
    for event in data.events:
        text = f'Appointment "{event.title}" at {event.start_local}'
        if event.end_local:
            text += f" until {event.end_local}"
        if event.location:
            text += f", {event.location}"
        key = f"event:{event.id or digest(event.title, event.start_local)}"
        yield PersonalDraft(FactKind.EVENT, text, key, Sensitivity.PERSONAL)


def _reminders(data: RemindersData) -> Iterator[PersonalDraft]:
    for reminder in data.items:
        key = f"reminder:{reminder.id or digest(reminder.content, reminder.trigger_at_local)}"
        text = f"Reminder due {reminder.trigger_at_local}: {reminder.content}"
        yield PersonalDraft(FactKind.REMINDER, text, key, Sensitivity.PERSONAL)


def _tasks(data: TasksData) -> Iterator[PersonalDraft]:
    for task in data.items:
        if task.overdue:
            when = " is overdue"
        elif task.days_until_due == 0:
            when = " is due today"
        elif task.days_until_due is not None:
            when = f" is due in {task.days_until_due} days"
        else:
            when = ""
        key = f"task:{task.id or digest(task.title)}"
        yield PersonalDraft(FactKind.TASK, f'Task "{task.title}"{when}', key, Sensitivity.PERSONAL)


def _commitments(data: ForYouData) -> Iterator[PersonalDraft]:
    for loop in data.open_loops:
        who = loop.counterparty or "someone"
        side = "owes" if loop.direction == "user_owes" else "is waiting for"
        text = f"The listener {side} {who}: {loop.subject} (open for {loop.days_open} days)"
        yield PersonalDraft(
            FactKind.COMMITMENT, text, f"commitment:{loop.id}", Sensitivity.PERSONAL
        )


def _birthdays(data: BirthdaysData) -> Iterator[PersonalDraft]:
    for item in data.items:
        when = "today" if item.days_until == 0 else f"in {item.days_until} days"
        text = f"{item.contact_name}'s birthday is {when}"
        if item.age_at_next is not None:
            text += f", turning {item.age_at_next}"
        key = f"birthday:{digest(item.contact_name, item.date_iso)}"
        yield PersonalDraft(FactKind.RELATION, text, key, Sensitivity.PERSONAL)


def _mails(data: MailsData) -> Iterator[PersonalDraft]:
    if data.total_unread_today:
        text = f"Unread e-mails received today: {data.total_unread_today}"
        yield PersonalDraft(
            FactKind.EMAIL, text, f"mails:{data.total_unread_today}", Sensitivity.PERSONAL
        )
    for mail in data.items:
        if is_commercial_content(mail.subject, email=True):
            continue
        sender = mail.sender_name or mail.sender_email or "an unknown sender"
        text = f'Unread e-mail from {sender}: "{mail.subject}" ({mail.received_local})'
        key = f"email:{mail.id or digest(sender, mail.subject, mail.received_local)}"
        yield PersonalDraft(FactKind.EMAIL, text, key, Sensitivity.PERSONAL)


def _health(data: HealthData) -> Iterator[PersonalDraft]:
    for item in data.items:
        if item.value_today is None:
            continue
        text = f"{item.kind.replace('_', ' ')} today: {round(item.value_today)} {item.unit}"
        if item.value_avg_window is not None:
            text += (
                f"; daily average over the last {item.window_days} days: "
                f"{round(item.value_avg_window)} {item.unit}"
            )
        key = f"health:{item.kind}:{round(item.value_today)}"
        yield PersonalDraft(FactKind.HEALTH, text, key, Sensitivity.SENSITIVE)


def _weather(data: WeatherData) -> Iterator[PersonalDraft]:
    place = f" in {data.location_city}" if data.location_city else ""
    text = f"Weather{place}: {data.description}, {round(data.temperature_c)} °C now"
    if data.temperature_min_c is not None and data.temperature_max_c is not None:
        text += (
            f", between {round(data.temperature_min_c)} and "
            f"{round(data.temperature_max_c)} °C today"
        )
    if data.precipitation_probability is not None:
        text += f", {round(data.precipitation_probability * 100)} % chance of rain in 3 hours"
    yield PersonalDraft(
        FactKind.WEATHER, text, f"weather:{data.location_city or 'here'}", Sensitivity.PUBLIC
    )


def _read[T](
    section: CardSection, kind: type[T], render: Callable[[T], Iterator[PersonalDraft]]
) -> Iterator[PersonalDraft]:
    data = _payload(section, kind)
    return render(data) if data is not None else iter(())


#: Where each source reads in the bundle, and how its payload becomes facts.
_READERS: Final[dict[PersonalSource, Callable[[CardsBundle], Iterator[PersonalDraft]]]] = {
    PersonalSource.AGENDA: lambda cards: _read(cards.agenda, AgendaData, _agenda),
    PersonalSource.REMINDERS: lambda cards: _read(cards.reminders, RemindersData, _reminders),
    PersonalSource.TASKS: lambda cards: _read(cards.tasks, TasksData, _tasks),
    PersonalSource.COMMITMENTS: lambda cards: _read(cards.for_you, ForYouData, _commitments),
    PersonalSource.BIRTHDAYS: lambda cards: _read(cards.birthdays, BirthdaysData, _birthdays),
    PersonalSource.MAILS: lambda cards: _read(cards.mails, MailsData, _mails),
    PersonalSource.HEALTH: lambda cards: _read(cards.health, HealthData, _health),
    PersonalSource.WEATHER: lambda cards: _read(cards.weather, WeatherData, _weather),
}


#: The sources the Today Briefing reads — the others come from the radio's readers.
BRIEFING_SOURCES: Final[frozenset[PersonalSource]] = frozenset(_READERS)

#: Source names match the briefing's sections, except commitments (its For You card).
BRIEFING_SECTIONS: Final[dict[PersonalSource, str]] = {
    source: SECTION_FOR_YOU if source is PersonalSource.COMMITMENTS else source.value
    for source in BRIEFING_SOURCES
}


def briefing_drafts(cards: CardsBundle) -> dict[PersonalSource, list[PersonalDraft]]:
    """The drafts of every source the briefing's sections carry (an unhealthy one: none)."""
    return {source: list(read(cards)) for source, read in _READERS.items()}


@dataclass(frozen=True, slots=True)
class PersonalFacts:
    """The listener's material, numbered ``p1`` to ``pN`` across its four parts.

    Attributes:
        day: The day ahead, which every edition of the journal voices.
        corner: The things to note, which the morning and the evening editions add.
        done: What the listener did today, which the noon and the evening open on.
        ahead: Tomorrow and the rest of the week, which the evening closes on.
    """

    day: tuple[RadioFact, ...] = ()
    corner: tuple[RadioFact, ...] = ()
    done: tuple[RadioFact, ...] = ()
    ahead: tuple[RadioFact, ...] = ()


def personal_facts(
    drafts: Mapping[PersonalSource, Sequence[PersonalDraft]],
    *,
    disabled: frozenset[PersonalSource] = frozenset(),
) -> PersonalFacts:
    """The listener's material as facts, in source order, bounded per source and part.

    A record is ONE fact: a draft whose ledger key an earlier part already carries is
    left out (the week ahead never retells an appointment the day already holds).

    Args:
        drafts: Each source's drafts (the briefing's and the readers'); a source
            absent from the mapping has nothing to say.
        disabled: The sources the person switched off for the radio.

    Returns:
        The four parts, their ids unique across all of them.
    """
    parts: dict[JournalPart, list[RadioFact]] = {part: [] for part in JournalPart}
    taken: set[str] = set()
    for source in PersonalSource:
        if source in disabled:
            continue
        counted: dict[JournalPart, int] = dict.fromkeys(JournalPart, 0)
        for draft in drafts.get(source, ()):
            part = draft.part or default_part(source)
            if counted[part] >= MAX_PER_SOURCE[source] or draft.key in taken:
                continue
            counted[part] += 1
            taken.add(draft.key)
            parts[part].append(
                RadioFact(
                    id=f"p{sum(len(facts) for facts in parts.values()) + 1}",
                    kind=draft.kind,
                    text=draft.text[:FACT_TEXT_MAX_CHARS],
                    key=draft.key[:FACT_KEY_MAX_CHARS],
                    sensitivity=draft.sensitivity,
                )
            )
    return PersonalFacts(
        day=tuple(parts[JournalPart.DAY]),
        corner=tuple(parts[JournalPart.CORNER]),
        done=tuple(parts[JournalPart.DONE]),
        ahead=tuple(parts[JournalPart.AHEAD]),
    )


def assert_sources_complete() -> None:
    """Refuse to import with a source no bound is declared for (ADR-085).

    Raises:
        RuntimeError: When a source has no bound.
    """
    missing = sorted(source.value for source in PersonalSource if source not in MAX_PER_SOURCE)
    if missing:
        raise RuntimeError(f"personal sources without a bound: {missing}")


assert_sources_complete()


__all__ = [
    "BRIEFING_SOURCES",
    "CORNER_SOURCES",
    "MAX_PER_SOURCE",
    "NEUTRAL_SOURCES",
    "JournalPart",
    "PersonalDraft",
    "PersonalFacts",
    "PersonalSource",
    "assert_sources_complete",
    "briefing_drafts",
    "default_part",
    "digest",
    "personal_facts",
]
