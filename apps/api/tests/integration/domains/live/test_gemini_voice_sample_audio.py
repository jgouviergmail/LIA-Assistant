"""The live voice sample reaches the browser as the WAV it plays, whatever the model answered.

Real ffmpeg and the real Gemini TTS client; the vendor is a local HTTP double,
so nothing is synthesised or paid. Measured 2026-09-26 on the Interactions API:
the 3.8 models answer a WAV (24 kHz, mono, 16-bit), the 2.5 previews raw L16
samples. Either way the provider hands back the protocol's 16-bit mono PCM at
its ``sample_rate``, and the WAV the connector service wraps it in is what the
browser's audio element plays.
"""

from __future__ import annotations

import base64
import io
import math
import struct
import wave
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from src.domains.live.providers.gemini import GeminiLiveProvider
from src.domains.voice.gemini_tts_client import GeminiTTSClient
from src.infrastructure.media.pcm import wav_container
from src.infrastructure.media.wav import wav_bytes

pytestmark = pytest.mark.integration
#: ffmpeg runs as an asyncio subprocess (a Proactor loop on Windows, conftest).
REQUIRES_ASYNC_SUBPROCESSES = True

MODULE = "src.domains.live.providers.gemini"


def _tone(rate: int, seconds: float) -> bytes:
    """A 440 Hz tone as 16-bit mono little-endian samples."""
    return b"".join(
        struct.pack("<h", round(5000 * math.sin(2 * math.pi * 440 * index / rate)))
        for index in range(int(rate * seconds))
    )


def _answer(audio: bytes, mime_type: str) -> dict[str, Any]:
    return {
        "status": "completed",
        "usage": {"total_input_tokens": 9, "total_output_tokens": 17},
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "audio",
                        "mime_type": mime_type,
                        "data": base64.b64encode(audio).decode(),
                    }
                ],
            }
        ],
    }


async def _sample(answer: dict[str, Any]) -> bytes:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answer)

    def _client(model: str, **kwargs: Any) -> GeminiTTSClient:
        return GeminiTTSClient(model, transport=httpx.MockTransport(handler), **kwargs)

    with patch(f"{MODULE}.GeminiTTSClient", _client):
        return await GeminiLiveProvider().sample_voice("k-person", "Kore", "Hello.")


def _played(pcm: bytes) -> tuple[int, int, int, int]:
    """What the browser reads from the connector service's WAV of ``pcm``."""
    with wave.open(io.BytesIO(wav_bytes(pcm, GeminiLiveProvider().sample_rate))) as reader:
        return (
            reader.getnchannels(),
            reader.getsampwidth(),
            reader.getframerate(),
            reader.getnframes(),
        )


async def test_a_wav_answer_is_handed_back_as_its_own_samples() -> None:
    samples = _tone(24_000, 0.5)

    pcm = await _sample(_answer(wav_container(samples, sample_rate=24_000), "audio/wav"))

    assert pcm == samples  # the protocol's rate already: decoded, never altered
    assert _played(pcm) == (1, 2, 24_000, 12_000)


async def test_raw_samples_at_another_rate_play_at_the_right_speed() -> None:
    """A rate the vendor declares in the type is honoured, then resampled to the protocol's."""
    samples = _tone(16_000, 0.5)

    pcm = await _sample(_answer(samples, "audio/L16;codec=pcm;rate=16000"))

    channels, width, rate, frames = _played(pcm)
    assert (channels, width, rate) == (1, 2, 24_000)
    # Half a second at 24 kHz, give or take the resampler's edge.
    assert frames == pytest.approx(12_000, abs=64)
