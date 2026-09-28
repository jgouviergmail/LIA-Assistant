"""The antenna: what it gives each segment, what it remembers, what it survives."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import TypeVar
from uuid import UUID, uuid4

import numpy as np
import pytest
from prometheus_client import REGISTRY

from src.domains.radio import antenna as antenna_module
from src.domains.radio.aired import RedisAiredLedger
from src.domains.radio.antenna import (
    AiredLedger,
    Antenna,
    AntennaCrew,
    AntennaSetup,
)
from src.domains.radio.cast import Cast
from src.domains.radio.delivery import StylePhrases
from src.domains.radio.editorial import NewsCandidate, Subjects
from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, clock_fact
from src.domains.radio.flash import FLASH_SEQ_BASE, FlashNote
from src.domains.radio.formats import JournalEdition, RadioFormat, RadioRole
from src.domains.radio.meanings import Vector
from src.domains.radio.news_desk import read_news_desk
from src.domains.radio.personal import PersonalFacts
from src.domains.radio.production import (
    NothingAired,
    ProducedSegment,
    ProductionLimits,
    ProductionOutcome,
    ProductionResult,
    VoicedLine,
    VoiceEngine,
    WritingRequest,
)
from src.domains.radio.programme import Slot
from src.domains.radio.prompting import ON_AIR_SHOWN_MAX, AnalysisRequest
from src.domains.radio.script import ScriptDraft
from src.domains.radio.verification import VerifiedLine
from tests.unit.domains.radio.fakes import FakeRedis

pytestmark = pytest.mark.unit

T = TypeVar("T")

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)
#: 19:00 on the listener's clock: the journal's evening edition.
EVENING = datetime(2026, 9, 26, 17, 0, tzinfo=UTC)
LOCAL = timezone(timedelta(hours=2))
USER = UUID("00000000-0000-4000-8000-0000000000aa")


def story(
    key: str, outlet: str, fingerprint: str, *, text: str | None = None, age_min: int = 60
) -> NewsCandidate:
    return NewsCandidate(
        key=key,
        outlet=outlet,
        url=f"https://{outlet.lower()}.example/{key}",
        title=f"Headline {fingerprint}",
        summary=f"Summary of {fingerprint}.",
        published_at=NOW - timedelta(minutes=age_min),
        fingerprint=fingerprint,
        full_text=text,
    )


def title_of(key: str) -> str:
    """The headline of a story of the desk, by its key."""
    return next(candidate.title for candidate in STORIES if candidate.key == key)


STORIES = [
    # The freshest story, told by two outlets: it airs first, and once.
    story("a1", "Alpha", "rain", text="The whole article about the rain. " * 20, age_min=10),
    story("b1", "Beta", "rain", age_min=10),
    story("a2", "Alpha", "vote"),
    story("b2", "Beta", "bridge"),
    story("c1", "Gamma", "fire"),
    story("c2", "Gamma", "market"),
    story("a3", "Alpha", "storm"),
    story("b3", "Beta", "harvest"),
]
DAY = (
    RadioFact(
        id="p1",
        kind=FactKind.EVENT,
        text="Dentist at 10:30.",
        key="event:dentist",
        sensitivity=Sensitivity.PERSONAL,
    ),
    RadioFact(
        id="p2",
        kind=FactKind.WEATHER,
        text="Sunny, 21 °C.",
        key="weather:here",
        sensitivity=Sensitivity.PUBLIC,
    ),
)


class Sources:
    """The day and the news, counted — and able to fail."""

    def __init__(self, *, day_fails: bool = False) -> None:
        self.day_reads = 0
        self.news_reads = 0
        self.day_fails = day_fails

    async def day(self) -> PersonalFacts:
        self.day_reads += 1
        if self.day_fails:
            raise ConnectionError("briefing down")
        return PersonalFacts(day=DAY)

    async def candidates(
        self, *, heard_keys: frozenset[str], heard_stories: frozenset[str]
    ) -> list[NewsCandidate]:
        self.news_reads += 1
        return list(STORIES)


class Meanings:
    """The shared headline vectors, standing in: « rain », « storm » and « tempest » tell
    ONE event, every other headline its own — asked for counted, and able to fail."""

    def __init__(self, *, fails: bool = False) -> None:
        self.asked: list[list[str]] = []
        self.fails = fails

    async def vectors(self, titles: Sequence[str]) -> dict[str, Vector]:
        self.asked.append(list(titles))
        await asyncio.sleep(0.01)  # a provider takes a moment: another desk may start
        if self.fails:
            raise ConnectionError("embeddings down")
        one = {"Headline rain": "Headline storm", "Headline tempest": "Headline storm"}
        axes = sorted({"Headline storm", *(c.title for c in STORIES)} - set(one))
        return {
            title: np.array(
                [1.0 if axis == one.get(title, title) else 0.0 for axis in axes],
                dtype=np.float32,
            )
            for title in titles
        }


class SlowSources(Sources):
    """Sources that take a moment to answer, as a database does."""

    async def day(self) -> PersonalFacts:
        await asyncio.sleep(0.01)
        return await super().day()


class Analyst:
    def __init__(self, points: int) -> None:
        self.points = points
        self.read: list[AnalysisRequest] = []

    async def analyse(
        self, request: AnalysisRequest, *, story_key: str, min_points: int, max_points: int
    ) -> tuple[RadioFact, ...]:
        self.read.append(request)
        return tuple(
            RadioFact(
                id=f"a{n}",
                kind=FactKind.ANALYSIS,
                text=f"context: point {n}.",
                key=f"{story_key}#a{n}",
                sensitivity=Sensitivity.PUBLIC,
            )
            for n in range(1, self.points + 1)
        )


class Studio:
    """Stands for ``produce_segment``: records what it was asked, answers « produced »
    having told the FIRST story of its pack, as a one-story programme does."""

    def __init__(
        self,
        *,
        tells: FactKind = FactKind.NEWS,
        also: frozenset[FactKind] = frozenset(),
        tells_many: int = 1,
    ) -> None:
        self.requests: list[WritingRequest] = []
        self.checkers: list[object] = []
        self.tells = tells
        self.also = also
        self.tells_many = tells_many
        self.fail_next = 0

    async def __call__(
        self, request: WritingRequest, out: Path, **kwargs: object
    ) -> ProductionResult:
        self.requests.append(request)
        self.checkers.append(kwargs["checker"])
        if self.fail_next:
            self.fail_next -= 1
            return ProductionResult(ProductionOutcome.CHECK_FAILED)
        told = [fact.id for fact in request.pack.facts if fact.kind is self.tells]
        told = told[: self.tells_many]
        told += [fact.id for fact in request.pack.facts if fact.kind in self.also]
        return ProductionResult(
            ProductionOutcome.PRODUCED,
            segment=ProducedSegment(
                title=request.format.value,
                audio_path=out,
                duration_s=20.0,
                transcript=(),
                dropped_lines=0,
                unrendered=(),
            ),
            # One line per fact told, five seconds apart.
            lines=tuple(VoicedLine(offset_s=5.0 * n, refs=(fid,)) for n, fid in enumerate(told)),
        )


class NoTts:
    def record_tts_call(
        self,
        provider: str,
        model: str,
        characters: int,
        duration_ms: float = 0.0,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        raise AssertionError("the studio stands in for every voice")


class NoWriter:
    async def write(self, request: WritingRequest) -> ScriptDraft | None:
        raise AssertionError("the studio stands in for the writer")


class Checker:
    async def unsupported(
        self, lines: Sequence[VerifiedLine], pack: FactPack
    ) -> frozenset[int] | None:
        raise AssertionError("the studio stands in for the verifier")


class SilentClient:
    """A voice engine's client the studio never calls."""

    provider_name = "edge"
    audio_format = "mp3"

    async def synthesize(self, text: str, voice_name: str | None = None, **kwargs: object) -> bytes:
        raise AssertionError("the studio stands in for every voice")

    async def synthesize_base64(
        self, text: str, voice_name: str | None = None, **kwargs: object
    ) -> str:
        raise AssertionError("the studio stands in for every voice")

    async def close(self) -> None:
        return None


