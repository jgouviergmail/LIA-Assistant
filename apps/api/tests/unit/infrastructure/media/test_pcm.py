"""Raw 16-bit mono PCM: its audible span (`trim_silence`), and its WAV container."""

from __future__ import annotations

import array
import io
import wave

import pytest

from src.infrastructure.media.pcm import trim_silence, wav_container

pytestmark = pytest.mark.unit

RATE = 24_000


def _pcm(*runs: tuple[int, int]) -> bytes:
    """Runs of ``(sample_value, count)`` as little-endian 16-bit PCM."""
    samples = array.array("h")
    for value, count in runs:
        samples.extend([value] * count)
    return samples.tobytes()


def test_silence_on_both_sides_is_cut_and_a_margin_kept() -> None:
    lead, body, tail = 24_000, 4_800, 48_000  # 1 s, 0.2 s, 2 s
    pcm = _pcm((0, lead), (9_000, body), (0, tail))
    out = trim_silence(pcm, sample_rate=RATE, margin_ms=100)
    margin = RATE * 100 // 1000
    assert len(out) == (body + 2 * margin) * 2
    # The audible run sits after exactly one margin of kept silence.
    kept = array.array("h")
    kept.frombytes(out)
    assert list(kept[:margin]) == [0] * margin
    assert kept[margin] == 9_000 and kept[margin + body - 1] == 9_000


def test_a_stream_with_nothing_audible_is_empty() -> None:
    assert trim_silence(_pcm((0, 10_000), (12, 10_000)), sample_rate=RATE) == b""
    assert trim_silence(b"", sample_rate=RATE) == b""


def test_a_margin_never_reaches_past_the_ends_and_an_odd_byte_is_dropped() -> None:
    pcm = _pcm((-9_000, 100)) + b"\x01"
    out = trim_silence(pcm, sample_rate=RATE, margin_ms=1_000)
    assert out == _pcm((-9_000, 100))


def test_the_threshold_is_the_audible_line() -> None:
    pcm = _pcm((0, 50), (399, 50), (401, 50), (0, 50))
    out = trim_silence(pcm, sample_rate=RATE, margin_ms=0)
    kept = array.array("h")
    kept.frombytes(out)
    assert list(kept) == [401] * 50


def test_raw_samples_are_wrapped_in_a_wav_that_reads_back() -> None:
    pcm = _pcm((-7, 3), (9_000, 5))
    wav = wav_container(pcm, sample_rate=RATE)
    assert (wav[:4], wav[8:12]) == (b"RIFF", b"WAVE")
    with wave.open(io.BytesIO(wav)) as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (
            1,
            2,
            RATE,
        )
        assert reader.readframes(reader.getnframes()) == pcm


def test_a_wav_holds_whole_samples_only() -> None:
    pcm = _pcm((9_000, 4))
    wav = wav_container(pcm + b"\x01", sample_rate=16_000)
    assert len(wav) == 44 + len(pcm)  # the canonical header, then whole samples only
    with wave.open(io.BytesIO(wav)) as reader:
        assert reader.getframerate() == 16_000
        assert reader.readframes(reader.getnframes()) == pcm
