"""Raw TTS metadata makes samples readable without re-encoding or changing the wire."""

from __future__ import annotations

import base64
import io
import struct
import wave
from unittest.mock import AsyncMock

import pytest

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.audio_output import (
    audio_for_mix,
    mix_audio_format,
    synthesize_playable_base64,
)
from src.domains.voice.elevenlabs_tts_client import ElevenLabsTTSClient
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.factory import TTSConfig, get_tts_client_sync
from src.domains.voice.openai_tts_client import OpenAITTSClient
from src.domains.voice.protocol import RawAudioSpec

pytestmark = pytest.mark.unit


async def test_browser_pcm_container_keeps_rate_samples_and_one_provider_call() -> None:
    client = OpenAITTSClient(response_format="pcm")
    samples = struct.pack("<5h", -32768, -1000, 0, 1000, 32767)
    client.synthesize = AsyncMock(return_value=samples)
    client.synthesize_base64 = AsyncMock()
    try:
        result = await synthesize_playable_base64(client, text="Test", voice_name="nova")
        with wave.open(io.BytesIO(base64.b64decode(result)), "rb") as reader:
            assert reader.getframerate() == 24000
            assert reader.readframes(5) == samples
        client.synthesize.assert_awaited_once_with(text="Test", voice_name="nova")
        client.synthesize_base64.assert_not_awaited()
    finally:
        await client.close()


async def test_browser_encoded_audio_retains_existing_base64_path() -> None:
    client = OpenAITTSClient(response_format="mp3")
    client.synthesize = AsyncMock()
    client.synthesize_base64 = AsyncMock(return_value="encoded-original")
    try:
        assert (
            await synthesize_playable_base64(client, text="Test", voice_name="nova")
            == "encoded-original"
        )
        client.synthesize_base64.assert_awaited_once_with(text="Test", voice_name="nova")
        client.synthesize.assert_not_awaited()
    finally:
        await client.close()


@pytest.fixture(autouse=True)
def provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, provider: "k")
    )


@pytest.mark.parametrize("rate", [16000, 22050, 24000, 44100])
async def test_configured_elevenlabs_pcm_rate_and_samples_are_preserved(rate: int) -> None:
    config = TTSConfig(
        provider="elevenlabs",
        model="eleven_v4_turbo",
        voice_male="a",
        voice_female="b",
        output_format=f"pcm_{rate}",
    )
    client = get_tts_client_sync(config, strict=True)
    try:
        assert isinstance(client, ElevenLabsTTSClient)
        assert client.raw_audio_spec == RawAudioSpec(rate)
        assert client.audio_format == "pcm"
        assert mix_audio_format(client) == "wav"
        samples = struct.pack("<5h", -32768, -1000, 0, 1000, 32767)
        wrapped = audio_for_mix(client, samples)
        with wave.open(io.BytesIO(wrapped), "rb") as reader:
            assert (reader.getframerate(), reader.getnchannels(), reader.getsampwidth()) == (
                rate,
                1,
                2,
            )
            assert reader.readframes(reader.getnframes()) == samples
    finally:
        await client.close()


async def test_openai_pcm_is_24khz_while_the_client_keeps_its_raw_wire() -> None:
    client = get_tts_client_sync(
        TTSConfig(
            provider="openai",
            model="tts-1",
            voice_male="a",
            voice_female="b",
            response_format="pcm",
        ),
        strict=True,
    )
    try:
        assert isinstance(client, OpenAITTSClient)
        assert client.raw_audio_spec == RawAudioSpec(24000)
        assert client.audio_format == "pcm"
        with wave.open(io.BytesIO(audio_for_mix(client, b"\x00\x01")), "rb") as reader:
            assert reader.getframerate() == 24000
            assert reader.readframes(1) == b"\x00\x01"
    finally:
        await client.close()


@pytest.mark.parametrize("fmt", ["mp3", "opus", "aac", "flac", "wav"])
async def test_encoded_openai_responses_are_kept_byte_for_byte(fmt: str) -> None:
    client = get_tts_client_sync(
        TTSConfig(
            provider="openai", model="tts-1", voice_male="a", voice_female="b", response_format=fmt
        ),
        strict=True,
    )
    try:
        audio = b"already encoded"
        assert isinstance(client, OpenAITTSClient)
        assert client.raw_audio_spec is None
        assert mix_audio_format(client) == fmt
        assert audio_for_mix(client, audio) is audio
    finally:
        await client.close()


async def test_ulaw_keeps_the_encoding_and_sample_count_including_an_odd_byte_pad() -> None:
    client = ElevenLabsTTSClient(output_format="ulaw_8000")
    try:
        samples = b"\xff\xff\x80"
        wrapped = audio_for_mix(client, samples)
        assert client.raw_audio_spec == RawAudioSpec(8000, "ulaw")
        assert mix_audio_format(client) == "wav"
        assert wrapped[12:20] == b"fmt \x12\x00\x00\x00"
        assert struct.unpack_from("<HHIIHHH", wrapped, 20) == (7, 1, 8000, 8000, 1, 8, 0)
        assert struct.unpack_from("<I", wrapped, wrapped.index(b"fact") + 8)[0] == len(samples)
        assert wrapped.endswith(b"data\x03\x00\x00\x00" + samples + b"\x00")
        assert len(wrapped) - 8 == struct.unpack_from("<I", wrapped, 4)[0]
    finally:
        await client.close()


@pytest.mark.parametrize("audio", [b"", b"\x01", b"\x01\x02\x03"])
async def test_incomplete_pcm_samples_are_refused_without_a_provider_call(audio: bytes) -> None:
    client = ElevenLabsTTSClient(output_format="pcm_22050")
    try:
        with pytest.raises(TTSProviderError) as error:
            audio_for_mix(client, audio)
        assert error.value.code == "provider_invalid_response"
    finally:
        await client.close()
