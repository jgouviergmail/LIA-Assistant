"""A cold dashboard must not silence the listener's journal."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from random import Random
from uuid import UUID, uuid4

import pytest

from src.domains.briefing import service as briefing
from src.domains.briefing.cache_keys import section_cache_key
from src.domains.briefing.constants import SECTION_NAMES
from src.domains.briefing.exceptions import ConnectorAccessError
from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    CardStatus,
    ForYouData,
    WeatherData,
)
from src.domains.radio import adapters
from src.domains.radio.day_source import ListenerDay
from src.domains.radio.facts import FactKind, clock_fact
from src.domains.radio.formats import RadioFormat
from src.domains.radio.grid import AiredSegment, GridInputs, next_segment
from src.domains.radio.packs import Desk, available_formats
from src.domains.radio.personal import PersonalSource, briefing_drafts, personal_facts
from src.domains.users.models import User
from tests.unit.domains.radio.test_day_source import DONE_EVENT, Reader, Recorder

pytestmark = pytest.mark.unit
NOW = datetime(2026, 9, 28, 7, 0, tzinfo=UTC)


class Cache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.reads: list[str] = []

    async def get(self, key: str) -> str | None:
        self.reads.append(key)
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        assert ex > 0
        self.values[key] = value


async def test_cold_cache_still_schedules_the_personal_journal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(id=uuid4(), language="en", timezone="UTC", briefing_preferences={})
    cache = Cache()

    class Database:
        async def get(self, model: type[User], user_id: UUID) -> User:
            assert model is User and user_id == user.id
            return user

    @asynccontextmanager
    async def database() -> AsyncIterator[Database]:
        yield Database()

    async def redis() -> Cache:
        return cache

    async def agenda(*, user: User, user_tz: object, language: str) -> AgendaData:
        return AgendaData(events=[AgendaEventItem(title="Team meeting", start_local="10:00")])

    monkeypatch.setattr(adapters, "get_db_context", database)
    monkeypatch.setattr(briefing, "get_redis_cache", redis)
    monkeypatch.setattr(briefing, "fetch_agenda", agenda)
    cards = await (await adapters._cards_of(user.id))(frozenset({"agenda"}))
    facts = personal_facts(briefing_drafts(cards))
    desk = Desk(clock=clock_fact(NOW), day=facts.day, corner=facts.corner)
    decision = next_segment(
        GridInputs(
            session_started_at=NOW,
            aired=(AiredSegment(RadioFormat.OPENING, NOW),),
            air_at=NOW,
            timezone=UTC,
            frequencies={},
            available=available_formats(desk),
            public_mode=False,
            voices_by_format={RadioFormat.JOURNAL: 1},
            stop_at=None,
        ),
        Random(0),
    )
    assert decision is not None and decision.format is RadioFormat.JOURNAL


class Material:
    """Real source-to-journal composition, with only IO at the boundaries replaced."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.user = User(
            id=uuid4(),
            language="en",
            timezone="UTC",
            briefing_preferences={"hidden": list(SECTION_NAMES)},
        )
        self.cache = Cache()
        self.fetched: list[str] = []
        self.agenda_error = False
        self.agenda_empty = False
        self.recorder = Recorder()
        monkeypatch.setattr(briefing, "get_redis_cache", self.redis)
        # An unexpected source read is visible even if the section mapper catches it.
        for name in SECTION_NAMES:
            monkeypatch.setattr(briefing, f"fetch_{name}", self.unexpected)
        monkeypatch.setattr(briefing, "fetch_agenda", self.agenda)
        monkeypatch.setattr(briefing, "fetch_weather", self.weather)
        monkeypatch.setattr(briefing, "fetch_for_you", self.commitments)

    async def redis(self) -> Cache:
        return self.cache

    async def unexpected(self, **kwargs: object) -> None:
        self.fetched.append("unexpected")
        raise AssertionError("an unselected source must never be read")

    async def agenda(self, **kwargs: object) -> AgendaData:
        self.fetched.append("agenda")
        if self.agenda_error:
            raise ConnectorAccessError("calendar", "connector_oauth_expired", "Expired")
        events = (
            []
            if self.agenda_empty
            else [AgendaEventItem(id="event-1", title="Team meeting", start_local="10:00")]
        )
        return AgendaData(events=events)

    async def weather(self, **kwargs: object) -> WeatherData:
        self.fetched.append("weather")
        return WeatherData(
            temperature_c=18,
            condition_code="Clear",
            description="Clear",
            icon_emoji="sun",
        )

    async def commitments(self, **kwargs: object) -> ForYouData:
        self.fetched.append("for_you")
        return ForYouData(open_loops=[], recent_automations=[])

    def day(
        self,
        sources: frozenset[PersonalSource],
        *,
        public: bool = False,
        done: Reader | None = None,
    ) -> ListenerDay:
        return ListenerDay(
            user_id=self.user.id,
            tz=UTC,
            disabled_sources=frozenset(PersonalSource) - sources,
            public_mode=public,
            cards=briefing.BriefingService(self.user).read_selected_cards,
            readers={},
            done_readers={PersonalSource.AGENDA: done} if done else {},
            ahead_readers={},
            horizon_s=300,
            record=self.recorder,
            clock=lambda: NOW.replace(hour=13) if done else NOW,
        )

    def expire_agenda(self) -> None:
        self.cache.values.pop(
            section_cache_key(
                user_id=self.user.id,
                language="en",
                section="agenda",
            )
        )


