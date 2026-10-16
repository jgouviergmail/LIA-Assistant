"""A buffered readout is ONE playable MP3, whatever container its sentences came back in.

Real ffmpeg, no provider: an engine configured for raw samples returns a WAV
per sentence, and two WAV files joined byte to byte play their first sentence
alone. The readout decodes them to one rate and encodes once (ADR-345).
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest

from src.domains.voice.text_readout import _as_one_mp3
from src.infrastructure.media.ffmpeg import probe_duration
from src.infrastructure.media.pcm import wav_container

pytestmark = pytest.mark.integration
#: ffmpeg runs as an asyncio subprocess (a Proactor loop on Windows, conftest).
REQUIRES_ASYNC_SUBPROCESSES = True


def _tone_wav(rate: int, seconds: float) -> bytes:
    samples = b"".join(
        struct.pack("<h", round(5000 * math.sin(2 * math.pi * 440 * index / rate)))
        for index in range(int(rate * seconds))
    )
    return wav_container(samples, sample_rate=rate)


async def test_two_wav_sentences_become_one_mp3_holding_both(tmp_path: Path) -> None:
    parts = [(_tone_wav(44100, 0.5), "audio/wav"), (_tone_wav(16000, 0.75), "audio/wav")]

    audio = await _as_one_mp3(parts)

    path = tmp_path / "readout.mp3"
    path.write_bytes(audio)
    assert audio[:3] == b"ID3" or audio[0] == 0xFF  # an MP3 stream, never a RIFF
    # Both sentences are heard: the encoder adds a frame of padding at most.
    assert await probe_duration(path, timeout_s=10) == pytest.approx(1.25, abs=0.1)


async def test_mp3_sentences_are_passed_through_byte_for_byte() -> None:
    parts = [(b"\xff\xfb\x90one", "audio/mpeg"), (b"\xff\xfb\x90two", "audio/mpeg")]

    assert await _as_one_mp3(parts) == b"\xff\xfb\x90one\xff\xfb\x90two"
