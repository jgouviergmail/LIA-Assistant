"""The voices LIA speaks with for one person (ADR-345 amendment 2026-10-14).

A person chooses LIA's male and female voice in the voice mode settings, among
the voices of the engine that speaks in the chat — the ``voice_tts`` slot's, or
Edge's when that engine cannot be served. The choice is kept PER PROVIDER
(:func:`~src.domains.voice.engine_voices.choice_key`): a model switched for
another keeps it, and a provider switched back to finds the voices chosen on it
(kept per provider and model before 2026-10-16 — those entries are still read,
:func:`~src.domains.voice.engine_voices.stored_choice`). It applies where LIA
speaks in the chat — its voice comments and the read-aloud — never the radio
(its roles have their own), a live session or a phone call (their voices are
the provider's). A gender with no choice speaks with the instance's voice.

- WRITTEN strictly: a voice the engine does not offer in the person's language
  is refused (``lia_voice_unknown``); an engine that cannot list its voices
  refuses a selection until it can verify it. Returning to defaults remains available.
- READ forgivingly, by the page and before LIA speaks: a choice the engine no
  longer offers in the person's language reads as the instance's voice; an
  engine that cannot list its voices right now keeps the choice (it cannot
  tell). Before LIA speaks, the list is the one known WITHOUT asking the vendor
  — a shipped list or a cache every account of the instance shares — because a
  cold Fish Audio listing took 6.8-9.2 s on dev: a voice turn never waits on it,
  and a catalogue not cached yet keeps the choice.
- STORED by one atomic statement as a new mapping: two saves never lose each
  other's provider, no row is read and then written back, and the entries an
  older release kept per model for that provider go with the save.
- FORGOTTEN when the voice is: deleting a voice from the instance's library
  gives every person who chose it the instance's voice back — the one way a
  voice disappears that LIA performs itself.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, NoReturn, get_args
from uuid import UUID

import structlog
from fastapi import status
from sqlalchemy import ColumnElement, Text, case, cast, func, literal, select, text, update
from sqlalchemy.dialects.postgresql import JSONB

from src.core.constants import FISHAUDIO_PROVIDER_NAME, VOICE_ID_MAX_CHARS
from src.core.exceptions import BaseAPIException, raise_user_inactive
from src.core.sql_search import LIKE_ESCAPE, escape_like
from src.domains.llm_config.credential_fence import credential_is_current
from src.domains.users.models import User
from src.domains.voice.engine_voices import (
    LIVE_CATALOGUES,
    EngineVoices,
    choice_key,
    known_engine,
    offered_engine,
    stored_choice,
    usable_voices,
)
from src.domains.voice.factory import TTSConfig, get_tts_config, served_config
from src.domains.voice.fishaudio.catalogue_revision import (
    advance_revision,
    current_revision,
    lock_catalogue,
    pending_removals,
)
from src.domains.voice.voices_catalog import VoiceOption
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

#: LIA's two voices, as the avatar's gender picks one.
Gender = Literal["male", "female"]
GENDERS: Final[tuple[Gender, ...]] = get_args(Gender)

#: The refusal a write of a voice the engine does not offer receives.
LIA_VOICE_UNKNOWN: Final[str] = "lia_voice_unknown"
LIA_VOICE_CATALOGUE_UNAVAILABLE: Final[str] = "lia_voice_catalogue_unavailable"

_EMPTY_OBJECT = cast(literal("{}"), JSONB)

# Correlate to the UPDATE's target row, not a precomputed candidate snapshot:
# PostgreSQL must derive this value again after waiting for a concurrent writer.
_WITHOUT_VOICE_SQL = """(
    SELECT jsonb_object_agg(engine.key, kept.voices)
    FROM jsonb_each(
        CASE WHEN jsonb_typeof(account.lia_voices) = 'object'
             THEN account.lia_voices ELSE '{}'::jsonb END
    ) AS engine
    CROSS JOIN LATERAL (
        SELECT jsonb_object_agg(voice.key, voice.value) AS voices
        FROM jsonb_each(
            CASE WHEN jsonb_typeof(engine.value) = 'object'
                 THEN engine.value ELSE '{}'::jsonb END
        ) AS voice
        WHERE jsonb_typeof(voice.value) = 'string'
          AND voice.value <> to_jsonb(CAST(:voice_id AS text))
    ) AS kept
    WHERE kept.voices IS NOT NULL
)"""
_FORGET_VOICE_SQL = text(f"""
    WITH changed AS (
        UPDATE users AS account
        SET lia_voices = {_WITHOUT_VOICE_SQL}, updated_at = now()
        WHERE account.lia_voices IS NOT NULL
          AND CAST(account.lia_voices AS text) LIKE :holding ESCAPE :like_escape
          AND account.lia_voices IS DISTINCT FROM {_WITHOUT_VOICE_SQL}
        RETURNING 1
    )
    SELECT count(*) FROM changed
    """)


@dataclass(frozen=True, slots=True)
class LiaVoices:
    """What the voice mode settings show: the engine, its voices, the person's choice.

    Attributes:
        engine: The engine that speaks in the chat, with its whole catalogue.
        voices: The voices the person may choose (their language's rule applied).
        chosen: Their choice for each gender, as it reads (a voice no longer
            offered is left out).
        defaults: The instance's voice for each gender, named as the catalogue
            names it (its id when the catalogue does not hold it).
    """

    engine: EngineVoices
    voices: list[VoiceOption]
    chosen: dict[Gender, str]
    defaults: dict[Gender, VoiceOption]


def choice_on(stored: object, key: str) -> dict[Gender, str]:
    """The voices a person chose for the engine in place, each gender read forgivingly.

    Args:
        stored: The ``users.lia_voices`` column as stored.
        key: The key the engine's voices are kept under (``EngineVoices.key``, its
            provider); an entry an older release kept per model is read too.

    Returns:
        A voice per gender chosen; anything else names no voice.
    """
    return stored_choice(stored, key, _genders)


def _genders(raw: object) -> dict[Gender, str]:
    """One entry's voices, each gender read forgivingly."""
    if not isinstance(raw, Mapping):
        return {}
    return {
        gender: voice
        for gender in GENDERS
        if isinstance(voice := raw.get(gender), str) and _well_formed(voice)
    }


