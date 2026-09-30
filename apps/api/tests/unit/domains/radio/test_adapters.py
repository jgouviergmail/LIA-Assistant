"""The radio's ports on the platform: the engine, the loop's parts, the cost (ADR-324)."""

from __future__ import annotations

import contextlib
import dataclasses
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.radio import adapters
from src.domains.radio.adapters import (
    NEWS_CANDIDATES_READ_MAX,
    RADIO_VOICE_SLOT,
    RADIO_WRITER_SLOT,
    AccountedProducer,
    AccountSetupBuilder,
    CollectedDay,
    LedgerCostReader,
    NewsDesk,
    bound_call,
    interest_stories_limit,
    radio_engine,
)
from src.domains.radio.editorial import NEWS_MAX_AGE_S
from src.domains.radio.flash import FlashNote
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.interests import interest_stories_max
from src.domains.radio.live_store import RadioSessionRecord
from src.domains.radio.personal import PersonalFacts, PersonalSource
from src.domains.radio.preferences import RadioPreferences
from src.domains.radio.production import ProducedSegment
from src.domains.radio.programme import Slot
from src.domains.radio.prompting import ListenerTaste
from src.domains.radio.schemas import RadioStartRequest
from src.domains.radio.setup import RadioSetup, VerificationMode
from src.domains.radio.setup_builder import REFUSED_VOICE_UNAVAILABLE, RadioStartRefused
from src.domains.voice.factory import TTSConfig
from src.domains.voice.voices_catalog import ElevenLabsVoicesError, VoiceOption

pytestmark = pytest.mark.unit

USER = UUID("00000000-0000-4000-8000-0000000000d1")
NOW = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
VOICE = VoiceOption(voice_id="v1", label="One", gender="female", language="en")
SLOT = Slot(seq=1, format=RadioFormat.OPENING, station_id=True, air_at=NOW, duration_s=25.0)
SETUP = RadioSetup(
    language="en",
    language_name="English",
    timezone="UTC",
    station_name="LIA Radio",
    personality="Calm.",
    listener_name=None,
    interests=(),
    stated_tastes=(),
    frequencies={},
    public_mode=False,
    voices={RadioRole.HOST: "voice-a"},
    verification=VerificationMode.OFF,
    disabled_sources=frozenset(),
    disabled_feeds=frozenset(),
    seed=7,
    startup_estimate_s=12.0,
)
RECORD = RadioSessionRecord(
    session_id=uuid4(), user_id=USER, run_id="radio_run", started_at=NOW, setup=SETUP.to_dict()
)


def config(provider: str) -> TTSConfig:
    return TTSConfig(provider=provider, model="m", voice_male="a", voice_female="b")


def serving(monkeypatch: pytest.MonkeyPatch, provider: str, reason: str | None = None) -> None:
    async def tts_config(slot: str) -> TTSConfig:
        assert slot == RADIO_VOICE_SLOT
        return config(provider)

    monkeypatch.setattr(adapters, "get_tts_config", tts_config)
    monkeypatch.setattr(adapters, "unservable_reason", lambda cfg, *, records_tokens: reason)


class TestTheEngine:
    async def test_an_engine_the_instance_cannot_serve_refuses_the_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serving(monkeypatch, "openai", reason="api_key_missing")

        with pytest.raises(RadioStartRefused) as refused:
            await radio_engine()
        assert refused.value.reason == REFUSED_VOICE_UNAVAILABLE

    async def test_a_shipped_catalogue_is_the_engine_s_voices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serving(monkeypatch, "edge")
        monkeypatch.setitem(adapters._STATIC_CATALOGUES, "edge", lambda: [VOICE])

        engine = await radio_engine()

        assert engine.voices == [VOICE]
        assert engine.multilingual is False  # an Edge voice speaks its own language

    async def test_a_live_catalogue_that_fails_offers_no_voice_rather_than_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serving(monkeypatch, "elevenlabs")

        async def unavailable(*, api_key: str, base_url: str) -> list[VoiceOption]:
            raise ElevenLabsVoicesError("vendor says no")

        monkeypatch.setattr(adapters, "get_elevenlabs_voices", unavailable)

        engine = await radio_engine()

        assert engine.voices == [] and engine.multilingual is True


class Production:
    """Stands for the antenna: answers, or breaks."""

    def __init__(self, *, broken: bool = False) -> None:
        self.broken = broken

    async def produce(
        self, slot: Slot, *, previous: RadioFormat | None, following: RadioFormat | None
    ) -> ProducedSegment | None:
        if self.broken:
            raise RuntimeError("the writer broke")
        return None

    async def produce_flash(
        self,
        notes: Sequence[FlashNote],
        *,
        seq: int,
        cuts: RadioFormat | None,
        resumes: RadioFormat | None,
    ) -> ProducedSegment | None:
        if self.broken:
            raise RuntimeError("the writer broke")
        return None


