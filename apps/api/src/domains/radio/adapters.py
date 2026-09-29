"""The radio's ports on the platform (ADR-324): the start, the loop's parts, the cost.

The pure modules decide; this module reads the account and the instance and
binds them:

- every read opens a short session of its own and closes it before anything
  waits on the network (ADR-304);
- every model call goes through the one structured door, bound to the radio's
  OWN slot and to the session's tracker — so every euro of a session lands on
  its run's row, the one figure the player shows live (ADR-272), and every call
  answers to the spending ceilings;
- the voices come from the TTS factory's STRICT door: an engine the instance
  cannot serve refuses the start, and a substitute engine never airs in silence.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from src.core.config import settings
from src.core.constants import DEFAULT_ELEVENLABS_BASE_URL, ELEVENLABS_PROVIDER_NAME
from src.core.i18n import get_language_name, normalize_language
from src.core.i18n_radio import radio_station_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.prompt_store import read_prompt_file
from src.core.user_display import resolve_user_display_name
from src.domains.briefing.consultations import SelectedCardsReader
from src.domains.briefing.service import BriefingService
from src.domains.chat.repository import ChatRepository
from src.domains.chat.service import TrackingContext
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.personalities.service import PersonalityService
from src.domains.radio.aired import RedisAiredLedger
from src.domains.radio.antenna import Antenna, AntennaCrew, AntennaSetup, DaySource
from src.domains.radio.budget import radio_spend_blocked
from src.domains.radio.cast import engine_key
from src.domains.radio.constants import FLASH_NOTES_MAX
from src.domains.radio.consultations import collecting, consulted, recorder_for
from src.domains.radio.day_source import ListenerDay
from src.domains.radio.delivery import DELIVERY_LINES, load_style_phrases
from src.domains.radio.editorial import NEWS_MAX_AGE_S, NewsCandidate
from src.domains.radio.flash import FlashNote
from src.domains.radio.formats import FORMAT_SPECS, RadioFormat
from src.domains.radio.interest_search import refresh_listener_interests
from src.domains.radio.jev_checker import JevLineChecker
from src.domains.radio.live_store import RadioSessionRecord
from src.domains.radio.meanings import RedisHeadlineVectors
from src.domains.radio.orchestrator import FlashSource, Producer
from src.domains.radio.personal import NEUTRAL_SOURCES, PersonalFacts, PersonalSource
from src.domains.radio.preferences import RadioPreferences
from src.domains.radio.production import NothingAired, ProducedSegment, VoiceEngine
from src.domains.radio.programme import Slot
from src.domains.radio.prompting import ListenerTaste, StationVoice, load_templates
from src.domains.radio.readers import AHEAD_READERS, DONE_READERS, OWN_READERS
from src.domains.radio.readers.notifications import read_flash_notes
from src.domains.radio.readers.taste import read_taste
from src.domains.radio.repository import mark_listened, news_candidates, read_preferences
from src.domains.radio.runner import LoopParts
from src.domains.radio.schemas import RadioStartRequest
from src.domains.radio.settings_view import (
    instance_defaults,
    production_limits,
    radio_media_root,
)
from src.domains.radio.setup import RadioSetup, checked_formats
from src.domains.radio.setup_builder import (
    REFUSED_VOICE_UNAVAILABLE,
    ListenerProfile,
    RadioStartRefused,
    compose_setup,
    in_company,
)
from src.domains.radio.writing import (
    ModelAnalyst,
    ModelLineChecker,
    ModelScriptWriter,
    StructuredCall,
)
from src.domains.users.models import User
from src.domains.voice.factory import (
    TTSConfig,
    get_tts_client_sync,
    get_tts_config,
    unservable_reason,
)
from src.domains.voice.families import family_of
from src.domains.voice.voices_catalog import (
    ElevenLabsVoicesError,
    VoiceOption,
    get_edge_voices,
    get_elevenlabs_voices,
    get_gemini_voices,
    get_openai_voices,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.factory import LLMType, get_llm
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.llm.memory_embeddings import get_memory_embeddings
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.observability.callbacks import TokenTrackingCallback

logger = structlog.get_logger(__name__)

#: The radio's own slots (ADR-324): tuned apart from the chat's.
RADIO_WRITER_SLOT: Final[LLMType] = "radio_writer"
RADIO_ANALYST_SLOT: Final[LLMType] = "radio_analyst"
RADIO_VERIFIER_SLOT: Final[LLMType] = "radio_verifier"
RADIO_VOICE_SLOT: Final[str] = "radio_voice"

#: The stories a gathering reads, never heard first — enough for every shortlist once
#: the second tellings and an outlet's excess are set aside (every language: 818 stories
#: in 48 hours on dev, 2026-09-27).
NEWS_CANDIDATES_READ_MAX: Final[int] = 300

#: The engines whose voice list is fixed and shipped with the client.
_STATIC_CATALOGUES: Final[dict[str, Callable[[], list[VoiceOption]]]] = {
    "edge": get_edge_voices,
    "openai": get_openai_voices,
    "gemini": get_gemini_voices,
}


# --- The voices -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RadioEngine:
    """The engine the radio's voice slot names, as it stands.

    Attributes:
        config: Its configuration.
        voices: Its voices (every language).
        multilingual: Whether every voice speaks every language.
    """

    config: TTSConfig
    voices: list[VoiceOption]
    multilingual: bool


async def _engine_voices(config: TTSConfig) -> list[VoiceOption]:
    """The engine's voices: a shipped list, or the account's live one (ElevenLabs)."""
    static = _STATIC_CATALOGUES.get(config.provider)
    if static is not None:
        return static()
    if config.provider != ELEVENLABS_PROVIDER_NAME:
        return []
    api_key = LLMConfigOverrideCache.get_api_key(ELEVENLABS_PROVIDER_NAME) or ""
    try:
        return await get_elevenlabs_voices(api_key=api_key, base_url=DEFAULT_ELEVENLABS_BASE_URL)
    except ElevenLabsVoicesError as error:
        # The message may carry the vendor's words; its type says enough.
        logger.warning("radio_voice_catalogue_unavailable", error_type=type(error).__name__)
        return []


def _aired_ledger(redis: Any, user_id: UUID) -> RedisAiredLedger:
    return RedisAiredLedger(
        redis,
        user_id=user_id,
        personal_ttl_s=settings.radio_aired_ledger_ttl_seconds,
        clock=lambda: datetime.now(UTC),
    )


async def aired_ledger(user_id: UUID) -> RedisAiredLedger:
    """What a listener heard across sessions — the settings' counters and « forget » read it."""
    return _aired_ledger(await get_redis_cache(), user_id)


