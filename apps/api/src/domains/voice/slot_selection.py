"""A voice slot cannot acquire a library voice while that voice is being removed."""

from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import FISHAUDIO_PROVIDER_NAME
from src.core.exceptions import BaseAPIException, raise_structured_validation_error
from src.core.llm_agent_config import LLMAgentConfig
from src.domains.llm.models import LLMModelKindEnum
from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.domains.llm_config.credential_fence import credential_is_current
from src.domains.llm_config.speech_guard import VoiceSelection
from src.domains.voice import engine_voices
from src.domains.voice.factory import tts_config_from_effective
from src.domains.voice.fishaudio.catalogue_revision import (
    current_revision,
    lock_catalogue,
    pending_removals,
)


class LibrarySpeechGuard:
    """Stateless implementation installed by the API's composition root."""

    async def prepare(
        self, db: AsyncSession, slot: str, effective: LLMAgentConfig
    ) -> VoiceSelection | None:
        return await prepare_selection(db, slot, effective)

    async def fence(self, db: AsyncSession, slot: str, selection: VoiceSelection | None) -> None:
        await fence_selection(db, slot, selection)


def _refuse_voice() -> NoReturn:
    raise_structured_validation_error(
        error_type="fishaudio_voice_unavailable",
        loc=["body", "provider_config"],
        msg="The selected Fish Audio voice is no longer available; refresh the voice list.",
        input_value=None,
        ctx={},
    )


async def prepare_selection(
    db: AsyncSession, slot: str, effective: LLMAgentConfig
) -> VoiceSelection | None:
    """Read a catalogue with the request session returned before its vendor waits."""
    if LLM_TYPES_REGISTRY[slot].required_kind is not LLMModelKindEnum.tts:
        return None
    if effective.provider != FISHAUDIO_PROVIDER_NAME:
        return None
    config = tts_config_from_effective(effective)
    await db.commit()
    engine = await engine_voices.offered_engine(config)
    if not engine.voices:
        raise BaseAPIException(
            status_code=503,
            detail={
                "code": "lia_voice_catalogue_unavailable",
                "type": "lia_voice_catalogue_unavailable",
            },
            log_level="warning",
            log_event="voice_slot_catalogue_unavailable",
        )
    voices = frozenset({config.voice_male, config.voice_female})
    if not voices.issubset(voice.voice_id for voice in engine.voices):
        _refuse_voice()
    return VoiceSelection(engine.catalogue_revision, voices, engine.credential_fingerprint)


async def fence_selection(db: AsyncSession, slot: str, selection: VoiceSelection | None) -> None:
    """Serialize the final slot write with removal's committed reservation."""
    if LLM_TYPES_REGISTRY[slot].required_kind is not LLMModelKindEnum.tts:
        return
    await lock_catalogue(db)
    if selection is None:
        return
    if await current_revision(db) != selection.revision:
        _refuse_voice()
    if not await credential_is_current(
        db, FISHAUDIO_PROVIDER_NAME, selection.credential_fingerprint
    ):
        _refuse_voice()
    if selection.voices.intersection(await pending_removals(db)):
        _refuse_voice()