def _well_formed(voice: str) -> bool:
    return bool(voice.strip()) and len(voice) <= VOICE_ID_MAX_CHARS


def gender_of(value: str) -> Gender | None:
    """``value`` as one of LIA's genders, or ``None`` for anything else."""
    return next((gender for gender in GENDERS if gender == value), None)


def _offered_to(engine: EngineVoices, language: str) -> list[VoiceOption]:
    return usable_voices(engine.voices, language, engine.multilingual)


def kept(
    choice: Mapping[Gender, str], engine: EngineVoices, offered: list[VoiceOption]
) -> dict[Gender, str]:
    """The part of ``choice`` the engine still offers — all of it when it cannot tell.

    Args:
        choice: A voice per gender.
        engine: The engine, with its catalogue (empty when it could not be read).
        offered: The voices the person may choose on it.

    Returns:
        The choices still offered.
    """
    if not engine.voices:
        return dict(choice)
    ids = {voice.voice_id for voice in offered}
    return {gender: voice for gender, voice in choice.items() if voice in ids}


async def _stored(user_id: UUID) -> object:
    async with get_db_context() as db:
        return await db.scalar(select(User.lia_voices).where(User.id == user_id))


async def chat_engine() -> EngineVoices:
    """The engine that speaks in the chat, with its catalogue."""
    return await offered_engine(served_config(await get_tts_config()))


def _default(engine: EngineVoices, gender: Gender) -> VoiceOption:
    voice_id = engine.config.voice_male if gender == "male" else engine.config.voice_female
    named = next((voice for voice in engine.voices if voice.voice_id == voice_id), None)
    return named or VoiceOption(voice_id=voice_id, label=voice_id, gender=gender)


