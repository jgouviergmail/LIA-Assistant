"""The editor's desk: the right facts to the right format, never twice, nothing to say named."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from src.domains.radio.facts import (
    FactKind,
    RadioFact,
    Sensitivity,
    SourceRef,
    clock_fact,
)
from src.domains.radio.formats import JournalEdition, RadioFormat
from src.domains.radio.packs import Desk, available_formats, pack_for

pytestmark = pytest.mark.unit

CLOCK = clock_fact(datetime(2026, 9, 26, 8, 5, tzinfo=UTC))
MORNING, NOON, EVENING = JournalEdition.MORNING, JournalEdition.NOON, JournalEdition.EVENING


def personal(fid: str, kind: FactKind, key: str | None = None) -> RadioFact:
    return RadioFact(
        id=fid,
        kind=kind,
        text=f"{kind.value} {fid}",
        key=key or f"k:{fid}",
        sensitivity=Sensitivity.PERSONAL,
    )


def news(fid: str) -> RadioFact:
    return RadioFact(
        id=fid,
        kind=FactKind.NEWS,
        text=f"story {fid}",
        key=f"n:{fid}",
        sensitivity=Sensitivity.PUBLIC,
        source=SourceRef(label="Outlet"),
    )


WEATHER = RadioFact(
    id="p9",
    kind=FactKind.WEATHER,
    text="Sunny, 21 °C",
    key="weather:here",
    sensitivity=Sensitivity.PUBLIC,
)
DAY = (
    personal("p1", FactKind.EVENT),
    personal("p2", FactKind.TASK),
    personal("p3", FactKind.COMMITMENT),
    personal("p4", FactKind.REMINDER),
    personal("p5", FactKind.TASK),
    WEATHER,
)
CORNER = (
    personal("p6", FactKind.MEETING),
    personal("p7", FactKind.BOOKMARK),
)
#: What the listener did today, and what the week ahead holds (ADR-324 decision 41).
DONE = (personal("d1", FactKind.EVENT), personal("d2", FactKind.TASK))
AHEAD = (personal("a1", FactKind.EVENT), personal("a2", FactKind.RELATION))


def ids(fmt: RadioFormat, desk: Desk, *, clock_mark: datetime | None = None) -> list[str] | None:
    pack = pack_for(fmt, desk, clock_mark=clock_mark)
    return None if pack is None else [fact.id for fact in pack.facts]


def journal(desk: Desk, edition: JournalEdition) -> list[str] | None:
    """The journal of ``edition``, given ``desk``."""
    return ids(RadioFormat.JOURNAL, replace(desk, edition=edition))


def test_the_opening_and_the_sign_off_say_nothing_about_the_person() -> None:
    desk = Desk(clock=CLOCK, day=DAY)
    assert ids(RadioFormat.OPENING, desk) == ["c1", "p9"]
    assert ids(RadioFormat.SIGN_OFF, desk) == []


def test_the_time_is_said_by_the_opening_and_at_a_clock_mark_alone() -> None:
    """Said at every programme, the date and the time were heard again and again
    (reported 2026-09-26: at the start, then again before the listener's day...)."""
    desk = Desk(clock=CLOCK, day=DAY, news={RadioFormat.BULLETIN: (news("n1"),)})
    assert journal(desk, MORNING) == ["p1", "p2", "p3", "p4", "p5", "p9"]
    assert ids(RadioFormat.BULLETIN, desk) == ["n1"]
    nine = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
    marked = pack_for(RadioFormat.BULLETIN, desk, clock_mark=nine)
    assert marked is not None
    [clock] = [fact for fact in marked.facts if fact.kind is FactKind.CLOCK]
    assert clock == clock_fact(nine)  # « the nine o'clock news » cites the MARK, not now


def test_the_weather_is_said_once_a_session() -> None:
    said = Desk(clock=CLOCK, day=DAY, said=frozenset({FactKind.WEATHER}))
    assert ids(RadioFormat.OPENING, said) == ["c1"]
    assert journal(said, MORNING) == ["p1", "p2", "p3", "p4", "p5"]
    for edition in JournalEdition:
        assert "p9" not in (journal(said, edition) or [])


class TestJournal:
    """ADR-324 decision 41: ONE journal in three editions — what each one is given."""

    FULL = Desk(clock=CLOCK, day=DAY, corner=CORNER, done=DONE, ahead=AHEAD)

    def test_the_morning_voices_the_day_ahead_and_the_things_to_note(self) -> None:
        # Never what was done (nothing was), never the week: the day's and the corner's.
        assert journal(self.FULL, MORNING) == ["p1", "p2", "p3", "p4", "p5", "p9", "p6", "p7"]

    def test_the_noon_opens_on_what_was_done_then_what_is_left(self) -> None:
        # The corner's items and the week ahead wait for the morning and the evening.
        assert journal(self.FULL, NOON) == ["d1", "d2", "p1", "p2", "p3", "p4", "p5", "p9"]

    def test_the_evening_goes_over_the_day_then_looks_ahead(self) -> None:
        assert journal(self.FULL, EVENING) == [
            "d1",
            "d2",
            "p1",
            "p2",
            "p3",
            "p4",
            "p5",
            "p9",
            "p6",
            "p7",
            "a1",
            "a2",
        ]

    def test_the_day_is_told_once_and_the_evening_goes_over_it_again(self) -> None:
        heard = Desk(clock=CLOCK, day=DAY, done=DONE, aired=frozenset({"k:p1", "k:p2", "k:d1"}))
        assert journal(heard, MORNING) == ["p3", "p4", "p5", "p9"]
        assert journal(heard, NOON) == ["d2", "p3", "p4", "p5", "p9"]
        assert journal(heard, EVENING) == ["d1", "d2", "p1", "p2", "p3", "p4", "p5", "p9"]

    def test_the_evening_never_repeats_what_this_session_already_said(self) -> None:
        """Earlier sessions of the day are gone over again; this one's are not."""
        desk = Desk(
            clock=CLOCK,
            day=DAY,
            aired=frozenset({"k:p1", "k:p2"}),
            heard_this_session=frozenset({"k:p2"}),
        )
        assert journal(desk, EVENING) == ["p1", "p3", "p4", "p5", "p9"]

    def test_a_day_of_weather_alone_is_no_journal(self) -> None:
        desk = Desk(clock=CLOCK, day=(WEATHER,))
        for edition in JournalEdition:
            assert journal(desk, edition) is None
            assert RadioFormat.JOURNAL not in available_formats(replace(desk, edition=edition))

    def test_what_was_done_alone_makes_a_noon_or_an_evening_never_a_morning(self) -> None:
        desk = Desk(clock=CLOCK, done=DONE)
        assert journal(desk, MORNING) is None
        assert journal(desk, NOON) == ["d1", "d2"]
        assert journal(desk, EVENING) == ["d1", "d2"]

    def test_the_week_ahead_alone_makes_an_evening_only(self) -> None:
        desk = Desk(clock=CLOCK, ahead=AHEAD)
        assert journal(desk, MORNING) is None and journal(desk, NOON) is None
        assert journal(desk, EVENING) == ["a1", "a2"]

    def test_the_desk_offers_the_journal_of_its_own_edition(self) -> None:
        desk = Desk(clock=CLOCK, ahead=AHEAD, edition=NOON)
        assert RadioFormat.JOURNAL not in available_formats(desk)
        assert RadioFormat.JOURNAL in available_formats(replace(desk, edition=EVENING))


def test_news_formats_speak_their_shortlist_and_an_analysis_its_story() -> None:
    analysis_point = RadioFact(
        id="a1",
        kind=FactKind.ANALYSIS,
        text="context: why it matters",
        key="n:1#a1",
        sensitivity=Sensitivity.PUBLIC,
    )
    desk = Desk(
        clock=CLOCK,
        news={RadioFormat.BULLETIN: (news("n1"), news("n2")), RadioFormat.ANALYSIS: (news("n7"),)},
    )
    assert ids(RadioFormat.BULLETIN, desk) == ["n1", "n2"]
    assert pack_for(RadioFormat.ANALYSIS, desk) is None  # the analyst has not run yet
    with_points = Desk(clock=CLOCK, news=desk.news, analysis=(analysis_point,))
    assert ids(RadioFormat.ANALYSIS, with_points) == ["n7", "a1"]


def test_the_dossier_and_the_debate_read_the_article_first_the_discussion_its_story() -> None:
    point = RadioFact(
        id="a1",
        kind=FactKind.ANALYSIS,
        text="history: how it began",
        key="n:1#a1",
        sensitivity=Sensitivity.PUBLIC,
    )
    news_desk = {
        RadioFormat.DOSSIER: (news("n3"),),
        RadioFormat.DEBATE: (news("n4"),),
        RadioFormat.DISCUSSION: (news("n5"), news("n6")),
    }
    desk = Desk(clock=CLOCK, news=news_desk)
    assert pack_for(RadioFormat.DOSSIER, desk) is None  # the analyst has not run yet
    assert pack_for(RadioFormat.DEBATE, desk) is None
    assert ids(RadioFormat.DISCUSSION, desk) == ["n5", "n6"]
    read = Desk(clock=CLOCK, news=news_desk, analysis=(point,))
    assert ids(RadioFormat.DOSSIER, read) == ["n3", "a1"]
    assert ids(RadioFormat.DEBATE, read) == ["n4", "a1"]
    # Judged on their story alone: the analyst is paid for once the grid chose one.
    assert {RadioFormat.DOSSIER, RadioFormat.DEBATE, RadioFormat.DISCUSSION} <= available_formats(
        desk
    )


def test_available_formats_is_what_has_something_to_say() -> None:
    desk = Desk(clock=CLOCK, day=DAY, news={RadioFormat.ANALYSIS: (news("n7"),)})
    available = available_formats(desk)
    assert RadioFormat.ANALYSIS in available  # judged on its story
    assert RadioFormat.BULLETIN not in available  # no shortlist
    assert {RadioFormat.OPENING, RadioFormat.SIGN_OFF, RadioFormat.JOURNAL} <= available


class TestNothingNew:
    """ADR-324 decision 38: « nothing new » is said from a fact, never invented."""

    def test_an_exhausted_desk_offers_the_station_s_word_and_its_fact(self) -> None:
        desk = Desk(clock=CLOCK, day=DAY, news_exhausted=True)
        pack = pack_for(RadioFormat.NOTHING_NEW, desk)
        assert pack is not None
        [fact] = pack.facts
        assert fact.kind is FactKind.NEWSROOM and fact.sensitivity is Sensitivity.PUBLIC
        assert RadioFormat.NOTHING_NEW in available_formats(desk)

    def test_a_desk_with_news_left_has_nothing_to_say_about_it(self) -> None:
        desk = Desk(clock=CLOCK, day=DAY)
        assert pack_for(RadioFormat.NOTHING_NEW, desk) is None
        assert RadioFormat.NOTHING_NEW not in available_formats(desk)
