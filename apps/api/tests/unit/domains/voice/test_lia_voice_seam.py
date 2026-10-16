"""The one seam where the chat's voice is chosen (ADR-345 amendment 2026-10-14).

Every chat surface that speaks — the voice comments, the progressive stream, the
read-aloud — asks ``VoiceCommentService._get_voice_for_language``: the person's
own voice when they chose one, the configured voice otherwise, and never a
failure to read the choice that costs the audio.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from structlog.testing import capture_logs

from src.domains.voice import service as voice_service
from src.domains.voice.factory import TTSConfig
from src.domains.voice.service import VoiceCommentService
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit

EDGE = TTSConfig(
    provider="edge",
    model="edge-tts",
    voice_male="fr-FR-HenriNeural",
    voice_female="fr-FR-DeniseNeural",
)


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    yield from fresh_module_logger(voice_service)


@pytest.fixture(autouse=True)
def _edge_speaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voice_service, "get_tts_config", AsyncMock(return_value=EDGE))


def _choice(monkeypatch: pytest.MonkeyPatch, answer: Any) -> list[tuple[Any, ...]]:
    asked: list[tuple[Any, ...]] = []

    async def spoken(user_id: str | None, config: TTSConfig, gender: str, language: str) -> Any:
        asked.append((user_id, config.provider, gender, language))
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(voice_service, "spoken_voice", spoken)
    return asked


async def test_the_person_s_voice_speaks_read_once_per_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _choice(monkeypatch, "fr-FR-VivienneMultilingualNeural")
    service = VoiceCommentService(lia_gender="female", user_id="person")
    try:
        assert await service._get_voice_for_language("fr") == "fr-FR-VivienneMultilingualNeural"
        assert await service._get_voice_for_language("fr") == "fr-FR-VivienneMultilingualNeural"
    finally:
        await service.close()

    assert asked == [("person", "edge", "female", "fr")]


@pytest.mark.parametrize(
    ("gender", "configured"), [("male", "fr-FR-HenriNeural"), ("female", "fr-FR-DeniseNeural")]
)
async def test_without_a_choice_the_configured_voice_of_lia_s_gender_speaks(
    monkeypatch: pytest.MonkeyPatch, gender: str, configured: str
) -> None:
    _choice(monkeypatch, None)
    service = VoiceCommentService(lia_gender=gender, user_id="person")
    try:
        assert await service._get_voice_for_language("fr") == configured
    finally:
        await service.close()


async def test_a_choice_that_cannot_be_read_never_costs_the_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _choice(monkeypatch, RuntimeError("database down"))
    service = VoiceCommentService(lia_gender="male", user_id="person")
    try:
        with capture_logs() as logs:
            voice = await service._get_voice_for_language("fr")
    finally:
        await service.close()

    assert voice == "fr-FR-HenriNeural"
    assert [entry for entry in logs if entry["event"] == "lia_voice_choice_unreadable"] == [
        {
            "event": "lia_voice_choice_unreadable",
            "error_type": "RuntimeError",
            "log_level": "warning",
        }
    ]
