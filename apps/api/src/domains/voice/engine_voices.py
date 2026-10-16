"""The voices of a speech engine, as a person may be offered them (ADR-324, ADR-345).

One reader for every surface where someone chooses a voice — the radio's roles
and the chat's two voices:

- the engine's catalogue: a list shipped with the client (Edge, OpenAI, Gemini),
  or the vendor ACCOUNT's live one (ElevenLabs; Fish Audio, with the instance's
  pinned voices);
- whether its voices speak every language (its family says so);
- the rule that orders or narrows them for a person's language;
- the key a person's choice is kept under — the slot's PROVIDER, whose catalogue
  every model of it shares: a model switched for another keeps the voices chosen,
  and a provider switched back to finds its own (:func:`choice_key`). A release
  before 2026-10-16 kept them per provider AND model, so every model change of the
  radio's slot (fourteen on one instance in eighteen days) handed the listener other
  voices; those entries are still read (:func:`stored_choice`) and replaced at the
  next save (:func:`holds_choice_of`).

A live catalogue that cannot be read offers no voice rather than raising: an empty
list is the caller's to read (a settings page offers « automatic » alone, a stored
choice is read forgivingly, since nothing can tell it is gone). A live catalogue is
also known WITHOUT asking its vendor, as its cache holds it (:func:`known_engine`):
what the speaking path reads, since a cold Fish Audio listing took 6.8-9.2 s on
dev (2026-10-14) — a voice turn never waits on it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final
from uuid import UUID

import structlog

from src.core.constants import (
    DEFAULT_ELEVENLABS_BASE_URL,
    ELEVENLABS_PROVIDER_NAME,
    FISHAUDIO_PROVIDER_NAME,
)
from src.core.i18n_types import canonical_language
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.credential_fence import credential_fingerprint
from src.domains.voice.factory import TTSConfig
from src.domains.voice.families import family_of
from src.domains.voice.fishaudio.catalogue_revision import catalogue_revision
from src.domains.voice.fishaudio.pins import read_pins
from src.domains.voice.fishaudio.voices import FishVoicesError, get_fish_voices, peek_fish_voices
from src.domains.voice.voices_catalog import (
    ElevenLabsVoicesError,
    VoiceOption,
    get_cached_elevenlabs_voices,
    get_edge_voices,
    get_gemini_voices,
    get_openai_voices,
    peek_elevenlabs_voices,
)

logger = structlog.get_logger(__name__)

#: The engines whose voice list is fixed and shipped with the client.
STATIC_CATALOGUES: Final[dict[str, Callable[[], list[VoiceOption]]]] = {
    "edge": get_edge_voices,
    "openai": get_openai_voices,
    "gemini": get_gemini_voices,
}


async def _elevenlabs_voices(config: TTSConfig, api_key: str) -> list[VoiceOption]:
    return await get_cached_elevenlabs_voices(api_key, DEFAULT_ELEVENLABS_BASE_URL)


async def _fishaudio_voices(config: TTSConfig, api_key: str) -> list[VoiceOption]:
    # The pins are read (a short session of their own) before the vendor is asked.
    return await get_fish_voices(api_key, await read_pins())


#: The engines whose voice list belongs to the vendor ACCOUNT, read live.
LIVE_CATALOGUES: Final[dict[str, Callable[[TTSConfig, str], Awaitable[list[VoiceOption]]]]] = {
    ELEVENLABS_PROVIDER_NAME: _elevenlabs_voices,
    FISHAUDIO_PROVIDER_NAME: _fishaudio_voices,
}


async def _elevenlabs_known(config: TTSConfig) -> list[VoiceOption] | None:
    api_key = LLMConfigOverrideCache.get_api_key(ELEVENLABS_PROVIDER_NAME) or ""
    return await peek_elevenlabs_voices(api_key)


async def _fishaudio_known(config: TTSConfig) -> list[VoiceOption] | None:
    api_key = LLMConfigOverrideCache.get_api_key(FISHAUDIO_PROVIDER_NAME) or ""
    return await peek_fish_voices(api_key, await read_pins())


#: The same live catalogues as their caches hold them: ``None`` while none is cached.
KNOWN_LIVE_CATALOGUES: Final[
    dict[str, Callable[[TTSConfig], Awaitable[list[VoiceOption] | None]]]
] = {
    ELEVENLABS_PROVIDER_NAME: _elevenlabs_known,
    FISHAUDIO_PROVIDER_NAME: _fishaudio_known,
}

# Every live catalogue can be known without its vendor (ADR-085: checked at import).
if set(KNOWN_LIVE_CATALOGUES) != set(LIVE_CATALOGUES):
    raise RuntimeError("every live voice catalogue needs its cache-only reader")


@dataclass(frozen=True, slots=True)
class EngineVoices:
    """The engine a voice slot names, and the voices it offers.

    Attributes:
        config: The slot's configuration.
        voices: Its voices, every language, in the catalogue's order.
        multilingual: Whether every voice speaks every language.
        catalogue_revision: The Fish Audio catalogue generation the voices were
            listed under (``None`` for every other provider).
        credential_fingerprint: Internal identity of the key used by a live catalogue.
    """

    config: TTSConfig
    voices: list[VoiceOption]
    multilingual: bool
    catalogue_revision: UUID | None = None
    credential_fingerprint: str | None = field(default=None, repr=False)

    @property
    def key(self) -> str:
        """The key a person's choice of its voices is kept under (:func:`choice_key`)."""
        return choice_key(self.config.provider)

    @property
    def name(self) -> str:
        """The engine as it is shown: its provider and model."""
        return f"{self.config.provider}/{self.config.model}"