async def radio_engine_key() -> str:
    """The voice engine in place — known even when it cannot be served (its slot's setting)."""
    config = await get_tts_config(RADIO_VOICE_SLOT)
    return engine_key(config.provider, config.model)


async def radio_engine() -> RadioEngine:
    """The engine the radio speaks with.

    Raises:
        RadioStartRefused: ``voice_unavailable`` when the instance cannot serve
            it to a caller that records token-billed usage (the radio does).
    """
    config = await get_tts_config(RADIO_VOICE_SLOT)
    if unservable_reason(config, records_tokens=True) is not None:
        raise RadioStartRefused(REFUSED_VOICE_UNAVAILABLE)
    family = family_of(config.provider)
    voices = await _engine_voices(config)
    return RadioEngine(config, voices, multilingual=bool(family and family.multilingual_voices))


# --- The start ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Account:
    """What the start reads of the listener's account, detached from its session."""

    language: str
    timezone: str
    first_name: str | None
    memory_enabled: bool
    personality: str
    preferences: RadioPreferences


async def _read_account(user_id: UUID, *, engine: str) -> _Account:
    preferences = await read_preferences(user_id, engine=engine)
    async with get_db_context() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise LookupError("the listener's account is gone")
        chosen = preferences.personality_id or user.personality_id
        personality = await PersonalityService(db).get_prompt_instruction(chosen)
        return _Account(
            language=normalize_language(user.language),
            timezone=user.timezone,
            first_name=resolve_user_display_name(user.full_name, None) or None,
            memory_enabled=bool(user.memory_enabled),
            personality=str(personality),
            preferences=preferences,
        )


