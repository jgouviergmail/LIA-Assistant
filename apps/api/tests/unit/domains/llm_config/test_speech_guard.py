"""The typed speech port fails closed when a caller bypasses API composition."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BaseAPIException
from src.domains.llm.models import LLMModelKindEnum
from src.domains.llm_config import speech_guard as module
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY

pytestmark = pytest.mark.unit


async def test_an_unwired_tts_write_is_refused_before_any_database_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "_guard", None)
    db = AsyncMock(spec=AsyncSession)
    with pytest.raises(BaseAPIException) as refusal:
        await module.authorize_speech(db, "voice_tts", LLM_DEFAULTS["voice_tts"])
    assert refusal.value.status_code == 503
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_an_unwired_speech_port_does_not_block_other_model_kinds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "_guard", None)
    slot = next(
        key
        for key, value in LLM_TYPES_REGISTRY.items()
        if value.required_kind is LLMModelKindEnum.chat
    )
    db = AsyncMock(spec=AsyncSession)
    await module.authorize_speech(db, slot, LLM_DEFAULTS[slot])
    db.execute.assert_not_awaited()
