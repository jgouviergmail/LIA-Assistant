"""`trim_silence`: the audible span of a continuous stream, with its margin, or nothing."""

from __future__ import annotations

import array

import pytest

from src.infrastructure.media.pcm import trim_silence

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
