"""Committed Fish Audio references: one query, the runtime's own slot parser."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import FISHAUDIO_PROVIDER_NAME
from src.core.llm_config_helper import merge_config
from src.domains.llm.models import LLMModelKindEnum
from src.domains.llm_config.cache import OVERRIDE_FIELDS
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
from src.domains.llm_config.models import LLMConfigOverride
from src.domains.voice.factory import tts_config_from_effective


async def slots_by_voice(db: AsyncSession) -> dict[str, list[str]]:
    """Read references on the caller's short transaction, optionally under its lock."""
    slots = sorted(
        slot
        for slot, metadata in LLM_TYPES_REGISTRY.items()
        if metadata.required_kind is LLMModelKindEnum.tts
    )
    result = await db.execute(
        select(LLMConfigOverride).where(LLMConfigOverride.llm_type.in_(slots))
    )
    overrides = {
        row.llm_type: {
            field: value for field in OVERRIDE_FIELDS if (value := getattr(row, field)) is not None
        }
        for row in result.scalars()
    }
    speaking: dict[str, list[str]] = {}
    for slot in slots:
        config = tts_config_from_effective(
            merge_config(LLM_DEFAULTS[slot], overrides.get(slot, {}))
        )
        if config.provider == FISHAUDIO_PROVIDER_NAME:
            for voice_id in {config.voice_male, config.voice_female}:
                speaking.setdefault(voice_id, []).append(slot)
    return speaking