class AccountSetupBuilder:
    """Reads the listener's account, settings and taste into a session's frozen setup."""

    async def build(
        self, user_id: UUID, request: RadioStartRequest, *, now: datetime, run_id: str
    ) -> tuple[RadioSetup, datetime | None]:
        """The setup and the automatic stop; the start is filed as listening.

        Args:
            user_id: The listener.
            request: What they chose for this session.
            now: The start's instant.
            run_id: The session's run (what the start reads is filed under it).

        Returns:
            The setup and the automatic stop (None for none).

        Raises:
            RadioStartRefused: ``voice_unavailable`` or ``no_voice``.
        """
        engine = await radio_engine()
        account = await _read_account(
            user_id, engine=engine_key(engine.config.provider, engine.config.model)
        )
        taste = await self._taste(user_id, account, request, run_id=run_id)
        profile = ListenerProfile(
            language=account.language,
            language_name=get_language_name(account.language),
            timezone=account.timezone,
            first_name=account.first_name,
            station_name=radio_station_name(account.language),
            personality=account.personality,
            interests=taste.interests,
            stated_tastes=taste.stated,
        )
        built = compose_setup(
            profile,
            account.preferences,
            request,
            catalogue=engine.voices,
            multilingual=engine.multilingual,
            defaults=instance_defaults(),
            seed=secrets.randbits(31),
            now=now,
        )
        await _file_listening(user_id, now)
        return built

    @staticmethod
    async def _taste(
        user_id: UUID, account: _Account, request: RadioStartRequest, *, run_id: str
    ) -> ListenerTaste:
        """Nothing in company; else what the listener let LIA use, recorded."""
        if in_company(account.preferences, request):
            return ListenerTaste()
        async with collecting(run_id):
            return await read_taste(
                user_id,
                interests_allowed=await is_capability_enabled(PlatformCapability.INTERESTS),
                stated_allowed=account.memory_enabled,
                record=recorder_for(user_id, run_id),
            )


async def _file_listening(user_id: UUID, now: datetime) -> None:
    """File that the listener listened — the newsroom reads for recent listeners."""
    try:
        await mark_listened(user_id, now=now)
    except Exception as exc:  # noqa: BLE001 — the session plays; the newsroom may doze
        logger.warning("radio_listening_unfiled", error_type=type(exc).__name__)


# --- The loop ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NewsDesk:
    """The stored stories a session may choose from (the antenna's ``NewsSource``).

    Attributes:
        user_id: The listener (their running sites are offered).
        disabled_feeds: The base sources they unticked (every other one airs).
        clock: The current instant (aware).
    """

    user_id: UUID
    run_id: str
    disabled_feeds: frozenset[str]
    clock: Callable[[], datetime]

    async def candidates(
        self, *, heard_keys: frozenset[str], heard_stories: frozenset[str]
    ) -> list[NewsCandidate]:
        """The freshest stories no news format is too old to air, never heard first."""
        async with consulted(self.user_id, self.run_id, "news"):
            return await news_candidates(
                self.user_id,
                disabled_feeds=self.disabled_feeds,
                since=self.clock() - timedelta(seconds=NEWS_MAX_AGE_S),
                limit=NEWS_CANDIDATES_READ_MAX,
                heard_keys=heard_keys,
                heard_stories=heard_stories,
            )


@dataclass(frozen=True, slots=True)
class CollectedDay:
    """The listener's day, every gathering inside a collector of the session's run."""

    source: DaySource
    run_id: str

    async def day(self) -> PersonalFacts:
        """The day's and the corner's facts, their reads recorded."""
        async with collecting(self.run_id):
            return await self.source.day()


class SpendFiler(Protocol):
    """Files what the session spent so far (its tracker)."""

    async def commit(self) -> None:
        """File the pending records; a failure is logged, never raised."""
        ...


class AccountedProducer:
    """Commits the session's spend after every production — the live cost follows."""

    def __init__(self, producer: Producer, tracker: SpendFiler) -> None:
        self._producer = producer
        self._tracker = tracker

    async def produce(
        self, slot: Slot, *, previous: RadioFormat | None, following: RadioFormat | None
    ) -> ProducedSegment | NothingAired | None:
        """Produce the slot, then file what it cost (never raises for the filing)."""
        try:
            return await self._producer.produce(slot, previous=previous, following=following)
        finally:
            await self._tracker.commit()

    async def produce_flash(
        self,
        notes: Sequence[FlashNote],
        *,
        seq: int,
        cuts: RadioFormat | None,
        resumes: RadioFormat | None,
    ) -> ProducedSegment | NothingAired | None:
        """Produce a news flash, then file what it cost (never raises for the filing)."""
        try:
            return await self._producer.produce_flash(notes, seq=seq, cuts=cuts, resumes=resumes)
        finally:
            await self._tracker.commit()


class NotificationFlashes:
    """What LIA wrote to the listener since the station last looked — the loop's ``FlashSource``.

    Each look is a consultation, including one that finds no notification or
    fails. The register's UI folds repeated reads without losing their count.
    """

    def __init__(self, user_id: UUID, run_id: str) -> None:
        """Bind the source to the listener and the session's run."""
        self._user_id = user_id
        self._run_id = run_id

    async def since(self, after: datetime) -> list[FlashNote]:
        """The notifications sent after ``after``, oldest first, as many as one flash tells."""
        async with consulted(self._user_id, self._run_id, PersonalSource.NOTIFICATIONS.value):
            return await read_flash_notes(self._user_id, after=after, limit=FLASH_NOTES_MAX)


