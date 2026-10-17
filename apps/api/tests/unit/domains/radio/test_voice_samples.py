"""The exact draft cast and the radio's own budget also govern settings samples."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.radio import voice_samples as module
from src.domains.radio.budget import BudgetStatus
from src.domains.radio.cast import cast_voices
from src.domains.radio.formats import RadioRole
from src.domains.voice.engine_voices import EngineVoices
from src.domains.voice.factory import TTSConfig
from src.domains.voice.sample_schemas import VoiceSampleResponse
from src.domains.voice.voices_catalog import VoiceOption

pytestmark = pytest.mark.unit
PERSON = uuid4()
CATALOGUE = [
    VoiceOption(f"voice-{i}", f"Voice {i}", "male" if i % 2 else "female", "fr") for i in range(8)
]
CONFIG = TTSConfig(provider="edge", model="edge-tts", voice_male="voice-1", voice_female="voice-0")


@pytest.fixture
def sampled(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def config(slot: str) -> TTSConfig:
        assert slot == "radio_voice"
        return CONFIG

    async def sample(**kwargs: Any) -> VoiceSampleResponse:
        voice = kwargs["choose"](EngineVoices(CONFIG, CATALOGUE, multilingual=False))
        calls.append({**kwargs, "voice_id": voice})
        return VoiceSampleResponse(voice_id=voice, audio_base64="SUQz", mime_type="audio/mpeg")

    monkeypatch.setattr(module, "get_tts_config", config)
    monkeypatch.setattr(module, "synthesize_sample", sample)
    return calls


@pytest.mark.parametrize("role", list(RadioRole))
async def test_automatic_voice_matches_real_cast_for_complete_unsaved_draft(
    sampled: list[dict[str, Any]], role: RadioRole
) -> None:
    draft = {RadioRole.HOST: "voice-7", RadioRole.ANCHOR: "voice-6"}
    expected = cast_voices(CATALOGUE, draft, language="fr", multilingual=False)
    assert expected is not None
    response = await module.sample_radio_voice(
        user_id=PERSON, language="fr", role=role, voices=draft
    )
    assert response.voice_id == expected.voices[role]
    assert sampled[0]["run_prefix"] == "radio_voice_sample"
    assert draft == {RadioRole.HOST: "voice-7", RadioRole.ANCHOR: "voice-6"}


async def test_explicit_voice_is_the_one_heard(sampled: list[dict[str, Any]]) -> None:
    response = await module.sample_radio_voice(
        user_id=PERSON,
        language="fr",
        role=RadioRole.SPEAKER_C,
        voices={RadioRole.SPEAKER_C: "voice-4"},
    )
    assert response.voice_id == "voice-4"


@pytest.mark.parametrize(
    "voices,code",
    [
        ({RadioRole.HOST: "off-list"}, "radio_voice_unknown"),
        ({RadioRole.HOST: "voice-0", RadioRole.SPEAKER_A: "voice-0"}, "radio_voice_shared"),
    ],
)
async def test_an_invalid_draft_never_synthesizes(
    sampled: list[dict[str, Any]], voices: dict[RadioRole, str], code: str
) -> None:
    with pytest.raises(BaseAPIException) as caught:
        await module.sample_radio_voice(
            user_id=PERSON, language="fr", role=RadioRole.HOST, voices=voices
        )
    assert caught.value.detail == {"code": code}
    assert sampled == []


async def test_reached_radio_budget_refuses_before_any_paid_synthesis(
    monkeypatch: pytest.MonkeyPatch, sampled: list[dict[str, Any]]
) -> None:
    paid = TTSConfig(provider="openai", model="tts-1", voice_male="voice-1", voice_female="voice-0")
    later = datetime(2026, 10, 17, tzinfo=UTC)
    monkeypatch.setattr(module, "get_tts_config", AsyncMock(return_value=paid))
    budget = AsyncMock(return_value=BudgetStatus(limit_eur=1, spent_eur=1.2, lifts_at=later))
    monkeypatch.setattr(module, "listener_budget", budget)
    with pytest.raises(BaseAPIException) as caught:
        await module.sample_radio_voice(
            user_id=PERSON, language="fr", role=RadioRole.HOST, voices={}
        )
    assert caught.value.status_code == 429
    assert caught.value.detail["code"] == "radio_budget_reached"
    assert caught.value.detail["lifts_at"] == later.isoformat()
    assert sampled == []
    budget.assert_awaited_once()