class Tracker:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class TestTheAccountedProducer:
    async def test_every_production_files_its_spend(self) -> None:
        tracker = Tracker()
        producer = AccountedProducer(Production(), tracker)

        assert await producer.produce(SLOT, previous=None, following=None) is None
        assert tracker.commits == 1

    async def test_a_production_that_breaks_still_files_what_it_spent(self) -> None:
        tracker = Tracker()
        producer = AccountedProducer(Production(broken=True), tracker)

        with pytest.raises(RuntimeError):
            await producer.produce(SLOT, previous=None, following=None)
        assert tracker.commits == 1

    @pytest.mark.parametrize("broken", [False, True])
    async def test_a_flash_files_its_spend_too(self, broken: bool) -> None:
        tracker = Tracker()
        producer = AccountedProducer(Production(broken=broken), tracker)

        with contextlib.suppress(RuntimeError):
            await producer.produce_flash([NOTE], seq=100_001, cuts=None, resumes=None)
        assert tracker.commits == 1


NOTE = FlashNote(id="m1", sent_at=NOW, topic="interest", excerpt="Hello.")


class TestTheFlashSource:
    """ADR-324 decision 32: what LIA wrote, read for a flash — never in company."""

    def _setup(self, **overrides: Any) -> Any:
        from dataclasses import replace as replaced

        return replaced(SETUP, **overrides)

    def test_a_listener_in_company_or_with_the_notifications_silenced_gets_none(
        self,
    ) -> None:
        record = RECORD
        assert adapters.flash_source(record, self._setup()) is not None
        assert adapters.flash_source(record, self._setup(public_mode=True)) is None
        silenced = self._setup(disabled_sources=frozenset({PersonalSource.NOTIFICATIONS}))
        assert adapters.flash_source(record, silenced) is None


