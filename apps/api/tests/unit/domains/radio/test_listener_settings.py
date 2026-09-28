"""What a listener may set: offered as published, refused where it is written (ADR-324)."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from prometheus_client import REGISTRY

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ResourceNotFoundError
from src.domains.radio import listener_settings
from src.domains.radio.adapters import RadioEngine
from src.domains.radio.constants import SOURCE_LABEL_MAX_CHARS
from src.domains.radio.editorial import NEWS_MAX_AGE_S
from src.domains.radio.errors import (
    PERSONALITY_UNKNOWN,
    SOURCE_LIMIT,
    SOURCE_REFUSED,
    TIMER_TOO_LONG,
    VOICE_UNKNOWN,
)
from src.domains.radio.formats import RadioRole
from src.domains.radio.newsroom.catalogue import CATALOGUE
from src.domains.radio.newsroom.discovery import FeedDescription
from src.domains.radio.newsroom.sources import Discovery, DiscoveryOutcome
from src.domains.radio.preferences import RadioPreferences
from src.domains.radio.repository import RadioSource, RadioSourceLimitReached, SourceStory
from src.domains.radio.schemas import RadioSourceUpdateRequest
from src.domains.radio.setup import VerificationMode
from src.domains.radio.setup_builder import REFUSED_VOICE_UNAVAILABLE, RadioStartRefused
from src.domains.voice.factory import TTSConfig
from src.domains.voice.voices_catalog import VoiceOption

pytestmark = pytest.mark.unit

USER = uuid.UUID("00000000-0000-4000-8000-0000000000e1")
ENGLISH = VoiceOption(voice_id="en-voice", label="Ann", gender="female", language="en")
FRENCH = VoiceOption(voice_id="fr-voice", label="Anne", gender="female", language="fr")
CHINESE = VoiceOption(voice_id="zh-voice", label="An", gender="female", language="zh")
FEED = "https://outlet.example/feed.xml"
MINE = uuid.UUID("00000000-0000-4000-8000-0000000000e2")


def engine_with(*voices: VoiceOption) -> RadioEngine:
    config = TTSConfig(provider="edge", model="m", voice_male="a", voice_female="b")
    return RadioEngine(config, list(voices), multilingual=False)


#: The key the voices of ``engine_with``'s engine are kept under.
ENGINE_KEY = "edge/m"


def offering(monkeypatch: pytest.MonkeyPatch, engine: RadioEngine | None) -> None:
    async def radio_engine() -> RadioEngine:
        if engine is None:
            raise RadioStartRefused(REFUSED_VOICE_UNAVAILABLE)
        return engine

    async def radio_engine_key() -> str:
        # Known even when the engine cannot be served: it is the slot's configuration.
        return ENGINE_KEY

    monkeypatch.setattr(listener_settings, "radio_engine", radio_engine)
    monkeypatch.setattr(listener_settings, "radio_engine_key", radio_engine_key)


def code_of(raised: pytest.ExceptionInfo[BaseAPIException]) -> dict[str, Any]:
    detail = raised.value.detail
    assert isinstance(detail, dict)
    return detail


class Written:
    """Stands for ``write_preferences``: records what reached the store."""

    def __init__(self) -> None:
        self.stored: list[RadioPreferences] = []
        self.engines: list[str] = []

    async def __call__(
        self, user_id: uuid.UUID, preferences: RadioPreferences, *, engine: str
    ) -> RadioPreferences:
        assert user_id == USER
        self.stored.append(preferences)
        self.engines.append(engine)
        return preferences


@pytest.fixture
def written(monkeypatch: pytest.MonkeyPatch) -> Written:
    store = Written()
    monkeypatch.setattr(listener_settings, "write_preferences", store)
    return store


class TestTheOfferedVoices:
    async def test_an_engine_the_instance_cannot_serve_offers_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        offering(monkeypatch, None)

        assert await listener_settings.offered_voices("en") == []

    async def test_the_voices_are_the_listener_s_language_s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH, FRENCH))

        assert await listener_settings.offered_voices("fr") == [FRENCH]

    async def test_the_options_read_the_stored_language_through_the_chokepoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH, CHINESE))

        options = await listener_settings.radio_options("zh")

        assert [voice.voice_id for voice in options.voices] == ["zh-voice"]
        assert options.timer_max_minutes == settings.radio_timer_max_minutes
        assert options.timer_default_minutes == settings.radio_timer_minutes
        assert options.verification_default == VerificationMode(settings.radio_verification_default)
        assert options.custom_sources_max == settings.radio_custom_sources_max


class TestSavingThePreferences:
    async def test_a_timer_past_the_instance_s_maximum_is_refused_with_the_maximum(
        self, monkeypatch: pytest.MonkeyPatch, written: Written
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH))
        too_long = RadioPreferences(timer_minutes=settings.radio_timer_max_minutes + 1)

        with pytest.raises(BaseAPIException) as refused:
            await listener_settings.save_preferences(USER, "en", too_long)

        assert code_of(refused) == {
            "code": TIMER_TOO_LONG,
            "max_minutes": settings.radio_timer_max_minutes,
        }
        assert written.stored == []

    async def test_the_longest_timer_the_instance_allows_is_kept(
        self, monkeypatch: pytest.MonkeyPatch, written: Written
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH))
        longest = RadioPreferences(timer_minutes=settings.radio_timer_max_minutes)

        assert await listener_settings.save_preferences(USER, "en", longest) == longest

    async def test_the_voices_saved_are_kept_for_the_engine_now_in_place(
        self, monkeypatch: pytest.MonkeyPatch, written: Written
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH))
        chosen = RadioPreferences(voices={RadioRole.HOST: ENGLISH.voice_id})

        await listener_settings.save_preferences(USER, "en", chosen)

        assert (written.stored, written.engines) == ([chosen], [ENGINE_KEY])

    async def test_a_voice_the_engine_does_not_offer_in_their_language_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, written: Written
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH, FRENCH))
        # A French voice for an English listener: the start would drop it.
        foreign = RadioPreferences(voices={RadioRole.HOST: FRENCH.voice_id})

        with pytest.raises(BaseAPIException) as refused:
            await listener_settings.save_preferences(USER, "en", foreign)

        assert code_of(refused) == {"code": VOICE_UNKNOWN}
        assert written.stored == []

    async def test_an_engine_that_cannot_list_its_voices_right_now_is_not_strict(
        self, monkeypatch: pytest.MonkeyPatch, written: Written
    ) -> None:
        offering(monkeypatch, None)
        chosen = RadioPreferences(voices={RadioRole.HOST: "kept-from-before"})

        assert await listener_settings.save_preferences(USER, "en", chosen) == chosen

    async def test_a_personality_not_offered_any_more_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, written: Written
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH))

        async def not_offered(personality_id: uuid.UUID) -> bool:
            return False

        monkeypatch.setattr(listener_settings, "_personality_offered", not_offered)

        with pytest.raises(BaseAPIException) as refused:
            await listener_settings.save_preferences(
                USER, "en", RadioPreferences(personality_id=uuid.uuid4())
            )

        assert code_of(refused) == {"code": PERSONALITY_UNKNOWN}
        assert written.stored == []


class TestReadingThePreferences:
    """The page is handed only what a write accepts (ADR-184): a voice the engine no longer
    offers reads as automatic. Sent back as stored, it refused every save — measured on dev
    2026-09-27: the radio's engine changed, and four stored voices blocked every setting."""

    @staticmethod
    def storing(monkeypatch: pytest.MonkeyPatch, stored: RadioPreferences) -> None:
        async def read_preferences(user_id: uuid.UUID, *, engine: str) -> RadioPreferences:
            # The voices read are those kept for the engine now in place.
            assert (user_id, engine) == (USER, ENGINE_KEY)
            return stored

        monkeypatch.setattr(listener_settings, "read_preferences", read_preferences)

    async def test_a_voice_the_engine_no_longer_offers_reads_as_automatic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH, FRENCH))
        stored = RadioPreferences(
            voices={
                RadioRole.HOST: "another-engine-voice",
                RadioRole.ANCHOR: ENGLISH.voice_id,
                RadioRole.EXPERT: FRENCH.voice_id,  # usable in French only
            },
            timer_minutes=30,
        )
        self.storing(monkeypatch, stored)

        read = await listener_settings.listener_preferences(USER, "en")

        assert read == stored.model_copy(update={"voices": {RadioRole.ANCHOR: ENGLISH.voice_id}})

    async def test_what_is_read_is_accepted_when_written_back(
        self, monkeypatch: pytest.MonkeyPatch, written: Written
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH))
        self.storing(monkeypatch, RadioPreferences(voices={RadioRole.HOST: "gone"}))

        read = await listener_settings.listener_preferences(USER, "en")

        assert await listener_settings.save_preferences(USER, "en", read) == read

    async def test_an_engine_that_cannot_list_its_voices_keeps_the_stored_choice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        offering(monkeypatch, None)
        stored = RadioPreferences(voices={RadioRole.HOST: "kept-from-before"})
        self.storing(monkeypatch, stored)

        assert await listener_settings.listener_preferences(USER, "en") == stored