async def lia_voices(user_id: UUID, language: str) -> LiaVoices:
    """What the voice mode settings show the person.

    Args:
        user_id: The person.
        language: Their stored language.

    Returns:
        The engine, the voices offered, the choice as it reads and the defaults.
    """
    engine = await chat_engine()
    offered = _offered_to(engine, language)
    return LiaVoices(
        engine=engine,
        voices=offered,
        chosen=kept(choice_on(await _stored(user_id), engine.key), engine, offered),
        defaults={gender: _default(engine, gender) for gender in GENDERS},
    )


def _refuse_unknown() -> NoReturn:
    raise BaseAPIException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": LIA_VOICE_UNKNOWN},
        log_level="info",
        log_event="lia_voice_refused",
        code=LIA_VOICE_UNKNOWN,
    )


async def save_lia_voices(user_id: UUID, language: str, choice: Mapping[Gender, str]) -> LiaVoices:
    """Keep the person's voices for the engine that speaks — strictly offered ones.

    Args:
        user_id: The person.
        language: Their stored language.
        choice: A voice per gender chosen (a gender left out speaks with the
            instance's voice).

    Returns:
        What the settings show once it is stored.

    Raises:
        BaseAPIException: 422 ``lia_voice_unknown`` for a voice the engine does
            not offer in the person's language; 503 when its catalogue cannot
            authorize a selection; 403 when the account can no longer write.
    """
    engine = await chat_engine()
    offered = _offered_to(engine, language)
    if choice and not engine.voices:
        raise BaseAPIException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": LIA_VOICE_CATALOGUE_UNAVAILABLE},
            log_level="warning",
            log_event="lia_voice_catalogue_unavailable",
            code=LIA_VOICE_CATALOGUE_UNAVAILABLE,
        )
    if kept(choice, engine, offered) != dict(choice):
        _refuse_unknown()
    await _write(
        user_id,
        engine.key,
        choice,
        catalogue_revision=engine.catalogue_revision,
        credential_fingerprint=engine.credential_fingerprint,
    )
    return LiaVoices(
        engine=engine,
        voices=offered,
        chosen=dict(choice),
        defaults={gender: _default(engine, gender) for gender in GENDERS},
    )


def _without_provider(provider: str) -> ColumnElement[Any]:
    """The stored mapping without ``provider``'s entries — its own and those an older
    release kept per model (``provider/model``), whose part before the slash is the
    provider: the same rule as ``engine_voices.holds_choice_of``.

    A scalar subquery on the row the UPDATE targets, never a snapshot read before
    it, so PostgreSQL derives it again after waiting for a concurrent writer; a
    column that does not hold an object (an early shape) reads as empty.
    """
    current = case(
        (func.jsonb_typeof(User.lia_voices) == "object", User.lia_voices), else_=_EMPTY_OBJECT
    )
    entry = func.jsonb_each(current).table_valued("key", "value")
    return (
        select(func.coalesce(func.jsonb_object_agg(entry.c.key, entry.c.value), _EMPTY_OBJECT))
        .where(func.split_part(entry.c.key, "/", 1) != provider)
        .scalar_subquery()
    )