def choice_key(provider: str) -> str:
    """The key a person's voices are kept under: the engine's provider.

    Every model of a provider offers the same voices — the catalogue is the
    provider's (:data:`STATIC_CATALOGUES`, :data:`LIVE_CATALOGUES`) — so a model
    switched for another keeps the voices chosen, and a provider switched back to
    finds its own.

    Args:
        provider: The voice slot's provider.

    Returns:
        The key.
    """
    return provider


def holds_choice_of(stored_key: str, key: str) -> bool:
    """Whether an entry stored under ``stored_key`` holds a choice for ``key``.

    Its own entry, or one a release before 2026-10-16 kept per model
    (``provider/model``): a writer replaces them all, so an older entry can never
    come back once the person chose again — or chose nothing.

    Args:
        stored_key: The key an entry is stored under.
        key: A choice key (:func:`choice_key`).

    Returns:
        Whether the entry is ``key``'s.
    """
    return stored_key == key or stored_key.startswith(f"{key}/")


def stored_choice[R](
    stored: object, key: str, read: Callable[[object], dict[R, str]]
) -> dict[R, str]:
    """A person's voices for ``key``, as stored.

    Its own entry when it holds a voice; else the fullest one a release before
    2026-10-16 kept per model (``provider/model``) — on a tie, the model whose name
    sorts last, the newer of two releases of one family.

    Args:
        stored: The mapping as stored (a choice key to that key's choice).
        key: A choice key (:func:`choice_key`).
        read: Reads one entry forgivingly (anything unreadable is no voice).

    Returns:
        The choice; empty when nothing readable is stored for ``key``.
    """
    if not isinstance(stored, Mapping):
        return {}
    own = read(stored.get(key))
    if own:
        return own
    fullest: dict[R, str] = {}
    older = sorted(name for name in stored if isinstance(name, str) and name != key)
    for name in older:
        if holds_choice_of(name, key):
            choice = read(stored[name])
            if len(choice) >= len(fullest):
                fullest = choice
    return fullest


