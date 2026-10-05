"""Real ffprobe/ffmpeg, synthetic audio and local HTTP doubles: no paid synthesis."""

from __future__ import annotations

import io
import math
import shutil
import struct
import wave
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.radio.audio import AudioAssemblyError, assemble_segment
from src.domains.radio.cast import Cast
from src.domains.radio.delivery import StylePhrases
from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, SourceRef
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.production import (
    ProductionLimits,
    ProductionOutcome,
    VoiceEngine,
    WritingRequest,
    produce_segment,
)
from src.domains.radio.script import LineKind, ScriptDraft, ScriptLine, ScriptPart
from src.domains.voice import elevenlabs_tts_client
from src.domains.voice.elevenlabs_tts_client import ElevenLabsTTSClient
from src.infrastructure.media.ffmpeg import transcode

# This media-only module opens real async subprocesses and no psycopg pools.
# The per-item loop hook leaves all following PostgreSQL tests on Selector.
REQUIRES_ASYNC_SUBPROCESSES = True

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
        reason="real audio assembly requires ffmpeg and ffprobe",
    ),
]

TEXT = "The parliament adopted the budget."
DRAFT = ScriptDraft(
    title="Budget",
    lines=[
        ScriptLine(
            role=RadioRole.ANCHOR, part=ScriptPart.BODY, kind=LineKind.FACT, text=TEXT, refs=["n1"]
        )
    ],
)
REQUEST = WritingRequest(
    format=RadioFormat.BRIEF,
    pack=FactPack(
        format=RadioFormat.BRIEF,
        facts=(
            RadioFact(
                id="n1",
                kind=FactKind.NEWS,
                text=TEXT,
                key="news:budget",
                sensitivity=Sensitivity.PUBLIC,
                source=SourceRef(label="News", url="https://news.example.org/budget"),
            ),
        ),
    ),
    language="en",
    local_now=datetime(2026, 10, 4, 12, tzinfo=UTC),
    station_id=False,
    station_name="Radio",
)


def pcm_tone(rate: int) -> bytes:
    return b"".join(
        struct.pack("<h", round(5000 * math.sin(2 * math.pi * 440 * index / rate)))
        for index in range(rate // 2)
    )


class Writer:
    async def write(self, request: WritingRequest) -> ScriptDraft:
        return DRAFT


class Ledger:
    def __init__(self) -> None:
        self.characters: list[int] = []

    def record_tts_call(
        self, provider: str, model: str, characters: int, duration_ms: float = 0, **kwargs: Any
    ) -> None:
        self.characters.append(characters)


@pytest.mark.parametrize("rate", [16000, 22050, 24000, 44100])
async def test_original_headerless_pcm_cannot_be_probed(tmp_path: Path, rate: int) -> None:
    """The old production path fails after a successful synthesis, at assembly."""
    line = tmp_path / "line.pcm"
    line.write_bytes(pcm_tone(rate))
    with pytest.raises(AudioAssemblyError):
        await assemble_segment([(ScriptPart.BODY, line)], tmp_path / "old.mp3", timeout_s=10)
    assert not (tmp_path / "old.mp3").exists()


@pytest.mark.parametrize(
    "fmt", ["pcm_16000", "pcm_22050", "pcm_24000", "pcm_44100", "ulaw_8000", "mp3_44100_128"]
)
async def test_real_radio_mix_of_configured_raw_or_encoded_audio_is_audible_and_billed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fmt: str
) -> None:
    rate = int(fmt.split("_")[1])
    raw = pcm_tone(rate)
    wav = io.BytesIO()
    with wave.open(wav, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(raw)
    if fmt == "ulaw_8000":
        payload = await transcode(
            wav.getvalue(),
            output_format="mulaw",
            args=["-codec:a", "pcm_mulaw", "-ar", "8000", "-ac", "1"],
            timeout_s=10,
        )
    elif fmt.startswith("mp3_"):
        payload = await transcode(
            wav.getvalue(), output_format="mp3", args=["-codec:a", "libmp3lame"], timeout_s=10
        )
    else:
        payload = raw
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.params["output_format"] == fmt
        return httpx.Response(200, content=payload)

    @asynccontextmanager
    async def no_external_capacity(*args: object, **kwargs: object):
        yield

    monkeypatch.setattr(
        LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, provider: "test-key")
    )
    monkeypatch.setattr(elevenlabs_tts_client, "tts_slot", no_external_capacity)
    client = ElevenLabsTTSClient(output_format=fmt)
    await client.close()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    ledger = Ledger()
    try:
        result = await produce_segment(
            REQUEST,
            tmp_path / "out.mp3",
            writer=Writer(),
            engine=VoiceEngine(
                client, "eleven_v4_turbo", StylePhrases({}, {}, "{role} {qualities}", "{role}")
            ),
            cast=Cast(dict.fromkeys(RadioRole, "voice")),
            ledger=ledger,
            limits=ProductionLimits(120, 1, 10, 1, 0),
        )
    finally:
        await client.close()
    assert result.outcome is ProductionOutcome.PRODUCED
    assert result.segment is not None
    assert len(requests) == len(ledger.characters) == len(result.segment.transcript)
    assert ledger.characters == [len(line.text) for line in result.segment.transcript]
    decoded = await transcode(
        (tmp_path / "out.mp3").read_bytes(),
        output_format="s16le",
        args=["-codec:a", "pcm_s16le", "-ar", "44100", "-ac", "1"],
        timeout_s=10,
    )
    samples = struct.unpack(f"<{len(decoded) // 2}h", decoded)
    assert max(abs(value) for value in samples) > 1000
    assert result.segment.transcript[0].offset_s == pytest.approx(0.5)
    assert result.segment.duration_s >= len(requests) * 0.5 + 0.5 + 0.4
    assert list(tmp_path.iterdir()) == [tmp_path / "out.mp3"]