@contextlib.asynccontextmanager
async def no_client() -> AsyncIterator[object]:
    yield object()


async def no_robots() -> object:
    return object()


class TestLookingForAFeed:
    async def test_a_site_slower_than_the_bound_reads_as_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def endless(*args: object, **kwargs: object) -> Discovery:
            await asyncio.Event().wait()
            raise AssertionError("never reached")

        monkeypatch.setattr(listener_settings, "discover_feed", endless)
        monkeypatch.setattr(listener_settings, "newsroom_client", no_client)
        monkeypatch.setattr(listener_settings, "newsroom_robots", no_robots)
        monkeypatch.setattr(listener_settings, "SOURCE_DISCOVERY_TIMEOUT_S", 0.01)

        found = await asyncio.wait_for(listener_settings.look_for_feed("slow.example"), 2)

        assert found == Discovery(DiscoveryOutcome.UNREACHABLE)


def found_feed(title: str, language: str | None = "en") -> Discovery:
    return Discovery(
        DiscoveryOutcome.FOUND,
        feed_url=FEED,
        description=FeedDescription(title=title, language=language, entries=5),
    )


class TestAddingASite:
    def looking(self, monkeypatch: pytest.MonkeyPatch, found: Discovery) -> None:
        async def look_for_feed(address: str) -> Discovery:
            return found

        monkeypatch.setattr(listener_settings, "look_for_feed", look_for_feed)

    async def test_a_site_with_no_feed_is_refused_with_what_was_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.looking(monkeypatch, Discovery(DiscoveryOutcome.FORBIDDEN))

        with pytest.raises(BaseAPIException) as refused:
            await listener_settings.add_listener_source(USER, "closed.example")

        assert code_of(refused) == {"code": SOURCE_REFUSED, "outcome": "forbidden"}

    async def test_past_the_limit_the_refusal_carries_the_maximum(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.looking(monkeypatch, found_feed("Outlet"))

        async def full(user_id: uuid.UUID, **kwargs: object) -> RadioSource:
            raise RadioSourceLimitReached

        monkeypatch.setattr(listener_settings, "add_source", full)

        with pytest.raises(BaseAPIException) as refused:
            await listener_settings.add_listener_source(USER, "outlet.example")

        assert code_of(refused) == {
            "code": SOURCE_LIMIT,
            "max_sources": settings.radio_custom_sources_max,
        }

    @pytest.mark.parametrize(
        ("title", "label"),
        [
            ("Outlet Daily", "Outlet Daily"),
            ("", "outlet.example"),  # a feed with no title is named by its host
            ("x" * (SOURCE_LABEL_MAX_CHARS + 20), "x" * SOURCE_LABEL_MAX_CHARS),
        ],
    )
    async def test_what_the_server_found_is_what_is_stored(
        self, monkeypatch: pytest.MonkeyPatch, title: str, label: str
    ) -> None:
        self.looking(monkeypatch, found_feed(title, language="fr"))
        stored: dict[str, Any] = {}

        async def add_source(user_id: uuid.UUID, **kwargs: Any) -> RadioSource:
            stored.update(kwargs)
            return RadioSource(
                id=uuid.uuid4(), feed_url=kwargs["feed_url"], title=kwargs["title"], language=None
            )

        monkeypatch.setattr(listener_settings, "add_source", add_source)

        await listener_settings.add_listener_source(USER, "outlet.example/some-page")

        assert stored == {
            "feed_url": FEED,
            "title": label,
            "language": "fr",
            "max_sources": settings.radio_custom_sources_max,
        }


def lookups(outcome: str) -> float:
    return REGISTRY.get_sample_value("radio_source_lookups_total", {"outcome": outcome}) or 0.0


class TestEveryLookupIsCounted:
    async def test_what_a_lookup_found_is_counted_timeouts_included(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answers = iter([Discovery(DiscoveryOutcome.NO_FEED)])

        async def discover(*args: object, **kwargs: object) -> Discovery:
            found = next(answers, None)
            if found is None:
                await asyncio.Event().wait()
                raise AssertionError("never reached")
            return found

        monkeypatch.setattr(listener_settings, "discover_feed", discover)
        monkeypatch.setattr(listener_settings, "newsroom_client", no_client)
        monkeypatch.setattr(listener_settings, "newsroom_robots", no_robots)
        monkeypatch.setattr(listener_settings, "SOURCE_DISCOVERY_TIMEOUT_S", 0.01)
        no_feed, unreachable = lookups("no_feed"), lookups("unreachable")

        await listener_settings.look_for_feed("empty.example")
        await listener_settings.look_for_feed("slow.example")

        assert (lookups("no_feed"), lookups("unreachable")) == (no_feed + 1, unreachable + 1)


class Ledger:
    """Stands for the listener's aired ledger."""

    def __init__(self, keys: frozenset[str] = frozenset()) -> None:
        self.keys = keys
        self.forgotten = False

    async def heard(self) -> tuple[frozenset[str], frozenset[str]]:
        return self.keys, frozenset()

    async def forget(self) -> None:
        self.forgotten = True


class TestTheSources:
    """ADR-324 decision 38: what each source holds for the listener, read at once."""

    async def test_the_view_counts_the_window_against_what_the_listener_heard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        offering(monkeypatch, engine_with(ENGLISH))
        unticked = CATALOGUE[1].url
        stored = RadioPreferences(disabled_feeds=[unticked])

        async def read_preferences(user_id: uuid.UUID, *, engine: str) -> RadioPreferences:
            return stored

        site = RadioSource(uuid.uuid4(), FEED, "Outlet", "en", paused=True)

        async def list_sources(user_id: uuid.UUID) -> list[RadioSource]:
            return [site]

        async def failing_base_sources() -> frozenset[str]:
            return frozenset({CATALOGUE[0].url})

        asked: list[datetime] = []

        async def source_stories(user_id: uuid.UUID, *, since: datetime) -> list[SourceStory]:
            asked.append(since)
            return [
                SourceStory(uuid.uuid4(), CATALOGUE[0].url, False, "k1", "fp1"),
                SourceStory(uuid.uuid4(), CATALOGUE[0].url, False, "k2", "fp2"),
            ]

        ledger = Ledger(frozenset({"k1"}))

        async def aired_ledger(user_id: uuid.UUID) -> Ledger:
            return ledger

        for name, value in {
            "read_preferences": read_preferences,
            "list_sources": list_sources,
            "failing_base_sources": failing_base_sources,
            "source_stories": source_stories,
            "aired_ledger": aired_ledger,
        }.items():
            monkeypatch.setattr(listener_settings, name, value)
        now = datetime(2026, 9, 27, 21, 0, tzinfo=UTC)

        view = await listener_settings.listener_sources(USER, now=now)

        assert asked == [now - timedelta(seconds=NEWS_MAX_AGE_S)]
        first, second = view.base[0], view.base[1]
        assert (first.stories, first.unheard, first.failing, first.heard) == (2, 1, True, True)
        assert (second.url, second.heard) == (unticked, False)
        assert [(own.title, own.paused) for own in view.own] == [("Outlet", True)]
        assert (view.stories, view.unheard) == (2, 1)

    async def test_renaming_or_pausing_a_site_that_is_not_theirs_reads_as_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        changes: list[tuple[uuid.UUID, str | None, bool | None]] = []

        async def update_source(
            user_id: uuid.UUID, source_id: uuid.UUID, *, title: str | None, paused: bool | None
        ) -> bool:
            changes.append((source_id, title, paused))
            return source_id == MINE

        monkeypatch.setattr(listener_settings, "update_source", update_source)

        await listener_settings.update_listener_source(
            USER, MINE, RadioSourceUpdateRequest(title="  My   blog ", paused=True)
        )
        stranger = uuid.uuid4()
        with pytest.raises(ResourceNotFoundError):
            await listener_settings.update_listener_source(
                USER, stranger, RadioSourceUpdateRequest(paused=False)
            )
        # The name is folded the way the station's own name is.
        assert changes == [(MINE, "My blog", True), (stranger, None, False)]

    async def test_forgetting_what_was_heard_empties_the_listener_s_ledger(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ledger = Ledger()

        async def aired_ledger(user_id: uuid.UUID) -> Ledger:
            assert user_id == USER
            return ledger

        monkeypatch.setattr(listener_settings, "aired_ledger", aired_ledger)

        await listener_settings.forget_heard(USER)

        assert ledger.forgotten