class BrokenLedger:
    async def heard(self) -> tuple[frozenset[str], frozenset[str]]:
        raise ConnectionError("redis down")

    async def treated(self) -> dict[RadioFormat, Subjects]:
        raise ConnectionError("redis down")

    async def headlines(self) -> tuple[str, ...]:
        raise ConnectionError("redis down")

    async def record(
        self,
        *,
        personal: frozenset[str],
        news: frozenset[str],
        stories: frozenset[str],
        headlines: Sequence[str] = (),
    ) -> None:
        raise ConnectionError("redis down")


CHECKER = Checker()
ENGINE = VoiceEngine(
    client=SilentClient(),
    model="edge",
    phrases=StylePhrases(roles={}, qualities={}, template="{role}", template_plain="{role}"),
)


@pytest.fixture
def studio(monkeypatch: pytest.MonkeyPatch) -> Studio:
    fake = Studio()
    monkeypatch.setattr(antenna_module, "produce_segment", fake)
    return fake


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def antenna(
    tmp_path: Path,
    *,
    sources: Sources | None = None,
    ledger: AiredLedger | None = None,
    analyst: Analyst | None = None,
    clock: Clock | None = None,
    meanings: Meanings | None = None,
    same_event_similarity: float = 0.0,
    cast: Cast | None = None,
) -> Antenna:
    sources = sources or Sources()
    return Antenna(
        setup=AntennaSetup(
            session_id=uuid4(),
            media_root=tmp_path,
            timezone=LOCAL,
            language="en",
            station_name="LIA Radio",
            listener_name="Alex",
            checked=frozenset({RadioFormat.BRIEF}),
            analysis_min_points=2,
            analysis_max_points=4,
            desk_ttl_s=60,
            same_event_similarity=same_event_similarity,
            limits=ProductionLimits(
                quote_max_chars=120,
                tts_concurrency=2,
                mix_timeout_s=30,
                tts_attempts=2,
                tts_rate_limit_wait_max_s=30.0,
            ),
        ),
        crew=AntennaCrew(
            writer=NoWriter(),
            analyst=analyst or Analyst(points=3),
            checker=CHECKER,
            engine=ENGINE,
            cast=cast or Cast(voices=dict.fromkeys(RadioRole, "voice")),
            tts_ledger=NoTts(),
        ),
        day=sources,
        news=sources,
        aired=ledger
        or RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock()),
        headlines=meanings or Meanings(fails=True),
        clock=clock or Clock(),
    )


def slot(
    fmt: RadioFormat, seq: int = 1, *, mark: datetime | None = None, at: datetime = NOW
) -> Slot:
    return Slot(seq=seq, format=fmt, station_id=False, air_at=at, duration_s=30.0, clock_mark=mark)


def said(request: WritingRequest) -> list[str]:
    return [fact.key for fact in request.pack.facts if fact.kind is FactKind.NEWS]


async def hear(ledger: RedisAiredLedger, produced: ProducedSegment | NothingAired | None) -> None:
    """The listener heard the whole segment: what the loop files once the player passed it."""
    assert isinstance(produced, ProducedSegment)
    await ledger.remember(produced.memory)


def first_told(request: WritingRequest) -> str:
    """The story a one-story programme told: the studio tells the first of its pack."""
    return next(fact.key for fact in request.pack.facts if fact.kind is FactKind.NEWS)


def told_in(request: WritingRequest) -> dict[str, bool]:
    """The news facts a request carries, each with whether it comes back to a story heard."""
    return {fact.key: fact.returning for fact in request.pack.facts if fact.kind is FactKind.NEWS}