async def _write(
    user_id: UUID,
    provider: str,
    choice: Mapping[Gender, str],
    *,
    catalogue_revision: UUID | None = None,
    credential_fingerprint: str | None = None,
) -> None:
    """Replace one provider's voices in one statement; every other provider's stay.

    Args:
        user_id: The person.
        provider: The key the voices are kept under (``EngineVoices.key``).
        choice: A voice per gender (none: both back to the instance's).
        catalogue_revision: The Fish Audio catalogue generation the choice was
            checked against.
        credential_fingerprint: The live catalogue's key the choice was checked with.

    Raises:
        BaseAPIException: 422 ``lia_voice_unknown`` when the catalogue moved since
            the choice was checked; 403 when the account can no longer write.
    """
    others = _without_provider(provider)
    value: ColumnElement[Any]
    if choice:
        entry = func.jsonb_build_object(
            cast(literal(provider), Text), cast(literal(json.dumps(dict(choice))), JSONB)
        )
        value = others.op("||")(entry)
    else:
        value = func.nullif(others, _EMPTY_OBJECT)
    async with get_db_context() as db:
        if choice and provider == FISHAUDIO_PROVIDER_NAME:
            await lock_catalogue(db)
            if await current_revision(db) != catalogue_revision:
                _refuse_unknown()
            if set(choice.values()).intersection(await pending_removals(db)):
                _refuse_unknown()
        if choice and provider in LIVE_CATALOGUES:
            if not await credential_is_current(db, provider, credential_fingerprint):
                _refuse_unknown()
        written = await db.scalar(
            update(User)
            .where(User.id == user_id, User.is_active, User.deleted_at.is_(None))
            .values(lia_voices=value)
            .returning(User.id)
        )
        if written is None:
            raise_user_inactive(user_id)


async def spoken_voice(
    user_id: str | None, config: TTSConfig, gender: str, language: str
) -> str | None:
    """The voice the person chose for LIA's ``gender`` on the engine that speaks.

    Args:
        user_id: The person (``None`` for an anonymous synthesis).
        config: The configuration of the client that speaks.
        gender: LIA's gender, as the avatar sets it.
        language: The language LIA speaks in.

    Returns:
        Their voice, or ``None`` for the instance's: no choice, or a choice the
        engine no longer offers them (a catalogue not known yet keeps it).
    """
    wanted = gender_of(gender)
    if user_id is None or wanted is None:
        return None
    stored = await _stored(UUID(user_id))
    voice = choice_on(stored, choice_key(config.provider)).get(wanted)
    if voice is None:
        return None
    # Never the vendor: a catalogue not cached yet keeps the choice (it cannot tell).
    engine = await known_engine(config)
    if engine is None:
        return voice
    return kept({wanted: voice}, engine, _offered_to(engine, language)).get(wanted)


def without_voice(stored: object, voice_id: str) -> dict[str, dict[str, str]] | None:
    """The stored voices once ``voice_id`` is gone — every other choice kept.

    Args:
        stored: The ``users.lia_voices`` column as stored.
        voice_id: The voice that no longer exists.

    Returns:
        A new mapping, or ``None`` when no choice is left.
    """
    if not isinstance(stored, Mapping):
        return None
    remaining: dict[str, dict[str, str]] = {}
    for engine, choice in stored.items():
        if not isinstance(engine, str) or not isinstance(choice, Mapping):
            continue
        voices = {
            gender: voice
            for gender, voice in choice.items()
            if isinstance(gender, str) and isinstance(voice, str) and voice != voice_id
        }
        if voices:
            remaining[engine] = voices
    return remaining or None


async def forget_voice(voice_id: str) -> int:
    """Give every person who chose ``voice_id`` the instance's voice back.

    Args:
        voice_id: A voice the instance's library just deleted.

    Returns:
        How many accounts had chosen it.
    """
    holding = f'%"{escape_like(voice_id)}"%'
    async with get_db_context() as db:
        await lock_catalogue(db)
        await advance_revision(db)
        forgotten: int = await db.scalar(
            _FORGET_VOICE_SQL,
            {"voice_id": voice_id, "holding": holding, "like_escape": LIKE_ESCAPE},
        )
    if forgotten:
        logger.info("lia_voice_forgotten", voice_id=voice_id, accounts=forgotten)
    return forgotten


__all__ = [
    "GENDERS",
    "LIA_VOICE_UNKNOWN",
    "LIA_VOICE_CATALOGUE_UNAVAILABLE",
    "Gender",
    "LiaVoices",
    "chat_engine",
    "choice_on",
    "forget_voice",
    "gender_of",
    "kept",
    "lia_voices",
    "save_lia_voices",
    "spoken_voice",
    "without_voice",
]