@pytest.fixture
def material(monkeypatch: pytest.MonkeyPatch) -> Material:
    return Material(monkeypatch)


async def test_radio_reads_selected_sources_even_when_hidden_on_dashboard(
    material: Material,
) -> None:
    facts = await material.day(frozenset({PersonalSource.AGENDA})).day()
    assert material.fetched == ["agenda"]
    assert [fact.key for fact in facts.day] == ["event:event-1"]
    assert material.recorder.rows == [(frozenset({"agenda"}), frozenset())]
    # The dashboard still honours its own display preferences.
    cached = await briefing.BriefingService(material.user).read_cached_cards()
    assert cached.agenda.status is CardStatus.HIDDEN


async def test_warm_cache_is_reused_and_expired_cache_is_refilled(material: Material) -> None:
    day = material.day(frozenset({PersonalSource.AGENDA}))
    first, second = await day.day(), await day.day()
    assert first == second
    assert material.fetched == ["agenda"]
    assert len(material.recorder.rows) == 1
    material.expire_agenda()
    assert await day.day() == first
    assert material.fetched == ["agenda", "agenda"]
    assert len(material.recorder.rows) == 2


async def test_empty_day_is_cached_without_repeated_fetches(material: Material) -> None:
    material.agenda_empty = True
    day = material.day(frozenset({PersonalSource.AGENDA}))
    assert (await day.day()).day == ()
    assert (await day.day()).day == ()
    assert material.fetched == ["agenda"]
    assert material.recorder.rows == [(frozenset({"agenda"}), frozenset())]


async def test_public_mode_fetches_only_weather(material: Material) -> None:
    facts = await material.day(frozenset(PersonalSource), public=True).day()
    assert material.fetched == ["weather"]
    assert all(key.endswith(":weather") for key in material.cache.reads)
    assert [fact.kind for fact in facts.day] == [FactKind.WEATHER]
    assert facts.corner == facts.done == facts.ahead == ()
    assert material.recorder.rows == [(frozenset({"weather"}), frozenset())]


async def test_all_sources_disabled_means_no_cache_or_source_io(material: Material) -> None:
    await material.day(frozenset()).day()
    assert material.fetched == []
    assert material.cache.values == {}
    assert material.cache.reads == []
    assert material.recorder.rows == []


async def test_failed_source_does_not_air_stale_data_or_silence_other_sources(
    material: Material,
) -> None:
    day = material.day(frozenset({PersonalSource.AGENDA, PersonalSource.WEATHER}))
    await day.day()
    material.expire_agenda()
    material.agenda_error = True
    facts = await day.day()
    assert [fact.kind for fact in facts.day] == [FactKind.WEATHER]
    assert material.recorder.rows[-1] == (frozenset({"agenda"}), frozenset({"agenda"}))
    material.agenda_error = False
    assert any(fact.kind is FactKind.EVENT for fact in (await day.day()).day)


async def test_commitments_use_for_you_card_but_keep_radio_source_name(material: Material) -> None:
    await material.day(frozenset({PersonalSource.COMMITMENTS})).day()
    assert material.fetched == ["for_you"]
    assert material.recorder.rows == [(frozenset({"commitments"}), frozenset())]


async def test_live_day_and_done_are_recorded_once_with_any_failure_preserved(
    material: Material,
) -> None:
    done = Reader([DONE_EVENT], fails=True)
    facts = await material.day(frozenset({PersonalSource.AGENDA}), done=done).day()
    assert [fact.key for fact in facts.day] == ["event:event-1"]
    assert material.recorder.rows == [(frozenset({"agenda"}), frozenset({"agenda"}))]


async def test_cache_only_api_still_never_fetches(material: Material) -> None:
    material.user.briefing_preferences = {}
    cards = await briefing.BriefingService(material.user).read_cached_cards()
    assert cards.agenda.status is CardStatus.NOT_CONFIGURED
    assert material.fetched == []


async def test_unknown_section_is_refused_before_io(material: Material) -> None:
    with pytest.raises(ValueError, match="unknown briefing section"):
        await briefing.BriefingService(material.user).read_selected_cards(frozenset({"typo"}))
    assert material.fetched == []
