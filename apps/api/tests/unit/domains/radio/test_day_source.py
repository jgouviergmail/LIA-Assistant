"""The listener's day as the antenna reads it: nothing switched off is opened, nothing in company."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from uuid import UUID, uuid4

import pytest

from src.domains.briefing.consultations import SectionReadObserver, SelectedCardsReader
from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    CardsBundle,
    CardSection,
    CardStatus,
    WeatherData,
)
from src.domains.radio.constants import JOURNAL_EVENING_FROM_HOUR, JOURNAL_NOON_FROM_HOUR
from src.domains.radio.day_source import ListenerDay
from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.formats import Frequency
from src.domains.radio.personal import JournalPart, PersonalDraft, PersonalSource

pytestmark = pytest.mark.unit


async def test_cancelling_a_gathering_keeps_completed_and_interrupted_consultations() -> None:
    entered = asyncio.Event()

    class PendingReader(Reader):
        async def __call__(
            self, user_id: UUID, *, now: datetime, tz: tzinfo
        ) -> list[PersonalDraft]:
            entered.set()
            await asyncio.Event().wait()
            return []

    recorder = Recorder()
    task = asyncio.create_task(_day(Reader([]), PendingReader([]), recorder).day())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert recorder.rows == [(frozenset({"tickets", "meetings"}), frozenset({"meetings"}))]


NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)
#: The desk's time to live in these tests.
HORIZON_S = 300.0
DONE_EVENT = PersonalDraft(
    FactKind.EVENT,
    'Appointment "Dentist" took place today',
    "done:event:1",
    Sensitivity.PERSONAL,
    JournalPart.DONE,
)
AHEAD_EVENT = PersonalDraft(
    FactKind.EVENT,
    'Appointment "Board" on Tuesday',
    "event:9",
    Sensitivity.PERSONAL,
    JournalPart.AHEAD,
)
SENT_MAIL = PersonalDraft(
    FactKind.EMAIL,
    'E-mail sent to Sam: "Plans"',
    "done:email:1",
    Sensitivity.PERSONAL,
    JournalPart.DONE,
)
TICKET = PersonalDraft(
    FactKind.TICKET,
    'Ticket "Renew the lease" waits on the listener',
    "ticket:1",
    Sensitivity.PERSONAL,
)
MEETING = PersonalDraft(
    FactKind.MEETING,
    'Meeting "Budget review" decided to move the launch',
    "meeting:1",
    Sensitivity.PERSONAL,
)


def _cards() -> CardsBundle:
    def ok(data: AgendaData | WeatherData) -> CardSection:
        return CardSection(status=CardStatus.OK, data=data, generated_at=NOW, from_cache=True)

    empty = CardSection(status=CardStatus.EMPTY, generated_at=NOW, from_cache=True)
    return CardsBundle(
        weather=ok(
            WeatherData(
                temperature_c=17.6,
                condition_code="Rain",
                description="light rain",
                icon_emoji="🌧",
                location_city="Lyon",
            )
        ),
        agenda=ok(AgendaData(events=[AgendaEventItem(title="Dentist", start_local="09:30")])),
        mails=empty,
        birthdays=empty,
        reminders=empty,
        health=empty,
        for_you=empty,
        tasks=empty,
        documents=empty,
    )


class Reader:
    """A source reader that counts its calls."""

    def __init__(self, drafts: list[PersonalDraft], *, fails: bool = False) -> None:
        self.calls = 0
        self._drafts = drafts
        self._fails = fails

    async def __call__(self, user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
        self.calls += 1
        if self._fails:
            raise RuntimeError("database unavailable")
        return self._drafts


class Recorder:
    """What the gatherings recorded as opened and failed."""

    def __init__(self) -> None:
        self.rows: list[tuple[frozenset[str], frozenset[str]]] = []

    def __call__(self, *, opened: frozenset[str], failed: frozenset[str], duration_ms: int) -> None:
        self.rows.append((opened, failed))


async def _read_cards(
    sections: frozenset[str], *, on_read: SectionReadObserver | None = None
) -> CardsBundle:
    return _cards()


async def _broken_cards(
    sections: frozenset[str], *, on_read: SectionReadObserver | None = None
) -> CardsBundle:
    raise ConnectionError("redis unavailable")


def _day(
    tickets: Reader,
    meetings: Reader,
    recorder: Recorder,
    *,
    disabled_sources: frozenset[PersonalSource] = frozenset(),
    public_mode: bool = False,
    journal_frequency: Frequency = Frequency.NORMAL,
    cards: SelectedCardsReader = _read_cards,
    done: Mapping[PersonalSource, Reader] | None = None,
    ahead: Mapping[PersonalSource, Reader] | None = None,
    now: datetime = NOW,
    tz: tzinfo = UTC,
) -> ListenerDay:
    return ListenerDay(
        user_id=uuid4(),
        tz=tz,
        disabled_sources=disabled_sources,
        public_mode=public_mode,
        journal_frequency=journal_frequency,
        cards=cards,
        readers={PersonalSource.TICKETS: tickets, PersonalSource.MEETINGS: meetings},
        done_readers=done or {},
        ahead_readers=ahead or {},
        horizon_s=HORIZON_S,
        record=recorder,
        clock=lambda: now,
    )


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 26, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("disabled", "read_calls"),
    [(PersonalSource.MAILS, 1), (PersonalSource.SENT_MAILS, 0)],
)
async def test_sent_mail_has_its_own_switch(disabled: PersonalSource, read_calls: int) -> None:
    sent = Reader([SENT_MAIL])
    facts = await _day(
        Reader([]),
        Reader([]),
        Recorder(),
        disabled_sources=frozenset({disabled}),
        done={PersonalSource.SENT_MAILS: sent},
        now=_at(JOURNAL_NOON_FROM_HOUR),
    ).day()
    assert sent.calls == read_calls
    assert [fact.text for fact in facts.done] == ([SENT_MAIL.text] if read_calls else [])


async def test_journal_off_reads_only_weather_even_with_personal_sources_enabled() -> None:
    tickets, meetings, recorder = Reader([TICKET]), Reader([MEETING]), Recorder()
    selected: list[frozenset[str]] = []

    async def cards(
        sections: frozenset[str], *, on_read: SectionReadObserver | None = None
    ) -> CardsBundle:
        selected.append(sections)
        return _cards()

    facts = await _day(
        tickets,
        meetings,
        recorder,
        journal_frequency=Frequency.OFF,
        cards=cards,
        done={PersonalSource.AGENDA: Reader([DONE_EVENT])},
        ahead={PersonalSource.AGENDA: Reader([AHEAD_EVENT])},
        now=_at(JOURNAL_EVENING_FROM_HOUR),
    ).day()
    assert selected == [frozenset({"weather"})]
    assert tickets.calls == meetings.calls == 0
    assert not facts.corner and not facts.done and not facts.ahead
    assert all(fact.kind is FactKind.WEATHER for fact in facts.day)
    assert recorder.rows == []


async def test_a_source_switched_off_is_never_opened_nor_recorded() -> None:
    tickets, meetings, recorder = Reader([TICKET]), Reader([MEETING]), Recorder()
    facts = await _day(
        tickets, meetings, recorder, disabled_sources=frozenset({PersonalSource.TICKETS})
    ).day()
    assert tickets.calls == 0
    assert recorder.rows == [(frozenset({"meetings"}), frozenset())]
    assert [fact.key for fact in facts.corner] == ["meeting:1"]
    assert all(fact.kind is not FactKind.TICKET for fact in facts.day)


async def test_in_company_only_the_weather_is_read_and_no_reader_runs() -> None:
    tickets, meetings, recorder = Reader([TICKET]), Reader([MEETING]), Recorder()
    facts = await _day(tickets, meetings, recorder, public_mode=True).day()
    assert (tickets.calls, meetings.calls, recorder.rows) == (0, 0, [])
    assert [fact.kind for fact in facts.day] == [FactKind.WEATHER]
    assert facts.corner == ()


async def test_a_blind_reader_is_silent_recorded_as_failed_and_the_others_speak() -> None:
    tickets, meetings, recorder = Reader([TICKET], fails=True), Reader([MEETING]), Recorder()
    facts = await _day(tickets, meetings, recorder).day()
    assert recorder.rows == [(frozenset({"tickets", "meetings"}), frozenset({"tickets"}))]
    assert [fact.key for fact in facts.corner] == ["meeting:1"]
    assert {fact.kind for fact in facts.day} == {FactKind.EVENT, FactKind.WEATHER}


async def test_a_briefing_cache_that_fails_leaves_the_readers_speaking() -> None:
    tickets, meetings, recorder = Reader([TICKET]), Reader([MEETING]), Recorder()
    facts = await _day(tickets, meetings, recorder, cards=_broken_cards).day()
    assert [fact.key for fact in facts.day] == ["ticket:1"]
    assert [fact.key for fact in facts.corner] == ["meeting:1"]


class TestDoneAndAhead:
    """ADR-324 decision 41 (lot 4b): what was done and what lies ahead are read for the
    editions the desk may be asked before it is read again."""

    def readers(self) -> tuple[Reader, Reader, Reader, Reader, Recorder]:
        return (
            Reader([TICKET]),
            Reader([MEETING]),
            Reader([DONE_EVENT]),
            Reader([AHEAD_EVENT]),
            Recorder(),
        )

    async def test_the_morning_reads_neither(self) -> None:
        tickets, meetings, done, ahead, recorder = self.readers()
        day = _day(
            tickets,
            meetings,
            recorder,
            done={PersonalSource.AGENDA: done},
            ahead={PersonalSource.AGENDA: ahead},
            now=_at(JOURNAL_NOON_FROM_HOUR - 2),
        )
        facts = await day.day()
        assert (done.calls, ahead.calls) == (0, 0)
        assert (facts.done, facts.ahead) == ((), ())
        assert recorder.rows == [(frozenset({"tickets", "meetings"}), frozenset())]

    async def test_the_noon_reads_what_was_done_the_evening_the_week_ahead_too(self) -> None:
        tickets, meetings, done, ahead, recorder = self.readers()
        noon = _day(
            tickets,
            meetings,
            recorder,
            done={PersonalSource.AGENDA: done},
            ahead={PersonalSource.AGENDA: ahead},
            now=_at(JOURNAL_NOON_FROM_HOUR, 30),
        )
        facts = await noon.day()
        assert (done.calls, ahead.calls) == (1, 0)
        assert [f.key for f in facts.done] == ["done:event:1"] and facts.ahead == ()
        evening = _day(
            tickets,
            meetings,
            recorder,
            done={PersonalSource.AGENDA: done},
            ahead={PersonalSource.AGENDA: ahead},
            now=_at(JOURNAL_EVENING_FROM_HOUR, 30),
        )
        facts = await evening.day()
        assert (done.calls, ahead.calls) == (2, 1)
        assert [f.key for f in facts.ahead] == ["event:9"]
        # One row per gathering, the agenda recorded ONCE though read for two parts.
        assert recorder.rows[-1] == (frozenset({"tickets", "meetings", "agenda"}), frozenset())

    async def test_minutes_before_an_edition_the_desk_already_reads_its_parts(self) -> None:
        """A journal produced two minutes before noon airs at noon: the gathering it reads
        must hold what was done this morning — the horizon is the desk's time to live."""
        tickets, meetings, done, _ahead, recorder = self.readers()
        just_before = _at(JOURNAL_NOON_FROM_HOUR) - timedelta(seconds=HORIZON_S / 2)
        day = _day(tickets, meetings, recorder, done={PersonalSource.AGENDA: done}, now=just_before)
        assert JournalPart.DONE in day.parts_due(just_before)
        assert JournalPart.DONE not in day.parts_due(just_before - timedelta(seconds=HORIZON_S))
        await day.day()
        assert done.calls == 1

    async def test_a_source_switched_off_is_not_read_for_its_done_part_either(self) -> None:
        tickets, meetings, done, _ahead, recorder = self.readers()
        day = _day(
            tickets,
            meetings,
            recorder,
            disabled_sources=frozenset({PersonalSource.AGENDA}),
            done={PersonalSource.AGENDA: done},
            now=_at(JOURNAL_EVENING_FROM_HOUR),
        )
        await day.day()
        assert done.calls == 0

    async def test_in_company_nothing_done_or_ahead_is_read(self) -> None:
        tickets, meetings, done, ahead, recorder = self.readers()
        day = _day(
            tickets,
            meetings,
            recorder,
            public_mode=True,
            done={PersonalSource.AGENDA: done},
            ahead={PersonalSource.AGENDA: ahead},
            now=_at(JOURNAL_EVENING_FROM_HOUR),
        )
        await day.day()
        assert (done.calls, ahead.calls, recorder.rows) == (0, 0, [])

    async def test_a_source_read_twice_whose_one_read_failed_is_recorded_failed_and_speaks(
        self,
    ) -> None:
        tickets, meetings, _done, _ahead, recorder = self.readers()
        blind = Reader([], fails=True)
        day = _day(
            tickets,
            meetings,
            recorder,
            done={PersonalSource.TICKETS: blind},
            now=_at(JOURNAL_NOON_FROM_HOUR, 30),
        )
        facts = await day.day()
        assert "ticket:1" in [f.key for f in facts.day]  # the waiting ticket still speaks
        assert recorder.rows == [(frozenset({"tickets", "meetings"}), frozenset({"tickets"}))]

    async def test_the_edition_is_read_on_the_listeners_clock(self) -> None:
        tickets, meetings, done, _ahead, recorder = self.readers()
        east = timezone(timedelta(hours=8))  # 07:00 UTC is 15:00 there: the noon edition
        day = _day(tickets, meetings, recorder, done={PersonalSource.AGENDA: done}, tz=east)
        await day.day()
        assert done.calls == 1
