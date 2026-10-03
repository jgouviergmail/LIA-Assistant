"""The listener's material as facts: fresh, bounded, host-only — the day apart from the corner."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    CardsBundle,
    CardSection,
    CardStatus,
    ForYouData,
    ForYouLoopItem,
    HealthData,
    HealthSummaryItem,
    MailItem,
    MailsData,
    SectionPayload,
    TaskItem,
    TasksData,
    WeatherData,
)
from src.domains.radio.facts import FactKind, FactPack, Sensitivity
from src.domains.radio.formats import RadioFormat
from src.domains.radio.personal import (
    CORNER_SOURCES,
    MAX_PER_SOURCE,
    JournalPart,
    PersonalDraft,
    PersonalFacts,
    PersonalSource,
    briefing_drafts,
    default_part,
    personal_facts,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)
LOCALES = ("en", "fr", "de", "es", "it", "zh")
_WEB = Path(__file__).resolve().parents[5] / "web"


def section(data: SectionPayload, status: CardStatus = CardStatus.OK) -> CardSection:
    return CardSection(status=status, data=data, generated_at=NOW)


def empty() -> CardSection:
    return section(None, CardStatus.EMPTY)


def bundle(**sections: CardSection) -> CardsBundle:
    names = (
        "weather",
        "agenda",
        "mails",
        "birthdays",
        "reminders",
        "health",
        "for_you",
        "tasks",
        "documents",
        "workboard",
    )
    return CardsBundle(**{name: sections.get(name, empty()) for name in names})


AGENDA = AgendaData(
    events=[
        AgendaEventItem(title="Dentist", start_local="09:30", end_local="10:00", id="e1"),
        AgendaEventItem(title="Team review", start_local="14:00", location="Room 4"),
    ]
)
WEATHER = WeatherData(
    temperature_c=17.6,
    temperature_min_c=11.2,
    temperature_max_c=21.5,
    condition_code="Rain",
    description="light rain",
    icon_emoji="🌧",
    location_city="Lyon",
    precipitation_probability=0.35,
)


def day_of(cards: CardsBundle, **kwargs: frozenset[PersonalSource]) -> PersonalFacts:
    return personal_facts(briefing_drafts(cards), **kwargs)


def test_the_day_reads_in_source_order_with_ids_the_writer_cites() -> None:
    facts = day_of(bundle(agenda=section(AGENDA), weather=section(WEATHER))).day
    assert [f.id for f in facts] == ["p1", "p2", "p3"]
    assert facts[0].text == 'Appointment "Dentist" at 09:30 until 10:00'
    assert facts[1].text == 'Appointment "Team review" at 14:00, Room 4'
    assert facts[0].key == "event:e1"
    FactPack(format=RadioFormat.JOURNAL, facts=facts)  # personal material admits them all


def test_only_the_host_may_say_it_and_health_is_sensitive() -> None:
    health = HealthData(
        items=[
            HealthSummaryItem(
                kind="steps",
                value_today=6123.4,
                value_avg_window=8450.2,
                unit="steps",
                window_days=14,
                days_with_data=12,
            )
        ]
    )
    material = day_of(bundle(agenda=section(AGENDA), health=section(health)))
    assert {f.sensitivity for f in material.day} == {Sensitivity.PERSONAL}
    [steps] = material.corner  # health belongs to the corner, never to « your day »
    assert steps.kind is FactKind.HEALTH and steps.sensitivity is Sensitivity.SENSITIVE
    assert "6123 steps" in steps.text and "14 days" in steps.text


def test_figures_are_written_the_way_the_voice_will_say_them() -> None:
    [weather] = day_of(bundle(weather=section(WEATHER))).day
    assert weather.text == (
        "Weather in Lyon: light rain, 18 °C now, between 11 and 22 °C today, "
        "35 % chance of rain in 3 hours"
    )
    assert weather.sensitivity is Sensitivity.PUBLIC


def test_a_stale_payload_behind_an_error_is_never_voiced() -> None:
    stale = section(AGENDA, CardStatus.ERROR)
    assert day_of(bundle(agenda=stale)) == PersonalFacts()


def test_a_source_switched_off_stays_silent() -> None:
    facts = day_of(
        bundle(agenda=section(AGENDA), weather=section(WEATHER)),
        disabled=frozenset({PersonalSource.AGENDA}),
    ).day
    assert [f.kind for f in facts] == [FactKind.WEATHER]


def test_an_inbox_is_bounded_and_counted() -> None:
    mails = MailsData(
        items=[
            MailItem(sender_name=f"Sender {n}", subject=f"Subject {n}", received_local="08:00")
            for n in range(10)
        ],
        total_unread_today=10,
    )
    facts = day_of(bundle(mails=section(mails))).day
    assert len(facts) == MAX_PER_SOURCE[PersonalSource.MAILS]
    assert facts[0].text == "Unread e-mails received today: 10"


def test_tasks_and_commitments_say_when_and_who() -> None:
    tasks = TasksData(
        items=[
            TaskItem(title="Tax form", overdue=True, days_until_due=-2),
            TaskItem(title="Slides", overdue=False, days_until_due=3),
        ],
        overdue_count=1,
    )
    loops = ForYouData(
        open_loops=[
            ForYouLoopItem(
                id="l1",
                subject="the signed quote",
                counterparty="Sam",
                direction="waiting_on_other",
                days_open=4,
            )
        ],
        recent_automations=[],
    )
    texts = [f.text for f in day_of(bundle(tasks=section(tasks), for_you=section(loops))).day]
    assert texts == [
        'Task "Tax form" is overdue',
        'Task "Slides" is due in 3 days',
        "The listener is waiting for Sam: the signed quote (open for 4 days)",
    ]


def test_a_reader_s_drafts_join_their_part_bounded_and_numbered_after_the_briefing() -> None:
    """The radio's own readers (tickets, meetings…) hand in drafts: a ticket makes
    the day, a meeting the corner, and ids stay unique across both."""
    ticket = PersonalDraft(
        FactKind.TICKET, 'Ticket "Renew the lease" is overdue', "ticket:t1", Sensitivity.PERSONAL
    )
    meeting = PersonalDraft(
        FactKind.MEETING, 'Meeting "Budget": 2 decisions', "meeting:m1", Sensitivity.PERSONAL
    )
    drafts = {
        **briefing_drafts(bundle(agenda=section(AGENDA))),
        # Nine tickets, each its own record: one record is one fact, whatever its count.
        PersonalSource.TICKETS: [ticket._replace(key=f"ticket:t{n}") for n in range(9)],
        PersonalSource.MEETINGS: [meeting],
    }
    material = personal_facts(drafts)
    assert [f.kind for f in material.day].count(FactKind.TICKET) == MAX_PER_SOURCE[
        PersonalSource.TICKETS
    ]
    assert [f.kind for f in material.corner] == [FactKind.MEETING]
    ids = [f.id for f in (*material.day, *material.corner)]
    assert len(ids) == len(set(ids)) and ids[0] == "p1"


def _part_draft(kind: FactKind, text: str, key: str, part: JournalPart) -> PersonalDraft:
    return PersonalDraft(kind, text, key, Sensitivity.PERSONAL, part)


class TestJournalParts:
    """ADR-324 decision 41 (lot 4b): what was done and what lies ahead are parts of their own,
    named by the draft — the day and the corner stay decided by the source."""

    def test_a_draft_that_names_its_part_goes_there_and_the_others_follow_their_source(
        self,
    ) -> None:
        done = _part_draft(
            FactKind.EVENT, "the dentist took place", "done:event:e1", JournalPart.DONE
        )
        ahead = _part_draft(FactKind.EVENT, "the board on Tuesday", "event:e9", JournalPart.AHEAD)
        meeting = PersonalDraft(FactKind.MEETING, "Budget", "meeting:m1", Sensitivity.PERSONAL)
        drafts = briefing_drafts(bundle(agenda=section(AGENDA)))
        drafts[PersonalSource.AGENDA] = [*drafts[PersonalSource.AGENDA], done, ahead]
        drafts[PersonalSource.MEETINGS] = [meeting]
        material = personal_facts(drafts)
        assert [f.key for f in material.day][:1] == ["event:e1"] and len(material.day) == 2
        assert [f.key for f in material.done] == ["done:event:e1"]
        assert [f.key for f in material.ahead] == ["event:e9"]
        assert [f.key for f in material.corner] == ["meeting:m1"]
        ids = [f.id for f in (*material.day, *material.corner, *material.done, *material.ahead)]
        assert sorted(ids, key=lambda i: int(i[1:])) == [f"p{n}" for n in range(1, 6)]
        assert len(set(ids)) == 5

    def test_a_record_the_day_tells_is_not_told_again_by_the_week_ahead(self) -> None:
        again = _part_draft(FactKind.EVENT, "the same dentist", "event:e1", JournalPart.AHEAD)
        drafts = briefing_drafts(bundle(agenda=section(AGENDA)))
        drafts[PersonalSource.AGENDA] = [*drafts[PersonalSource.AGENDA], again]
        material = personal_facts(drafts)
        assert material.ahead == () and [f.key for f in material.day][0] == "event:e1"

    def test_each_part_of_a_source_is_bounded_on_its_own(self) -> None:
        bound = MAX_PER_SOURCE[PersonalSource.AGENDA]
        done = [
            _part_draft(FactKind.EVENT, f"done {n}", f"done:event:{n}", JournalPart.DONE)
            for n in range(bound + 3)
        ]
        ahead = [
            _part_draft(FactKind.EVENT, f"ahead {n}", f"event:a{n}", JournalPart.AHEAD)
            for n in range(bound + 3)
        ]
        material = personal_facts({PersonalSource.AGENDA: [*done, *ahead]})
        assert (len(material.done), len(material.ahead)) == (bound, bound)

    def test_what_lia_did_is_a_source_of_its_own_and_its_switch_holds(self) -> None:
        assert PersonalSource.ACTIONS in MAX_PER_SOURCE
        assert PersonalSource.ACTIONS not in CORNER_SOURCES
        did = _part_draft(FactKind.ACTION, "LIA sent an e-mail", "done:action:1", JournalPart.DONE)
        material = personal_facts({PersonalSource.ACTIONS: [did]})
        assert [f.kind for f in material.done] == [FactKind.ACTION] and material.day == ()
        silent = personal_facts(
            {PersonalSource.ACTIONS: [did]}, disabled=frozenset({PersonalSource.ACTIONS})
        )
        assert silent == PersonalFacts()

    def test_the_default_part_follows_the_source(self) -> None:
        assert default_part(PersonalSource.MEETINGS) is JournalPart.CORNER
        assert default_part(PersonalSource.AGENDA) is JournalPart.DAY
        assert all(default_part(source) is JournalPart.CORNER for source in CORNER_SOURCES)


@pytest.mark.parametrize("locale", LOCALES)
def test_every_personal_source_has_a_name_and_a_hint_in_every_language(locale: str) -> None:
    raw = (_WEB / "locales" / locale / "translation.json").read_text(encoding="utf-8")
    radio_settings = json.loads(raw)["radio"]["settings"]
    for source in PersonalSource:
        name = radio_settings["source"].get(source.value)
        hint = radio_settings["source_hints"].get(source.value)
        assert isinstance(name, str) and name.strip(), (locale, source)
        assert isinstance(hint, str) and hint.strip(), (locale, source)