class TestAngles:
    """ADR-324 decision 39: an angle may come back to a story heard — never the story of the
    programme just before, never one the same programme already took."""

    async def test_it_may_come_back_to_a_story_heard_and_is_told_it_does(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        await ledger.record(
            personal=frozenset(), news=frozenset({"b1"}), stories=frozenset({"rain"})
        )
        radio = antenna(tmp_path, ledger=ledger)
        await radio.produce(slot(RadioFormat.COLUMN), previous=None, following=None)
        facts = told_in(studio.requests[0])
        assert facts["b1"] is True and facts["c2"] is False
        await radio.produce(slot(RadioFormat.BRIEF, 2), previous=None, following=None)
        assert not {"a1", "b1"} & set(told_in(studio.requests[1]))  # a brief renews its stories

    async def test_never_the_story_the_programme_just_before_told(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        radio = antenna(tmp_path)
        await radio.produce(slot(RadioFormat.BRIEF, 1), previous=None, following=None)
        before = first_told(studio.requests[0])
        await radio.produce(
            slot(RadioFormat.DISCUSSION, 2), previous=RadioFormat.BRIEF, following=None
        )
        assert before not in told_in(studio.requests[1])
        await radio.produce(slot(RadioFormat.COLUMN, 4), previous=None, following=None)
        assert before in told_in(studio.requests[2])  # two programmes later, it may

    async def test_a_news_flash_between_two_programmes_is_not_the_programme_before(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        # A flash interrupts and tells what LIA wrote: its place, numbered apart, must
        # not push the programme before out of the antenna's memory.
        radio = antenna(tmp_path)
        await radio.produce(slot(RadioFormat.BRIEF, 1), previous=None, following=None)
        before = first_told(studio.requests[0])
        assert await radio.produce_flash([NOTE_M1], seq=FLASH_SEQ_BASE + 1, cuts=None, resumes=None)
        await radio.produce(
            slot(RadioFormat.DISCUSSION, 2), previous=RadioFormat.BRIEF, following=None
        )
        assert before not in told_in(studio.requests[-1])

    async def test_never_a_story_the_same_programme_already_took(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        column = await antenna(tmp_path, ledger=ledger).produce(
            slot(RadioFormat.COLUMN), previous=None, following=None
        )
        await hear(ledger, column)
        took = first_told(studio.requests[0])
        radio = antenna(tmp_path, ledger=ledger)
        await radio.produce(slot(RadioFormat.COLUMN, 3), previous=None, following=None)
        assert took not in told_in(studio.requests[1])
        await radio.produce(slot(RadioFormat.DISCUSSION, 5), previous=None, following=None)
        assert told_in(studio.requests[2]).get(took) is True  # another angle comes back to it

    async def test_what_an_angle_tells_is_filed_as_taken_by_it_a_fresh_one_as_heard(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        radio = antenna(tmp_path)
        column = await radio.produce(slot(RadioFormat.COLUMN), previous=None, following=None)
        brief = await radio.produce(slot(RadioFormat.BRIEF, 2), previous=None, following=None)
        assert isinstance(column, ProducedSegment) and isinstance(brief, ProducedSegment)
        assert {line.angle for line in column.memory} == {RadioFormat.COLUMN}
        assert {line.angle for line in brief.memory} == {None}

    async def test_a_debate_speaks_with_the_voices_it_has_and_reads_the_article_first(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        analyst = Analyst(points=3)
        voices = {role: role.value for role in RadioRole}
        voices[RadioRole.SPEAKER_C] = voices[RadioRole.HOST]  # only LIA's voice was left
        radio = antenna(tmp_path, analyst=analyst, cast=Cast(voices=voices))
        await radio.produce(slot(RadioFormat.DEBATE), previous=None, following=None)
        [request] = studio.requests
        assert request.roles == (RadioRole.ANCHOR, RadioRole.SPEAKER_A, RadioRole.SPEAKER_B)
        assert len(analyst.read) == 1
        assert [fact.kind for fact in request.pack.facts].count(FactKind.ANALYSIS) == 3


class TestSourcesAndInterests:
    """ADR-324 decision 40: a news programme draws from the sources OR from what a search
    found for the listener's interests; when both have material, one programme of a
    format after the other."""

    INTERESTS = [
        replace(story("i1", "Delta", "comet", age_min=5), from_interests=True),
        replace(story("i2", "Epsilon", "chess", age_min=15), from_interests=True),
        replace(story("i3", "Zeta", "violin", age_min=25), from_interests=True),
    ]

    def read(
        self,
        candidates: list[NewsCandidate],
        interests_first: frozenset[RadioFormat] = frozenset(),
    ) -> dict[RadioFormat, list[NewsCandidate]]:
        return read_news_desk(
            candidates,
            keys=frozenset(),
            stories=frozenset(),
            headlines=(),
            vectors=None,
            threshold=0.9,
            now=NOW,
            excluded={},
            interests_first=interests_first,
        ).shortlists

    def test_the_sources_first_and_the_interests_on_their_turn(self) -> None:
        both = [*STORIES, *self.INTERESTS]
        default = self.read(both)
        assert default[RadioFormat.BRIEF]
        assert not any(c.from_interests for c in default[RadioFormat.BRIEF])
        turn = self.read(both, interests_first=frozenset({RadioFormat.BRIEF}))
        assert [c.key for c in turn[RadioFormat.BRIEF]] == ["i1", "i2", "i3"]
        assert not any(c.from_interests for c in turn[RadioFormat.BULLETIN])  # its own turn

    def test_a_turn_with_nothing_takes_the_other_material(self) -> None:
        assert [c.key for c in self.read(self.INTERESTS)[RadioFormat.BRIEF]] == ["i1", "i2", "i3"]
        sources_only = self.read(STORIES, interests_first=frozenset({RadioFormat.BRIEF}))
        assert sources_only[RadioFormat.BRIEF]
        assert not any(c.from_interests for c in sources_only[RadioFormat.BRIEF])

    async def test_one_programme_of_a_format_after_the_other(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        interests = self.INTERESTS

        class Both(Sources):
            async def candidates(self, **_: frozenset[str]) -> list[NewsCandidate]:
                return [*STORIES, *interests]

        radio = antenna(tmp_path, sources=Both())
        for seq in (1, 3, 5):
            await radio.produce(slot(RadioFormat.BRIEF, seq), previous=None, following=None)
        found = {candidate.key for candidate in interests}
        drew = [{key in found for key in told_in(request)} for request in studio.requests]
        assert drew == [{False}, {True}, {False}]

    async def test_a_programme_that_did_not_air_keeps_its_turn(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        interests = self.INTERESTS

        class Both(Sources):
            async def candidates(self, **_: frozenset[str]) -> list[NewsCandidate]:
                return [*STORIES, *interests]

        studio.fail_next = 2
        radio = antenna(tmp_path, sources=Both())
        await radio.produce(slot(RadioFormat.BRIEF, 1), previous=None, following=None)
        await radio.produce(slot(RadioFormat.BRIEF, 3), previous=None, following=None)
        found = {candidate.key for candidate in interests}
        drew = [{key in found for key in told_in(request)} for request in studio.requests]
        assert drew == [{False}, {False}]  # the sources' turn stands until one airs


class TestTheDeskOfEveryLanguage:
    """Every language fills the newsroom (ADR-324 decision 38): the desk asks for the
    stories never heard first, and reads its shortlists off the event loop."""

    async def test_the_newsroom_is_asked_for_what_was_never_heard_first(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        class Asked(Sources):
            def __init__(self) -> None:
                super().__init__()
                self.asked: list[tuple[frozenset[str], frozenset[str]]] = []

            async def candidates(
                self, *, heard_keys: frozenset[str], heard_stories: frozenset[str]
            ) -> list[NewsCandidate]:
                self.asked.append((heard_keys, heard_stories))
                return list(STORIES)

        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        await ledger.record(
            personal=frozenset({"event:dentist"}),
            news=frozenset({"a2"}),
            stories=frozenset({"vote"}),
            headlines=["Headline vote"],
        )
        sources = Asked()
        await antenna(tmp_path, sources=sources, ledger=ledger).available()
        [(keys, prints)] = sources.asked
        assert "a2" in keys and prints == frozenset({"vote"})

    async def test_the_desk_is_read_off_the_event_loop(
        self, tmp_path: Path, studio: Studio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Its meanings are a matrix product and its shortlists read hundreds of stories."""
        offloaded: list[str] = []
        run_in_thread = asyncio.to_thread

        async def spy(function: Callable[..., T], /, *args: object, **kwargs: object) -> T:
            offloaded.append(function.__name__)
            return await run_in_thread(function, *args, **kwargs)

        monkeypatch.setattr(antenna_module.asyncio, "to_thread", spy)
        radio = antenna(tmp_path, meanings=Meanings(), same_event_similarity=0.9)
        await radio.produce(slot(RadioFormat.HEADLINES), previous=None, following=None)
        assert "read_news_desk" in offloaded
        assert set(said(studio.requests[0])) >= {"b1", "a2"}  # the rain once, then the vote


class TestSameEvent:
    """Another article of an event heard is no news (ADR-324 decision 34)."""

    async def test_a_story_heard_is_not_offered_again_in_other_words(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        await ledger.record(
            personal=frozenset(),
            news=frozenset({"yesterday"}),
            stories=frozenset(),
            headlines=["Headline tempest"],  # no story of the desk any more
        )
        radio = antenna(tmp_path, ledger=ledger, meanings=Meanings(), same_event_similarity=0.9)
        await radio.produce(slot(RadioFormat.HEADLINES), previous=None, following=None)
        [request] = studio.requests
        # The rain and the storm tell the event heard: neither is news any more.
        assert not {"a1", "b1", "a3"} & set(said(request)) and "a2" in said(request)

    async def test_two_articles_of_one_event_are_one_story(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        radio = antenna(tmp_path, meanings=Meanings(), same_event_similarity=0.9)
        await radio.produce(slot(RadioFormat.HEADLINES), previous=None, following=None)
        [request] = studio.requests
        assert "b1" in said(request) and "a3" not in said(request)  # the rain, not the storm

    async def test_two_desks_read_at_once_ask_once(self, tmp_path: Path, studio: Studio) -> None:
        """The start produces two slots together: their desks must not buy one reading twice."""
        meanings = Meanings()
        radio = antenna(tmp_path, meanings=meanings, same_event_similarity=0.9)
        await asyncio.gather(radio.available(), radio.available())
        assert len(meanings.asked) == 1

    async def test_a_headline_is_read_once_a_session(self, tmp_path: Path, studio: Studio) -> None:
        meanings = Meanings()
        radio = antenna(tmp_path, meanings=meanings, same_event_similarity=0.9)
        await radio.produce(slot(RadioFormat.HEADLINES), previous=None, following=None)
        await radio.produce(slot(RadioFormat.HEADLINES, 2), previous=None, following=None)
        assert meanings.asked == [sorted({c.title for c in STORIES})]

    async def test_a_blind_reading_leaves_the_words_to_judge_until_the_desk_is_read_again(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        meanings, clock = Meanings(fails=True), Clock()
        radio = antenna(tmp_path, meanings=meanings, same_event_similarity=0.9, clock=clock)
        assert await radio.produce(slot(RadioFormat.HEADLINES), previous=None, following=None)
        assert {"b1", "a3"} <= set(said(studio.requests[0]))  # the words alone: two stories
        clock.now += timedelta(seconds=30)
        await radio.produce(slot(RadioFormat.HEADLINES, 2), previous=None, following=None)
        assert len(meanings.asked) == 1
        clock.now += timedelta(seconds=60)
        await radio.produce(slot(RadioFormat.HEADLINES, 3), previous=None, following=None)
        assert len(meanings.asked) == 2

    async def test_no_threshold_reads_no_meaning(self, tmp_path: Path, studio: Studio) -> None:
        meanings = Meanings()
        radio = antenna(tmp_path, meanings=meanings, same_event_similarity=0.0)
        await radio.produce(slot(RadioFormat.HEADLINES), previous=None, following=None)
        assert meanings.asked == [] and "a3" in said(studio.requests[0])


class TestHeardIsWhatAired:
    """The ledger across sessions holds what the listener HEARD, never what was only
    produced (ADR-324 decision 35). Measured on dev 2026-09-27: a session stopped after its
    opening had filed the four news programmes produced ahead of it — over twenty sessions,
    at least four news programmes in ten filed as heard had never aired."""

    async def test_producing_a_segment_files_nothing(self, tmp_path: Path, studio: Studio) -> None:
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        radio = antenna(tmp_path, ledger=ledger)
        assert await radio.produce(slot(RadioFormat.HEADLINES), previous=None, following=None)
        assert await radio.produce_flash([NOTE_M1], seq=100_001, cuts=None, resumes=None)
        assert await ledger.heard() == (frozenset(), frozenset())
        assert await ledger.headlines() == ()

    async def test_a_news_programme_remembers_line_by_line_the_stories_it_tells(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        studio = Studio(tells_many=2)
        monkeypatch.setattr(antenna_module, "produce_segment", studio)
        produced = await antenna(tmp_path).produce(
            slot(RadioFormat.HEADLINES), previous=None, following=None
        )
        assert isinstance(produced, ProducedSegment)
        stories = {candidate.key: candidate for candidate in STORIES}
        first, second = (stories[key] for key in said(studio.requests[0])[:2])
        assert [
            (line.offset_s, line.personal, line.news, line.stories, line.headlines)
            for line in produced.memory
        ] == [
            (0.0, frozenset(), {first.key}, {first.fingerprint}, (first.title,)),
            (5.0, frozenset(), {second.key}, {second.fingerprint}, (second.title,)),
        ]

    async def test_a_line_of_the_listeners_day_remembers_its_record_and_no_headline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        studio = Studio(tells=FactKind.EVENT)
        monkeypatch.setattr(antenna_module, "produce_segment", studio)
        produced = await antenna(tmp_path).produce(
            slot(RadioFormat.JOURNAL), previous=None, following=None
        )
        assert isinstance(produced, ProducedSegment)
        [line] = produced.memory
        assert line.personal == {"event:dentist"}
        assert not (line.news or line.stories or line.headlines)

    async def test_the_first_line_of_an_analysis_remembers_the_story_it_analyses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An analysis that aired told its story, cited or not: from its first point on."""
        studio = Studio(tells=FactKind.ANALYSIS, tells_many=2)
        monkeypatch.setattr(antenna_module, "produce_segment", studio)
        produced = await antenna(tmp_path).produce(
            slot(RadioFormat.ANALYSIS), previous=None, following=None
        )
        assert isinstance(produced, ProducedSegment)
        first, second = produced.memory
        [story_key] = said(studio.requests[0])
        assert story_key in first.news and first.stories == {"rain"}
        assert first.headlines == (title_of(story_key),)
        assert story_key not in second.news and not (second.stories or second.headlines)

    async def test_a_flash_remembers_the_notes_it_tells(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        studio.tells, studio.tells_many = FactKind.NOTIFICATION, 2
        produced = await antenna(tmp_path).produce_flash(
            [NOTE_M1, NOTE_M2], seq=100_001, cuts=None, resumes=None
        )
        assert isinstance(produced, ProducedSegment)
        assert [line.personal for line in produced.memory] == [
            {"notification:m1"},
            {"notification:m2"},
        ]

    async def test_what_was_heard_is_remembered_by_the_next_session(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        produced = await antenna(tmp_path, ledger=ledger).produce(
            slot(RadioFormat.BRIEF), previous=None, following=None
        )
        told = said(studio.requests[0])[0]
        await antenna(tmp_path, ledger=ledger).produce(
            slot(RadioFormat.BRIEF), previous=None, following=None
        )
        assert told in said(studio.requests[1])  # produced, never heard: news again
        await hear(ledger, produced)
        await antenna(tmp_path, ledger=ledger).produce(
            slot(RadioFormat.BRIEF), previous=None, following=None
        )
        assert told not in said(studio.requests[2])


class TestNeverTwice:
    async def test_a_story_aired_is_offered_neither_again_nor_by_another_outlet(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        radio = antenna(tmp_path)
        assert await radio.produce(slot(RadioFormat.BRIEF), previous=None, following=None)
        first = said(studio.requests[0])
        rain = {"a1", "b1"}
        assert len(rain & set(first)) == 1  # the freshest story, told once
        assert await radio.produce(slot(RadioFormat.BRIEF, 2), previous=None, following=None)
        second = said(studio.requests[1])
        assert not rain & set(second)  # heard from one outlet, it is not news from the other

    async def test_a_story_left_untold_stays_on_the_desk(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """A brief tells one story of the three it is offered: the other two were never heard."""
        radio = antenna(tmp_path)
        await radio.produce(slot(RadioFormat.BRIEF), previous=None, following=None)
        told, *untold = said(studio.requests[0])
        assert untold
        await radio.produce(slot(RadioFormat.BRIEF, 2), previous=None, following=None)
        second = said(studio.requests[1])
        assert told not in second
        assert set(untold) <= set(second)

    async def test_the_stories_heard_are_shown_to_the_next_news_writer_only(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """Their HEADLINES, not the programme's title: a bulletin's title names one or two
        of its six stories, and the headlines that followed told another of them again
        from a second article (measured on dev 2026-09-27). A title of the listener's day
        never reaches a prompt whose voices may not say it."""
        radio = antenna(tmp_path)
        await radio.produce(slot(RadioFormat.JOURNAL), previous=None, following=None)
        await radio.produce(slot(RadioFormat.BRIEF, 2), previous=None, following=None)
        await radio.produce(slot(RadioFormat.HEADLINES, 3), previous=None, following=None)
        assert [request.on_air for request in studio.requests] == [(), (), ("Headline rain",)]

    async def test_every_story_a_programme_told_is_shown_once_in_the_order_it_aired(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        studio = Studio(tells_many=3)  # the headlines tell three of the stories offered
        monkeypatch.setattr(antenna_module, "produce_segment", studio)
        radio = antenna(tmp_path)
        await radio.produce(slot(RadioFormat.HEADLINES), previous=None, following=None)
        await radio.produce(slot(RadioFormat.BRIEF, 2), previous=None, following=None)
        told = said(studio.requests[0])[:3]
        headlines = studio.requests[1].on_air
        assert len(headlines) == len(set(headlines))  # one story, two outlets: shown once
        assert headlines == tuple(dict.fromkeys(title_of(key) for key in told))

    async def test_an_analysis_that_aired_told_its_story_even_uncited(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        studio = Studio(tells=FactKind.ANALYSIS)  # the anchor's line on the article was dropped
        monkeypatch.setattr(antenna_module, "produce_segment", studio)
        radio = antenna(tmp_path)
        assert await radio.produce(slot(RadioFormat.ANALYSIS), previous=None, following=None)
        rain = {"a1", "b1"}  # the one story with a full text, told by two outlets
        assert set(said(studio.requests[0])) <= rain
        await radio.produce(slot(RadioFormat.BRIEF, 2), previous=None, following=None)
        assert not rain & set(said(studio.requests[1]))

    async def test_the_next_session_of_the_day_remembers(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        brief = await antenna(tmp_path, ledger=ledger).produce(
            slot(RadioFormat.BRIEF), previous=None, following=None
        )
        await hear(ledger, brief)
        told = said(studio.requests[0])[0]
        await antenna(tmp_path, ledger=ledger).produce(
            slot(RadioFormat.HEADLINES), previous=None, following=None
        )
        assert told not in said(studio.requests[1])

    async def test_the_next_session_is_shown_the_stories_heard_before(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """An event told in one session came back in the next from another article
        (measured on dev 2026-09-27): what was heard is shown across launches too."""
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        brief = await antenna(tmp_path, ledger=ledger).produce(
            slot(RadioFormat.BRIEF), previous=None, following=None
        )
        await hear(ledger, brief)
        await antenna(tmp_path, ledger=ledger).produce(
            slot(RadioFormat.HEADLINES), previous=None, following=None
        )
        assert studio.requests[1].on_air == ("Headline rain",)

    async def test_a_long_history_shows_the_most_recent_headlines(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        redis, clock = FakeRedis(), Clock()
        ledger = RedisAiredLedger(redis, user_id=USER, personal_ttl_s=86400, clock=clock)
        earlier = tuple(f"Earlier story {n}" for n in range(ON_AIR_SHOWN_MAX + 10))
        await ledger.record(
            personal=frozenset(), news=frozenset(), stories=frozenset(), headlines=earlier
        )
        await antenna(tmp_path, ledger=ledger, clock=clock).produce(
            slot(RadioFormat.BRIEF), previous=None, following=None
        )
        assert studio.requests[0].on_air == earlier[-ON_AIR_SHOWN_MAX:]

    async def test_another_article_of_a_story_heard_is_not_offered_the_next_session(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """Measured on dev 2026-09-27: the second article of a mass came back in the next
        session as the figure of the day — another key, another fingerprint, the same
        headline but for two words."""

        class TwoArticles(Sources):
            async def candidates(self, **_: frozenset[str]) -> list[NewsCandidate]:
                first = story("m1", "Alpha", "mass one", age_min=5)
                second = story("m2", "Alpha", "mass two", age_min=20)
                return [
                    replace(first, title="Near 600 000 faithful expected at the huge Paris mass"),
                    replace(second, title="Near 600 000 faithful expected at the Paris mass"),
                    *STORIES[2:],
                ]

        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        brief = await antenna(tmp_path, sources=TwoArticles(), ledger=ledger).produce(
            slot(RadioFormat.BRIEF), previous=None, following=None
        )
        await hear(ledger, brief)
        assert said(studio.requests[0])[0] == "m1"  # the freshest, told
        await antenna(tmp_path, sources=TwoArticles(), ledger=ledger).produce(
            slot(RadioFormat.HEADLINES), previous=None, following=None
        )
        assert "m2" not in said(studio.requests[1])

        # And within one session, whatever the ledger says.
        radio = antenna(tmp_path, sources=TwoArticles(), ledger=BrokenLedger())
        await radio.produce(slot(RadioFormat.BRIEF), previous=None, following=None)
        assert said(studio.requests[2])[0] == "m1"
        await radio.produce(slot(RadioFormat.HEADLINES, 2), previous=None, following=None)
        assert "m2" not in said(studio.requests[3])

    async def test_a_story_heard_last_night_is_not_offered_again_the_next_day(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """A column reads stories two days old: its story must be remembered as long
        (reported 2026-09-26: « on risque de réentendre les mêmes sujets »)."""
        clock = Clock()
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=clock)
        column = await antenna(tmp_path, ledger=ledger, clock=clock).produce(
            slot(RadioFormat.COLUMN), previous=None, following=None
        )
        await hear(ledger, column)
        told = said(studio.requests[0])[0]
        clock.now = NOW + timedelta(hours=30)  # the next evening: past a day, within two
        await antenna(tmp_path, ledger=ledger, clock=clock).produce(
            slot(RadioFormat.COLUMN), previous=None, following=None
        )
        offered = said(studio.requests[1])
        assert offered, "the next day still has stories to offer"
        assert told not in offered

    async def test_a_story_without_a_fingerprint_is_remembered_by_its_key_as_long(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """The key is the story's own memory when no fingerprint names it across outlets."""

        class Unprinted(Sources):
            async def candidates(self, **_: frozenset[str]) -> list[NewsCandidate]:
                self.news_reads += 1
                return [replace(item, fingerprint="") for item in STORIES]

        clock = Clock()
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=clock)
        column = await antenna(tmp_path, sources=Unprinted(), ledger=ledger, clock=clock).produce(
            slot(RadioFormat.COLUMN), previous=None, following=None
        )
        await hear(ledger, column)
        told = said(studio.requests[0])[0]
        clock.now = NOW + timedelta(hours=30)
        await antenna(tmp_path, sources=Unprinted(), ledger=ledger, clock=clock).produce(
            slot(RadioFormat.COLUMN), previous=None, following=None
        )
        assert told not in said(studio.requests[1])

    async def test_a_ledger_that_fails_costs_the_next_session_not_this_segment(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        radio = antenna(tmp_path, ledger=BrokenLedger())
        assert await radio.produce(slot(RadioFormat.BRIEF), previous=None, following=None)
        assert await radio.produce(slot(RadioFormat.BRIEF, 2), previous=None, following=None)
        assert said(studio.requests[0])[0] not in said(studio.requests[1])


class TestDesk:
    async def test_the_sources_are_read_once_per_desk_life(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        sources, clock = Sources(), Clock()
        radio = antenna(tmp_path, sources=sources, clock=clock)
        await radio.available()
        await radio.produce(slot(RadioFormat.BRIEF), previous=None, following=None)
        await radio.available()
        assert (sources.day_reads, sources.news_reads) == (1, 1)
        clock.now += timedelta(seconds=61)
        await radio.available()
        assert (sources.day_reads, sources.news_reads) == (2, 2)

    async def test_the_two_productions_of_the_start_share_one_reading(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        sources = SlowSources()
        radio = antenna(tmp_path, sources=sources)
        await asyncio.gather(
            radio.produce(slot(RadioFormat.OPENING), previous=None, following=None),
            radio.produce(slot(RadioFormat.JOURNAL, 2), previous=None, following=None),
        )
        assert (sources.day_reads, sources.news_reads) == (1, 1)

    async def test_a_blind_source_reads_as_nothing_to_say(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        available = await antenna(tmp_path, sources=Sources(day_fails=True)).available()
        assert RadioFormat.JOURNAL not in available
        assert RadioFormat.BRIEF in available
        assert RadioFormat.JOURNAL in await antenna(tmp_path).available()

    async def test_a_listener_who_heard_every_story_left_is_told_so_once(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """ADR-324 decision 38: the desk offers « nothing new » only when the newsroom
        holds stories and the listener heard every one — never while news is left."""
        radio = antenna(tmp_path)
        assert RadioFormat.NOTHING_NEW not in await radio.available()
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        await ledger.record(
            personal=frozenset(),
            news=frozenset(candidate.key for candidate in STORIES),
            stories=frozenset(),
        )
        heard_it_all = antenna(tmp_path, ledger=ledger)
        available = await heard_it_all.available()
        assert RadioFormat.NOTHING_NEW in available and RadioFormat.BRIEF not in available

    async def test_the_writer_is_told_the_clock_mark_in_local_time(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        mark = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
        await antenna(tmp_path).produce(
            slot(RadioFormat.BULLETIN, mark=mark), previous=None, following=None
        )
        [request] = studio.requests
        assert request.clock_mark == mark
        assert request.clock_mark is not None and request.clock_mark.hour == 10
        assert request.local_now.utcoffset() == timedelta(hours=2)


class TestDistinctData:
    """Every programme speaks of its own data: nothing the session said is said again."""

    async def test_only_the_opening_and_a_clock_mark_say_the_time(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        radio = antenna(tmp_path)
        mark = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
        await radio.produce(slot(RadioFormat.OPENING), previous=None, following=None)
        await radio.produce(slot(RadioFormat.JOURNAL, 2), previous=None, following=None)
        await radio.produce(slot(RadioFormat.BULLETIN, 3, mark=mark), previous=None, following=None)
        clocks = [
            [fact.text for fact in request.pack.facts if fact.kind is FactKind.CLOCK]
            for request in studio.requests
        ]
        assert clocks[0] == [clock_fact(NOW.astimezone(LOCAL)).text]
        assert clocks[1] == []
        assert clocks[2] == [clock_fact(mark.astimezone(LOCAL)).text]

    async def test_the_weather_said_once_is_not_given_again(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        studio = Studio(tells=FactKind.WEATHER)  # the opening says the weather
        monkeypatch.setattr(antenna_module, "produce_segment", studio)
        radio = antenna(tmp_path)
        await radio.produce(slot(RadioFormat.OPENING), previous=None, following=None)
        await radio.produce(slot(RadioFormat.JOURNAL, 2), previous=None, following=None)
        kinds = [fact.kind for fact in studio.requests[1].pack.facts]
        assert FactKind.WEATHER not in kinds and FactKind.EVENT in kinds

    async def test_the_weather_left_unsaid_is_still_given(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        radio = antenna(tmp_path)  # the opening's writer left the weather out
        await radio.produce(slot(RadioFormat.OPENING), previous=None, following=None)
        await radio.produce(slot(RadioFormat.JOURNAL, 2), previous=None, following=None)
        assert FactKind.WEATHER in [fact.kind for fact in studio.requests[1].pack.facts]

    async def test_the_two_productions_of_the_start_never_both_get_the_weather(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The start produces two slots at once, and both desks read what was said before
        either had aired: the weather reached the opening AND the listener's day, said twice
        in a row (found by the cold review, 2026-09-27)."""

        class InFlight(Studio):
            async def __call__(
                self, request: WritingRequest, out: Path, **kwargs: object
            ) -> ProductionResult:
                answer = await super().__call__(request, out, **kwargs)
                await asyncio.sleep(0.02)  # the writer, the voices, the mix
                return answer

        studio = InFlight(tells=FactKind.WEATHER)
        monkeypatch.setattr(antenna_module, "produce_segment", studio)
        radio = antenna(tmp_path)
        await asyncio.gather(
            radio.produce(slot(RadioFormat.OPENING), previous=None, following=None),
            radio.produce(slot(RadioFormat.JOURNAL, 2), previous=None, following=None),
        )
        offered = [
            any(fact.kind is FactKind.WEATHER for fact in request.pack.facts)
            for request in studio.requests
        ]
        assert sorted(offered) == [False, True]

    async def test_a_production_that_failed_gives_the_weather_back(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        radio = antenna(tmp_path)
        studio.fail_next = 1  # the opening never airs
        await radio.produce(slot(RadioFormat.OPENING), previous=None, following=None)
        await radio.produce(slot(RadioFormat.JOURNAL, 2), previous=None, following=None)
        assert FactKind.WEATHER in [fact.kind for fact in studio.requests[1].pack.facts]

    async def test_the_evening_edition_does_not_go_over_what_this_session_just_said(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        studio = Studio(tells=FactKind.EVENT)
        monkeypatch.setattr(antenna_module, "produce_segment", studio)
        radio = antenna(tmp_path)
        await radio.produce(slot(RadioFormat.JOURNAL), previous=None, following=None)
        assert await radio.produce(
            slot(RadioFormat.JOURNAL, 2, at=EVENING), previous=None, following=None
        ) == NothingAired("nothing_to_say")
        assert len(studio.requests) == 1  # the day's one event was already told

    async def test_the_evening_edition_goes_over_what_an_earlier_session_said(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        studio = Studio(tells=FactKind.EVENT)
        monkeypatch.setattr(antenna_module, "produce_segment", studio)
        ledger = RedisAiredLedger(FakeRedis(), user_id=USER, personal_ttl_s=86400, clock=Clock())
        await antenna(tmp_path, ledger=ledger).produce(
            slot(RadioFormat.JOURNAL), previous=None, following=None
        )
        later = antenna(tmp_path, ledger=ledger)
        assert await later.produce(
            slot(RadioFormat.JOURNAL, at=EVENING), previous=None, following=None
        )
        kinds = [fact.kind for fact in studio.requests[1].pack.facts]
        assert FactKind.EVENT in kinds

    async def test_the_day_sources_done_and_ahead_parts_reach_the_editions_that_tell_them(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """ADR-324 decision 41 (lot 4b): what the day source read as done and as ahead is
        handed to the desk — the evening tells both, the morning neither."""

        class Journal(Sources):
            async def day(self) -> PersonalFacts:
                self.day_reads += 1
                done = RadioFact(
                    id="p3",
                    kind=FactKind.TASK,
                    text="Task done.",
                    key="done:task:1",
                    sensitivity=Sensitivity.PERSONAL,
                )
                ahead = RadioFact(
                    id="p4",
                    kind=FactKind.EVENT,
                    text="Board on Tuesday.",
                    key="event:board",
                    sensitivity=Sensitivity.PERSONAL,
                )
                return PersonalFacts(day=DAY, done=(done,), ahead=(ahead,))

        radio = antenna(tmp_path, sources=Journal())
        await radio.produce(slot(RadioFormat.JOURNAL), previous=None, following=None)
        await radio.produce(slot(RadioFormat.JOURNAL, 2, at=EVENING), previous=None, following=None)
        morning, evening = (
            [fact.key for fact in request.pack.facts] for request in studio.requests
        )
        assert "done:task:1" not in morning and "event:board" not in morning
        assert evening[:1] == ["done:task:1"] and evening[-1] == "event:board"

    async def test_the_journals_edition_follows_the_programmes_air_time(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """ADR-324 decision 41: a journal produced ahead of the edition it airs in is
        written for THAT edition — the desk and the writer read one decision."""
        radio = antenna(tmp_path)
        await radio.produce(slot(RadioFormat.JOURNAL), previous=None, following=None)
        await radio.produce(slot(RadioFormat.JOURNAL, 2, at=EVENING), previous=None, following=None)
        assert [request.edition for request in studio.requests] == [
            JournalEdition.MORNING,
            JournalEdition.EVENING,
        ]
        news = await radio.produce(slot(RadioFormat.BRIEF, 3), previous=None, following=None)
        assert news is not None and studio.requests[-1].edition is None


class TestAnalysis:
    async def test_an_analysis_is_paid_once_a_session_whatever_fails_after_it(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        """Measured 2026-09-26: six analyses in twenty minutes, the same reading paid
        for each time a check or a voice failed after it."""
        analyst = Analyst(points=3)
        radio = antenna(tmp_path, analyst=analyst)
        studio.fail_next = 1
        assert (
            await radio.produce(slot(RadioFormat.ANALYSIS), previous=None, following=None) is None
        )
        assert await radio.produce(slot(RadioFormat.ANALYSIS, 2), previous=None, following=None)
        assert len(analyst.read) == 1
        assert [f.kind for f in studio.requests[1].pack.facts].count(FactKind.ANALYSIS) == 3

    async def test_a_reading_that_came_back_empty_is_asked_for_again(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        analyst = Analyst(points=0)
        radio = antenna(tmp_path, analyst=analyst)
        await radio.produce(slot(RadioFormat.ANALYSIS), previous=None, following=None)
        analyst.points = 3
        assert await radio.produce(slot(RadioFormat.ANALYSIS, 2), previous=None, following=None)
        assert len(analyst.read) == 2

    async def test_the_analyst_reads_the_freshest_story_with_a_text(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        analyst = Analyst(points=3)
        await antenna(tmp_path, analyst=analyst).produce(
            slot(RadioFormat.ANALYSIS), previous=None, following=None
        )
        [read] = analyst.read
        assert read.outlet == "Alpha" and read.article.startswith("The whole article")
        [request] = studio.requests
        kinds = [fact.kind for fact in request.pack.facts]
        assert kinds.count(FactKind.ANALYSIS) == 3 and kinds.count(FactKind.NEWS) == 1

    async def test_an_analysis_without_points_is_not_produced(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        radio = antenna(tmp_path, analyst=Analyst(points=0))
        produced = await radio.produce(slot(RadioFormat.ANALYSIS), previous=None, following=None)
        assert produced == NothingAired("nothing_to_say") and studio.requests == []


async def test_the_verifier_reads_only_the_formats_the_listener_chose(
    tmp_path: Path, studio: Studio
) -> None:
    radio = antenna(tmp_path)
    await radio.produce(slot(RadioFormat.BRIEF), previous=None, following=None)
    await radio.produce(slot(RadioFormat.OPENING, 2), previous=None, following=None)
    assert studio.checkers == [CHECKER, None]


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


class TestEveryProductionIsCounted:
    """How each segment went reaches the dashboard, in one place: the antenna."""

    async def test_an_aired_segment_counts_as_produced_and_its_duration_is_measured(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        produced = sample("radio_segments_total", format="brief", outcome="produced")
        timed = sample("radio_segment_production_seconds_count", format="brief")

        assert await antenna(tmp_path).produce(
            slot(RadioFormat.BRIEF), previous=None, following=None
        )

        assert sample("radio_segments_total", format="brief", outcome="produced") == produced + 1
        assert sample("radio_segment_production_seconds_count", format="brief") == timed + 1

    async def test_a_format_with_nothing_to_say_is_counted_and_never_timed(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        silent = sample("radio_segments_total", format="analysis", outcome="nothing_to_say")
        timed = sample("radio_segment_production_seconds_count", format="analysis")
        radio = antenna(tmp_path, analyst=Analyst(points=0))

        produced = await radio.produce(slot(RadioFormat.ANALYSIS), previous=None, following=None)
        # Falsy like a failure's None: « assert await produce(...) » still means « it aired ».
        assert produced == NothingAired("nothing_to_say") and not produced

        assert sample("radio_segments_total", format="analysis", outcome="nothing_to_say") == (
            silent + 1
        )
        assert sample("radio_segment_production_seconds_count", format="analysis") == timed

    async def test_a_script_its_editor_refused_is_nothing_aired_never_a_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def refused(request: WritingRequest, out: Path, **kwargs: object) -> ProductionResult:
            return ProductionResult(ProductionOutcome.SCRIPT_REFUSED)

        monkeypatch.setattr(antenna_module, "produce_segment", refused)
        counted = sample("radio_segments_total", format="column", outcome="script_refused")

        assert await antenna(tmp_path).produce(
            slot(RadioFormat.COLUMN), previous=None, following=None
        ) == NothingAired("script_refused")

        assert (
            sample("radio_segments_total", format="column", outcome="script_refused") == counted + 1
        )

    async def test_a_failed_production_is_counted_by_how_it_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def voiceless(
            request: WritingRequest, out: Path, **kwargs: object
        ) -> ProductionResult:
            return ProductionResult(ProductionOutcome.VOICE_FAILED)

        monkeypatch.setattr(antenna_module, "produce_segment", voiceless)
        failed = sample("radio_segments_total", format="brief", outcome="voice_failed")

        assert (
            await antenna(tmp_path).produce(slot(RadioFormat.BRIEF), previous=None, following=None)
            is None
        )

        assert sample("radio_segments_total", format="brief", outcome="voice_failed") == failed + 1

    async def test_a_defect_is_counted_and_still_raised_for_the_loop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def broken(request: WritingRequest, out: Path, **kwargs: object) -> ProductionResult:
            raise RuntimeError("the mixer is gone")

        monkeypatch.setattr(antenna_module, "produce_segment", broken)
        errors = sample("radio_segments_total", format="brief", outcome="error")

        with pytest.raises(RuntimeError):
            await antenna(tmp_path).produce(slot(RadioFormat.BRIEF), previous=None, following=None)

        assert sample("radio_segments_total", format="brief", outcome="error") == errors + 1


NOTE_M1 = FlashNote(id="m1", sent_at=NOW, topic="interest", excerpt="The film you liked is out.")
NOTE_M2 = FlashNote(id="m2", sent_at=NOW, topic="heartbeat", excerpt="Your train leaves at 18:04.")


class CornerSources(Sources):
    """A listener whose personal corner holds the notification ``m1``."""

    async def day(self) -> PersonalFacts:
        self.day_reads += 1
        return PersonalFacts(
            day=DAY,
            corner=(
                RadioFact(
                    id="p3",
                    kind=FactKind.NOTIFICATION,
                    text='LIA sent the listener a notification (interest): "The film you liked"',
                    key="notification:m1",
                    sensitivity=Sensitivity.PERSONAL,
                ),
            ),
        )


class TestAFlash:
    """ADR-324 decision 32: LIA breaks in to say what she just wrote in the chat."""

    async def test_it_tells_the_notes_as_the_listeners_own_facts_and_hands_back(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        studio.tells = FactKind.NOTIFICATION
        studio.tells_many = 2
        radio = antenna(tmp_path)

        segment = await radio.produce_flash(
            [NOTE_M1, NOTE_M2], seq=100_001, cuts=RadioFormat.BRIEF, resumes=RadioFormat.BRIEF
        )

        assert segment is not None
        [request] = studio.requests
        assert request.format is RadioFormat.FLASH
        assert (request.previous, request.following) == (RadioFormat.BRIEF, RadioFormat.BRIEF)
        assert request.station_id is False and request.clock_mark is None
        facts = request.pack.facts
        assert [fact.key for fact in facts] == ["notification:m1", "notification:m2"]
        assert {fact.kind for fact in facts} == {FactKind.NOTIFICATION}
        assert {fact.sensitivity for fact in facts} == {Sensitivity.PERSONAL}
        assert "The film you liked is out." in facts[0].text and "(interest)" in facts[0].text
        assert isinstance(segment, ProducedSegment)
        assert segment.audio_path.name.startswith("100001")

    async def test_the_personal_corner_never_comes_back_to_a_note_a_flash_told(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        studio.tells = FactKind.NOTIFICATION
        control = antenna(tmp_path / "control", sources=CornerSources())
        assert await control.produce(slot(RadioFormat.JOURNAL, 3), previous=None, following=None)
        assert "notification:m1" in [fact.key for fact in studio.requests[-1].pack.facts]

        radio = antenna(tmp_path / "flashed", sources=CornerSources())
        assert await radio.produce_flash([NOTE_M1], seq=100_001, cuts=None, resumes=None)
        before = len(studio.requests)
        await radio.produce(slot(RadioFormat.JOURNAL, 3), previous=None, following=None)

        asked = studio.requests[before:]
        assert all("notification:m1" not in [f.key for f in r.pack.facts] for r in asked)

    async def test_a_note_the_corner_already_told_is_never_flashed_again(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        studio.tells = FactKind.NOTIFICATION
        radio = antenna(tmp_path, sources=CornerSources())
        assert await radio.produce(slot(RadioFormat.JOURNAL, 3), previous=None, following=None)
        before = len(studio.requests)

        assert await radio.produce_flash([NOTE_M1, NOTE_M2], seq=100_001, cuts=None, resumes=None)
        [request] = studio.requests[before:]
        assert [fact.key for fact in request.pack.facts] == ["notification:m2"]

        again = await radio.produce_flash([NOTE_M1], seq=100_002, cuts=None, resumes=None)
        assert again == NothingAired("nothing_to_say")
        assert len(studio.requests) == before + 1

    async def test_the_corner_leaves_alone_what_a_flash_is_telling(
        self, tmp_path: Path, studio: Studio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The corner reads the same notifications, newest first: while a flash is
        voiced, a programme of the corner must not tell its note too."""
        studio.tells = FactKind.NOTIFICATION
        voicing, done = asyncio.Event(), asyncio.Event()

        async def slow_flash(
            request: WritingRequest, out: Path, **kwargs: object
        ) -> ProductionResult:
            if request.format is RadioFormat.FLASH:
                voicing.set()
                await done.wait()
            return await studio(request, out, **kwargs)

        monkeypatch.setattr(antenna_module, "produce_segment", slow_flash)
        radio = antenna(tmp_path, sources=CornerSources())
        flash = asyncio.create_task(
            radio.produce_flash([NOTE_M1], seq=100_001, cuts=None, resumes=None)
        )
        await asyncio.wait_for(voicing.wait(), timeout=5)

        await radio.produce(slot(RadioFormat.JOURNAL, 3), previous=None, following=None)
        done.set()
        assert await flash

        corner = [r for r in studio.requests if r.format is RadioFormat.JOURNAL]
        assert all("notification:m1" not in [f.key for f in r.pack.facts] for r in corner)

    async def test_a_flash_that_failed_leaves_its_notes_to_the_corner(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        studio.tells = FactKind.NOTIFICATION
        studio.fail_next = 1
        radio = antenna(tmp_path, sources=CornerSources())
        assert await radio.produce_flash([NOTE_M1], seq=100_001, cuts=None, resumes=None) is None

        corner = await radio.produce(slot(RadioFormat.JOURNAL, 3), previous=None, following=None)
        assert isinstance(corner, ProducedSegment)
        [request] = [r for r in studio.requests if r.format is RadioFormat.JOURNAL]
        assert "notification:m1" in [fact.key for fact in request.pack.facts]

    async def test_a_flash_is_counted_under_its_own_format(
        self, tmp_path: Path, studio: Studio
    ) -> None:
        studio.tells = FactKind.NOTIFICATION
        produced = sample("radio_segments_total", format="flash", outcome="produced")

        assert await antenna(tmp_path).produce_flash(
            [NOTE_M1], seq=100_001, cuts=None, resumes=RadioFormat.BRIEF
        )

        assert sample("radio_segments_total", format="flash", outcome="produced") == produced + 1