async def engine_voices(config: TTSConfig, *, api_key: str | None = None) -> list[VoiceOption]:
    """The engine's voices: a shipped list, or the vendor account's live one.

    Args:
        config: The voice slot's configuration.
        api_key: The captured account key, or ``None`` to read the worker cache once.

    Returns:
        Its voices — none for a provider no catalogue serves, or a live list
        that could not be read.
    """
    static = STATIC_CATALOGUES.get(config.provider)
    if static is not None:
        return static()
    live = LIVE_CATALOGUES.get(config.provider)
    if live is None:
        return []
    if api_key is None:
        api_key = LLMConfigOverrideCache.get_api_key(config.provider) or ""
    try:
        return await live(config, api_key)
    except (ElevenLabsVoicesError, FishVoicesError) as error:
        # Its type says enough: the facts are the client's to log.
        logger.warning("voice_catalogue_unavailable", error_type=type(error).__name__)
        return []


def _engine(config: TTSConfig, voices: list[VoiceOption]) -> EngineVoices:
    family = family_of(config.provider)
    return EngineVoices(
        config=config, voices=voices, multilingual=bool(family and family.multilingual_voices)
    )


async def offered_engine(config: TTSConfig) -> EngineVoices:
    """The engine ``config`` names, with its voices and whether they speak every language."""
    # Capture ONCE, ahead of every await. A cache reload while the catalogue
    # answers must not tag account A's result with account B's credential.
    api_key = LLMConfigOverrideCache.get_api_key(config.provider) or ""
    fingerprint = credential_fingerprint(api_key) if config.provider in LIVE_CATALOGUES else None
    revision = await catalogue_revision() if config.provider == FISHAUDIO_PROVIDER_NAME else None
    engine = _engine(config, await engine_voices(config, api_key=api_key))
    return EngineVoices(engine.config, engine.voices, engine.multilingual, revision, fingerprint)


async def known_engine(config: TTSConfig) -> EngineVoices | None:
    """The engine with the voices known WITHOUT asking its vendor — what a voice turn reads.

    Args:
        config: The voice slot's configuration.

    Returns:
        The engine with its shipped list or its cached one; ``None`` while a live
        catalogue is not cached (whoever reads it next lists it).
    """
    static = STATIC_CATALOGUES.get(config.provider)
    if static is not None:
        return _engine(config, static())
    peek = KNOWN_LIVE_CATALOGUES.get(config.provider)
    if peek is None:
        return _engine(config, [])
    voices = await peek(config)
    return None if voices is None else _engine(config, voices)


def usable_voices(
    catalogue: Sequence[VoiceOption], language: str, multilingual: bool
) -> list[VoiceOption]:
    """The voices a person may be offered — what a settings page lists, and a write accepts.

    Args:
        catalogue: The engine's voices.
        language: The person's language.
        multilingual: Whether every voice of the engine speaks every language.

    Returns:
        Every voice for a multilingual engine — those native to the person's
        language first, then those that name no language, then the others, so
        a default speaks without an accent whenever the catalogue allows (a
        Fish Audio licensed voice is native to ONE language, ADR-345); else
        those of the person's language, or all of them when it has none (an
        accent beats no voice).
    """
    # Both sides through the one locale door: the catalogue says « zh », the
    # person « zh-CN », and only the canonical forms compare. A code the
    # product does not support names nothing (None) rather than the default
    # language, so a voice of another language never passes for the person's.
    wanted = canonical_language(language)
    matching = [
        voice
        for voice in catalogue
        if wanted is not None and canonical_language(voice.language) == wanted
    ]
    if multilingual:
        native = {voice.voice_id for voice in matching}
        neutral = [voice for voice in catalogue if voice.language is None]
        others = [
            voice
            for voice in catalogue
            if voice.voice_id not in native and voice.language is not None
        ]
        return [*matching, *neutral, *others]
    return matching or list(catalogue)


__all__ = [
    "KNOWN_LIVE_CATALOGUES",
    "LIVE_CATALOGUES",
    "STATIC_CATALOGUES",
    "EngineVoices",
    "choice_key",
    "engine_voices",
    "holds_choice_of",
    "known_engine",
    "offered_engine",
    "stored_choice",
    "usable_voices",
]