def flash_source(record: RadioSessionRecord, setup: RadioSetup) -> FlashSource | None:
    """The session's flash source; None when a notification may not air.

    A flash is personal: nothing of it airs in company (public mode), nor once
    the listener switched the notifications off for the radio.

    Args:
        record: The session.
        setup: Its frozen setup.

    Returns:
        The source, or None.
    """
    silenced = PersonalSource.NOTIFICATIONS in setup.disabled_sources
    in_company = setup.public_mode and PersonalSource.NOTIFICATIONS not in NEUTRAL_SOURCES
    if silenced or in_company:
        return None
    return NotificationFlashes(record.user_id, record.run_id)


def bound_call(slot: LLMType, *, user_id: UUID, callbacks: list[Any]) -> StructuredCall:
    """The structured door, bound to a radio slot, the listener and the session's tracker.

    Args:
        slot: The radio slot answering.
        user_id: The listener (the ceilings' owner).
        callbacks: The session tracker's callback.

    Returns:
        A call the writer, the analyst or the checker makes.
    """
    llm = get_llm(slot)
    provider = get_llm_config_for_agent(settings, slot).provider
    config = enrich_config_with_node_metadata(
        {"configurable": {"user_id": str(user_id)}, "callbacks": callbacks},
        node_name=slot,
    )

    async def call[M: BaseModel](messages: list[BaseMessage], schema: type[M]) -> M:
        return await get_structured_output(
            llm,
            messages,
            schema,
            provider=provider,
            node_name=slot,
            config=config,
            user_id=user_id,
        )

    return call


def _crew(
    record: RadioSessionRecord,
    setup: RadioSetup,
    *,
    engine: VoiceEngine,
    tracker: TrackingContext,
) -> AntennaCrew:
    callbacks: list[Any] = [TokenTrackingCallback(tracker, record.run_id)]
    station = StationVoice(setup.station_name, setup.language_name, setup.personality)
    templates = load_templates()
    limits = production_limits()

    def call(slot: LLMType) -> StructuredCall:
        return bound_call(slot, user_id=record.user_id, callbacks=callbacks)

    checked = checked_formats(setup.verification)
    return AntennaCrew(
        writer=ModelScriptWriter(
            template=templates.writer,
            station=station,
            call=call(RADIO_WRITER_SLOT),
            quote_max_chars=limits.quote_max_chars,
            taste=ListenerTaste(setup.interests, setup.stated_tastes),
        ),
        analyst=ModelAnalyst(
            template=templates.analyst, station=station, call=call(RADIO_ANALYST_SLOT)
        ),
        checker=(
            JevLineChecker(
                ModelLineChecker(
                    template=templates.verifier, station=station, call=call(RADIO_VERIFIER_SLOT)
                ),
                user_id=record.user_id,
                run_id=record.run_id,
                station_name=setup.station_name,
            )
            if checked
            else None
        ),
        engine=engine,
        cast=setup.cast,
        tts_ledger=tracker,
    )


async def _cards_of(user_id: UUID) -> SelectedCardsReader:
    """The shared source readers, filling only the sections the radio permits."""
    async with get_db_context() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise LookupError("the listener's account is gone")
    return BriefingService(user).read_selected_cards


async def _embed_headlines(texts: list[str]) -> list[list[float]]:
    """The platform's embedding of headlines, resolved at the call.

    A door that cannot open (no key) blinds the reading, never the session; the
    cost lands on the run the session's tracker holds (the embedder records it).
    """
    return await get_memory_embeddings().aembed_documents(texts)


