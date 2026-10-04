"""The synthesis loop shared by the voice comment and the direct readout.

Two rules it shares with the progressive streamer: a sentence with nothing to
pronounce is never sent (a provider refuses it, after billing the call), and a
failure is logged by its facts, never its message (ADR-303).
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from structlog.testing import capture_logs

from src.domains.voice import service as voice_service
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.schemas import VoiceAudioChunk
from src.domains.voice.service import VoiceCommentService, _SynthesisMetrics
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    """Keep `capture_logs` reliable under xdist — see `tests/support`."""
    yield from fresh_module_logger(voice_service)


async def _synthesize(sentences: list[str], synthesize_base64: AsyncMock) -> list[VoiceAudioChunk]:
    client = SimpleNamespace(synthesize_base64=synthesize_base64, audio_format="mp3")
    service = VoiceCommentService(tts_client=client)
    config = SimpleNamespace(is_paid=False, provider="edge", model="edge")
    with (
        patch.object(service, "_get_tts_config", AsyncMock(return_value=config)),
        patch.object(service, "_get_voice_for_language", AsyncMock(return_value="voice")),
        patch.object(service, "_resolve_prosody_settings", AsyncMock(return_value=None)),
    ):
        return [
            chunk
            async for chunk in service._synthesize_sentences(
                sentences, "fr", _SynthesisMetrics(), "direct_tts"
            )
        ]


async def test_a_sentence_with_nothing_to_say_is_not_sent() -> None:
    synthesize = AsyncMock(return_value="YXVkaW8=")

    chunks = await _synthesize(["Bonjour.", "🎉 [laughs] ✨.", "Au revoir.", "🙂"], synthesize)

    assert [call.kwargs["text"] for call in synthesize.await_args_list] == [
        "Bonjour.",
        "Au revoir.",
    ]
    assert [(c.phrase_index, c.phrase_text, c.is_last) for c in chunks] == [
        (0, "Bonjour.", False),
        (1, "Au revoir.", True),
    ]


async def test_a_refusal_is_logged_by_its_code_never_its_message() -> None:
    refusal = TTSProviderError(
        "provider_http_error",
        "HTTP 400: refused « the words of the answer »",
        details={"status_code": 400},
    )

    with capture_logs() as logs:
        chunks = await _synthesize(["Bonjour."], AsyncMock(side_effect=refusal))

    assert chunks == []
    errors = [entry for entry in logs if entry["event"] == "direct_tts_chunk_error"]
    assert [(e["error_code"], e["status_code"], e["transient"]) for e in errors] == [
        ("provider_http_error", 400, False)
    ]
    assert "the words of the answer" not in repr(logs)
