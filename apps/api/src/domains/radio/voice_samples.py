"""Hear the voice of a radio role against the complete settings draft."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import VOICE_ID_MAX_CHARS
from src.domains.radio.adapters import RADIO_VOICE_SLOT
from src.domains.radio.budget import listener_budget
from src.domains.radio.cast import cast_voices, shared_voice
from src.domains.radio.errors import (
    BUDGET_REACHED,
    NO_VOICE,
    VOICE_SHARED,
    VOICE_UNKNOWN,
    refuse,
)
from src.domains.radio.formats import RadioRole
from src.domains.voice.engine_voices import EngineVoices, usable_voices
from src.domains.voice.factory import get_tts_config
from src.domains.voice.sample_schemas import VoiceSampleResponse
from src.domains.voice.samples import synthesize_sample

VoiceId = Annotated[str, Field(min_length=1, max_length=VOICE_ID_MAX_CHARS, pattern=r"\S")]


class RadioVoiceSampleRequest(BaseModel):
    """The current draft distribution; an omitted role is resolved automatically."""

    model_config = ConfigDict(extra="forbid")
    role: RadioRole
    voices: dict[RadioRole, VoiceId] = Field(default_factory=dict)


async def sample_radio_voice(
    *, user_id: UUID, language: str, role: RadioRole, voices: dict[RadioRole, str]
) -> VoiceSampleResponse:
    """Hear the exact role's draft voice, including the cast's automatic assignment."""
    config = await get_tts_config(RADIO_VOICE_SLOT)
    if config.is_paid:
        budget = await listener_budget(user_id, now=datetime.now(UTC))
        if budget.reached:
            refuse(
                BUDGET_REACHED,
                max_eur=budget.limit_eur,
                lifts_at=budget.lifts_at.isoformat() if budget.lifts_at else None,
            )

    def choose(engine: EngineVoices) -> str:
        if not engine.voices:
            refuse(NO_VOICE)
        offered = usable_voices(engine.voices, language, engine.multilingual)
        if not set(voices.values()) <= {voice.voice_id for voice in offered}:
            refuse(VOICE_UNKNOWN)
        if shared_voice(voices):
            refuse(VOICE_SHARED)
        cast = cast_voices(
            engine.voices, voices, language=language, multilingual=engine.multilingual
        )
        if cast is None:
            refuse(NO_VOICE)
        return cast.voices[role]

    # The radio budget's ledger query includes every run with the radio_ prefix.
    return await synthesize_sample(
        user_id=user_id,
        language=language,
        config=config,
        choose=choose,
        run_prefix="radio_voice_sample",
    )
