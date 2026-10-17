"""Bounded TTS samples: one fixed sentence, the chosen voice and its actual cost.

The client is built immediately before reading its catalogue: both capture the
same configured provider credential before the first await. A later reload never
hands account A's catalogue to a client built on account B's key. This service
adds no synthesis retry, writes no preferences and sends no sentence to the chat.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, NoReturn
from uuid import UUID, uuid4

import structlog

from src.core.exceptions import BaseAPIException
from src.core.i18n_voice_samples import voice_sample_phrase
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.chat.service import TrackingContext
from src.domains.voice.audio_output import mix_audio_format, playable_base64
from src.domains.voice.engine_voices import EngineVoices, offered_engine, usable_voices
from src.domains.voice.exceptions import TTSProviderError, tts_failure_facts
from src.domains.voice.factory import TTSConfig, get_tts_config, serve_tts, served_config
from src.domains.voice.lia_voices import (
    LIA_VOICE_CATALOGUE_UNAVAILABLE,
    LIA_VOICE_UNKNOWN,
    Gender,
)
from src.domains.voice.protocol import TTSClient
from src.domains.voice.sample_schemas import VoiceSampleResponse
from src.domains.voice.schemas import AUDIO_MIME_TYPES, DEFAULT_AUDIO_MIME_TYPE
from src.domains.voice.spoken import speak
from src.infrastructure.llm.usage_guard import enforce_usage_limit

logger = structlog.get_logger(__name__)

VOICE_SAMPLE_RATE_MAX_CALLS: Final[int] = 12
VOICE_SAMPLE_RATE_WINDOW_SECONDS: Final[int] = 60
# One user bucket shared by the chat and radio settings; the existing limiter
# authenticates without keeping a request SQL session while synthesis waits.
rate_limit_voice_sample = create_user_rate_limiter(
    action="voice_sample",
    max_calls=VOICE_SAMPLE_RATE_MAX_CALLS,
    window_seconds=VOICE_SAMPLE_RATE_WINDOW_SECONDS,
    authenticate=get_current_active_session_for_stream,
)


def refuse_sample(code: str, *, status_code: int = 503) -> NoReturn:
    """Refuse a sample with a stable, translatable code."""
    raise BaseAPIException(
        status_code=status_code,
        detail={"code": code},
        code=code,
        log_level="info" if status_code < 500 else "warning",
        log_event="voice_sample_refused",
    )


async def synthesize_sample(
    *,
    user_id: UUID,
    language: str,
    config: TTSConfig,
    choose: Callable[[EngineVoices], str],
    run_prefix: str,
) -> VoiceSampleResponse:
    """Authorize a voice against its engine, synthesize once and file its cost.

    ``choose`` is the caller's pure selection rule (a gender's default, or the
    radio's cast); it runs against the exact catalogue of the client that speaks.
    The caller enforces its capability and any surface-specific spending bound.
    """
    client: TTSClient | None = None
    run_id = f"{run_prefix}_{uuid4().hex}"
    try:
        # No await between these captures: every client and offered_engine
        # captures the provider key synchronously before its first external I/O.
        client = serve_tts(config, strict=True).client
        engine = await offered_engine(config)
        voice_id = choose(engine)
        if config.is_paid:
            await enforce_usage_limit(user_id, layer="voice_sample")
        async with TrackingContext(
            run_id=run_id,
            user_id=user_id,
            session_id=f"{run_prefix}_{user_id}",
            conversation_id=None,
        ) as tracker:
            result = await speak(
                client,
                voice_sample_phrase(language),
                voice_id,
                model=config.model,
                ledger=tracker if config.is_paid else None,
            )
            # The provider has billed this response even if local wrapping fails.
            if config.is_paid:
                await tracker.commit()
            if not result.audio:
                refuse_sample("voice_sample_failed")
            return VoiceSampleResponse(
                audio_base64=playable_base64(client, result.audio),
                mime_type=AUDIO_MIME_TYPES.get(mix_audio_format(client), DEFAULT_AUDIO_MIME_TYPE),
                voice_id=voice_id,
            )
    except TTSProviderError as error:
        logger.warning("voice_sample_provider_failed", **tts_failure_facts(error))
        refuse_sample("voice_sample_failed")
    finally:
        try:
            if client is not None:
                await client.close()
        finally:
            TrackingContext.cleanup_run_records(run_id)


async def sample_lia_voice(
    *, user_id: UUID, language: str, gender: Gender, voice_id: str | None
) -> VoiceSampleResponse:
    """Hear an explicit chat voice, or the actual default for the requested gender."""
    config = served_config(await get_tts_config())

    def choose(engine: EngineVoices) -> str:
        if voice_id is None:
            return config.voice_male if gender == "male" else config.voice_female
        if not engine.voices:
            refuse_sample(LIA_VOICE_CATALOGUE_UNAVAILABLE)
        offered = usable_voices(engine.voices, language, engine.multilingual)
        if voice_id not in {voice.voice_id for voice in offered}:
            refuse_sample(LIA_VOICE_UNKNOWN, status_code=422)
        return voice_id

    return await synthesize_sample(
        user_id=user_id, language=language, config=config, choose=choose, run_prefix="voice_sample"
    )