class TestTheNewsDesk:
    async def test_it_reads_the_freshest_stories_no_format_is_too_old_to_air(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: dict[str, Any] = {}

        async def news_candidates(user_id: UUID, **kwargs: Any) -> list[Any]:
            asked.update(kwargs, user_id=user_id)
            return []

        monkeypatch.setattr(adapters, "news_candidates", news_candidates)
        unticked = frozenset({"https://feeds.example/unticked.xml"})
        desk = NewsDesk(
            user_id=USER,
            run_id="radio_test",
            disabled_feeds=unticked,
            interests_limit=40,
            clock=lambda: NOW,
        )

        heard, prints = frozenset({"a-story-id"}), frozenset({"a story"})
        from src.domains.agents.effects.treatments import treatment_collector

        with treatment_collector(run_id="radio_test"):
            assert await desk.candidates(heard_keys=heard, heard_stories=prints) == []
        assert asked == {
            "user_id": USER,
            "disabled_feeds": unticked,
            "since": NOW - timedelta(seconds=NEWS_MAX_AGE_S),
            "limit": NEWS_CANDIDATES_READ_MAX,
            # The interests' stories are counted apart: the sources never crowd them out.
            "interests_limit": 40,
            # What was heard comes last under the bound: it keeps what can still air.
            "heard_keys": heard,
            "heard_stories": prints,
        }


class TestTheInterests:
    """ONE count of interests (``RADIO_INTEREST_TOPICS_MAX``): the start reads that many,
    the writer is told them and the search looks them up; their stories have a bound of
    their own on the desk, and none at all when the session holds no interest."""

    @pytest.mark.parametrize(("capability", "expected"), [(True, 5), (False, 0)])
    async def test_the_start_reads_the_one_count_of_interests(
        self, monkeypatch: pytest.MonkeyPatch, capability: bool, expected: int
    ) -> None:
        asked: dict[str, object] = {}

        async def read_taste(user_id: UUID, **kwargs: object) -> ListenerTaste:
            asked.update(kwargs)
            return ListenerTaste()

        async def enabled(capability_name: PlatformCapability) -> bool:
            return capability

        monkeypatch.setattr(adapters, "read_taste", read_taste)
        monkeypatch.setattr(adapters, "is_capability_enabled", enabled)
        monkeypatch.setattr(settings, "radio_interest_topics_max", 5)
        account = adapters._Account(
            language="en",
            timezone="UTC",
            first_name=None,
            memory_enabled=False,
            personality="",
            preferences=RadioPreferences(),
        )
        request = RadioStartRequest(public_mode=False)
        await AccountSetupBuilder._taste(USER, account, request, run_id="radio_test")
        assert asked["interests_max"] == expected
        assert asked["stated_allowed"] is False

    def test_a_session_without_interests_reads_none_of_their_stories(self) -> None:
        # In company, with the capability off, or with no interest: what a search found
        # earlier must not air — it would voice what the listener cares about.
        assert interest_stories_limit(SETUP) == 0

    def test_a_session_with_interests_reads_every_story_the_searches_can_file(self) -> None:
        with_interests = dataclasses.replace(SETUP, interests=("jazz",))
        assert interest_stories_limit(with_interests) == interest_stories_max(
            topics=settings.radio_interest_topics_max,
            stories_per_search=settings.radio_interest_stories_max,
            fresh_s=settings.radio_interest_fresh_seconds,
            horizon_s=NEWS_MAX_AGE_S,
        )
        assert interest_stories_limit(with_interests) > 0


class TestTheCollectedDay:
    async def test_the_day_is_read_inside_a_collector_of_the_session_s_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []

        @contextlib.asynccontextmanager
        async def collecting(run_id: str) -> AsyncIterator[None]:
            events.append(f"open {run_id}")
            yield
            events.append(f"close {run_id}")

        facts = PersonalFacts()

        class Day:
            async def day(self) -> PersonalFacts:
                events.append("read")
                return facts

        monkeypatch.setattr(adapters, "collecting", collecting)

        assert await CollectedDay(Day(), "radio_run").day() is facts
        assert events == ["open radio_run", "read", "close radio_run"]


class Answer(BaseModel):
    text: str


class TestTheBoundCall:
    async def test_it_answers_through_the_radio_s_own_slot_and_the_session_s_tracker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}
        llm = object()

        @dataclass
        class SlotConfig:
            provider: str

        async def structured(
            model: object, messages: list[Any], schema: type[Answer], **kwargs: Any
        ) -> Answer:
            seen.update(kwargs, model=model, schema=schema)
            return Answer(text="ok")

        monkeypatch.setattr(adapters, "get_llm", lambda slot: llm)
        monkeypatch.setattr(
            adapters, "get_llm_config_for_agent", lambda _settings, slot: SlotConfig("vendor")
        )
        monkeypatch.setattr(adapters, "get_structured_output", structured)
        callback = object()

        call = bound_call(RADIO_WRITER_SLOT, user_id=USER, callbacks=[callback])
        answer = await call([], Answer)

        assert answer == Answer(text="ok")
        assert seen["model"] is llm and seen["schema"] is Answer
        assert seen["provider"] == "vendor" and seen["node_name"] == RADIO_WRITER_SLOT
        assert seen["user_id"] == USER
        # The node metadata adds the metrics handler beside the session's tracker.
        assert callback in seen["config"]["callbacks"]


class Client:
    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


class TestTheSessionParts:
    async def test_the_voice_client_is_closed_when_the_parts_cannot_be_built(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = Client()

        async def tts_config(slot: str) -> TTSConfig:
            return config("openai")

        async def gone(user_id: UUID) -> Any:
            raise LookupError("the listener's account is gone")

        monkeypatch.setattr(adapters, "get_tts_config", tts_config)
        monkeypatch.setattr(
            adapters, "get_tts_client_sync", lambda cfg, *, strict, records_tokens: client
        )
        monkeypatch.setattr(adapters, "_cards_of", gone)
        record = RadioSessionRecord(
            session_id=uuid4(), user_id=USER, run_id="radio_x", started_at=NOW
        )

        with pytest.raises(LookupError):
            async with adapters.session_parts(record, SETUP):
                pass
        assert client.closed == 1


class TestTheCost:
    @pytest.mark.parametrize(("summary", "cost"), [(None, 0.0), ("1.25", 1.25)])
    async def test_the_cost_is_the_run_s_billed_total(
        self, monkeypatch: pytest.MonkeyPatch, summary: str | None, cost: float
    ) -> None:
        @dataclass
        class Summary:
            billed_cost_eur: str

        class Repository:
            def __init__(self, db: object) -> None:
                pass

            async def get_token_summary_by_run_id(self, run_id: str) -> Summary | None:
                assert run_id == "radio_run"
                return None if summary is None else Summary(summary)

        @contextlib.asynccontextmanager
        async def db_context() -> AsyncIterator[object]:
            yield object()

        monkeypatch.setattr(adapters, "ChatRepository", Repository)
        monkeypatch.setattr(adapters, "get_db_context", db_context)

        assert await LedgerCostReader().cost_eur("radio_run") == cost