def _antenna(
    record: RadioSessionRecord,
    setup: RadioSetup,
    *,
    crew: AntennaCrew,
    cards: SelectedCardsReader,
    redis: Any,
    aired: RedisAiredLedger,
) -> Antenna:
    def clock() -> datetime:
        return datetime.now(UTC)

    tz = ZoneInfo(setup.timezone)
    listener_day = ListenerDay(
        user_id=record.user_id,
        tz=tz,
        disabled_sources=setup.disabled_sources,
        public_mode=setup.public_mode,
        journal_frequency=setup.frequencies.get(
            RadioFormat.JOURNAL, FORMAT_SPECS[RadioFormat.JOURNAL].default_frequency
        ),
        cards=cards,
        readers=OWN_READERS,
        done_readers=DONE_READERS,
        ahead_readers=AHEAD_READERS,
        horizon_s=settings.radio_desk_ttl_seconds,
        record=recorder_for(record.user_id, record.run_id),
        clock=clock,
    )
    return Antenna(
        setup=AntennaSetup(
            session_id=record.session_id,
            media_root=radio_media_root(),
            timezone=tz,
            language=setup.language,
            station_name=setup.station_name,
            listener_name=setup.listener_name,
            checked=checked_formats(setup.verification),
            analysis_min_points=settings.radio_analysis_min_points,
            analysis_max_points=settings.radio_analysis_max_points,
            desk_ttl_s=settings.radio_desk_ttl_seconds,
            same_event_similarity=settings.radio_same_event_similarity,
            limits=production_limits(),
        ),
        crew=crew,
        day=CollectedDay(listener_day, record.run_id),
        news=NewsDesk(
            user_id=record.user_id,
            run_id=record.run_id,
            disabled_feeds=setup.disabled_feeds,
            clock=clock,
        ),
        aired=aired,
        headlines=RedisHeadlineVectors(
            redis,
            embed=_embed_headlines,
            model=settings.memory_embedding_model,
            dimensions=settings.memory_embedding_dimensions,
        ),
        clock=clock,
    )


@asynccontextmanager
async def session_parts(record: RadioSessionRecord, setup: RadioSetup) -> AsyncIterator[LoopParts]:
    """The parts of one session's loop — the runner's ``LoopFactory``.

    The session's tracker and its voice client live exactly as long as the loop:
    the tracker files what is left when the loop ends, the client is closed on
    every path.

    Args:
        record: The session.
        setup: Its frozen setup.

    Yields:
        The producer (committing after each production), what is available, and
        whether a spending ceiling refuses the next production.
    """
    config = await get_tts_config(RADIO_VOICE_SLOT)
    client = get_tts_client_sync(config, strict=True, records_tokens=True)
    try:
        cards = await _cards_of(record.user_id)
        redis = await get_redis_cache()
        async with TrackingContext(record.run_id, record.user_id, record.run_id, None) as tracker:
            engine = VoiceEngine(
                client=client,
                model=config.model,
                phrases=load_style_phrases(read_prompt_file(DELIVERY_LINES)),
                base_voice_settings=config.voice_settings or None,
            )
            crew = _crew(record, setup, engine=engine, tracker=tracker)
            # One ledger: the antenna reads what was heard, the loop files what is heard.
            aired = _aired_ledger(redis, record.user_id)
            antenna = _antenna(record, setup, crew=crew, cards=cards, redis=redis, aired=aired)

            async def blocked() -> bool:
                # The account's ceilings, then the radio's own day (ADR-324 decision 37).
                return await radio_spend_blocked(record.user_id, now=datetime.now(UTC))

            # The listener's interests, searched beside the loop with their own key: the
            # stories reach the desk at its next reading (decision 40).
            interests = asyncio.create_task(
                refresh_listener_interests(
                    record.user_id,
                    run_id=record.run_id,
                    topics=setup.interests,
                    language=setup.language,
                    redis=redis,
                    now=datetime.now(UTC),
                )
            )
            try:
                yield LoopParts(
                    producer=AccountedProducer(antenna, tracker),
                    available=antenna.available,
                    spend_blocked=blocked,
                    aired=aired,
                    flashes=flash_source(record, setup),
                )
            finally:
                interests.cancel()
                # It never raises: all that is left to hear is its cancellation.
                with suppress(asyncio.CancelledError):
                    await interests
    finally:
        await client.close()


# --- The cost ---------------------------------------------------------------------------


class LedgerCostReader:
    """What a session has cost so far: its run's row, every family (ADR-272)."""

    async def cost_eur(self, run_id: str) -> float | None:
        """The run's billed total; 0.0 before its first production is filed."""
        async with get_db_context() as db:
            summary = await ChatRepository(db).get_token_summary_by_run_id(run_id)
        return 0.0 if summary is None else float(summary.billed_cost_eur)


__all__ = [
    "NEWS_CANDIDATES_READ_MAX",
    "RADIO_ANALYST_SLOT",
    "RADIO_VERIFIER_SLOT",
    "RADIO_VOICE_SLOT",
    "RADIO_WRITER_SLOT",
    "AccountSetupBuilder",
    "AccountedProducer",
    "CollectedDay",
    "LedgerCostReader",
    "NewsDesk",
    "RadioEngine",
    "SpendFiler",
    "aired_ledger",
    "bound_call",
    "radio_engine",
    "radio_engine_key",
    "session_parts",
]
