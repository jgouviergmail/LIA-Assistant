"""Unit tests for the long-audio windowing of the local Whisper engine.

The engine keeps only 30 s of a buffer (measured 2026-09-02); these tests pin
the three properties the windowing exists for: a window never exceeds the cap,
cuts land on silences when a VAD is available, and the fallback is fixed slices
rather than a silent truncation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.domains.voice.stt.long_audio import (
    SileroSegmenter,
    build_windows,
    fixed_windows,
    plan_windows,
    transcribe_in_windows,
)

pytestmark = pytest.mark.unit

SR = 16000


def _s(seconds: float) -> int:
    return int(seconds * SR)


# ----------------------------------------------------------------------------
# build_windows / fixed_windows — pure
# ----------------------------------------------------------------------------


def test_build_windows_merges_segments_and_cuts_only_on_silences() -> None:
    # Speech runs of 8 s separated by 1 s of silence; cap 20 s.
    segments = [(_s(0), _s(8)), (_s(9), _s(17)), (_s(18), _s(26)), (_s(27), _s(35))]
    windows = build_windows(segments, sample_rate=SR, max_window_seconds=20)
    # 0-17 fits (17 s); adding 18-26 would span 26 s → cut at the silence.
    assert windows == [(_s(0), _s(17)), (_s(18), _s(35))]
    assert all((end - start) <= _s(20) for start, end in windows)


def test_build_windows_never_exceeds_the_cap_even_for_one_long_run() -> None:
    windows = build_windows([(_s(0), _s(45))], sample_rate=SR, max_window_seconds=20)
    assert windows == [(_s(0), _s(20)), (_s(20), _s(40)), (_s(40), _s(45))]


def test_build_windows_ignores_empty_or_inverted_segments() -> None:
    assert (
        build_windows([(_s(1), _s(1)), (_s(3), _s(2))], sample_rate=SR, max_window_seconds=20) == []
    )
    assert build_windows([], sample_rate=SR, max_window_seconds=20) == []


def test_fixed_windows_cover_the_whole_buffer() -> None:
    windows = fixed_windows(_s(45), sample_rate=SR, max_window_seconds=20)
    assert windows == [(0, _s(20)), (_s(20), _s(40)), (_s(40), _s(45))]
    assert fixed_windows(0, sample_rate=SR, max_window_seconds=20) == []


@pytest.mark.parametrize(("sample_rate", "cap"), [(0, 20), (SR, 0), (-1, 20)])
def test_window_helpers_reject_non_positive_bounds(sample_rate: int, cap: float) -> None:
    with pytest.raises(ValueError):
        fixed_windows(10, sample_rate=sample_rate, max_window_seconds=cap)
    with pytest.raises(ValueError):
        build_windows([(0, 5)], sample_rate=sample_rate, max_window_seconds=cap)


# ----------------------------------------------------------------------------
# transcribe_in_windows — pure
# ----------------------------------------------------------------------------


def test_transcribe_in_windows_decodes_each_window_in_order_and_joins() -> None:
    samples = np.arange(10, dtype=np.float32)
    seen: list[list[float]] = []

    def decode(clip: list[float]) -> str:
        seen.append(clip)
        # The middle window comes back blank (silence): it must not leave a gap.
        return "  " if clip[0] == 4.0 else f"w{len(clip)}"

    text = transcribe_in_windows(samples, [(0, 4), (4, 7), (7, 10)], decode)
    assert seen == [[0.0, 1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]
    assert text == "w4 w3"


# ----------------------------------------------------------------------------
# SileroSegmenter — sherpa replaced by an injected detector
# ----------------------------------------------------------------------------


@dataclass
class _Front:
    start: int
    samples: list[float]


class _FakeDetector:
    """Emits the configured segments on flush; records what it was fed."""

    def __init__(self, segments: list[tuple[int, int]]) -> None:
        self._pending = [_Front(start, [0.0] * (end - start)) for start, end in segments]
        self._queue: list[_Front] = []
        self.fed_chunks: list[int] = []

    def accept_waveform(self, chunk: np.ndarray) -> None:
        self.fed_chunks.append(len(chunk))

    def empty(self) -> bool:
        return not self._queue

    @property
    def front(self) -> _Front:
        return self._queue[0]

    def pop(self) -> None:
        self._queue.pop(0)

    def flush(self) -> None:
        self._queue.extend(self._pending)
        self._pending = []


def _segmenter(model_path: Path, detector: _FakeDetector) -> SileroSegmenter:
    captured: dict[str, Any] = {}

    def factory(*args: Any) -> tuple[_FakeDetector, int]:
        captured["args"] = args
        return detector, 512

    seg = SileroSegmenter(
        str(model_path),
        threshold=0.5,
        min_silence_seconds=0.4,
        min_speech_seconds=0.25,
        max_speech_seconds=20.0,
        sample_rate=SR,
        vad_factory=factory,
    )
    seg.captured = captured  # type: ignore[attr-defined]  # test-only introspection
    return seg


def test_segmenter_feeds_whole_windows_and_clips_segments_to_the_buffer(tmp_path: Path) -> None:
    model = tmp_path / "silero_vad.onnx"
    model.write_bytes(b"x")
    detector = _FakeDetector([(0, 1000), (1500, 3000)])
    seg = _segmenter(model, detector)
    samples = np.zeros(2048, dtype=np.float32)

    segments = seg.segment(samples)

    assert seg.is_available() is True
    # 2048 samples → 4 windows of 512, the last one padded to a full window.
    assert detector.fed_chunks == [512, 512, 512, 512]
    assert segments == [(0, 1000), (1500, 2048)]
    # The factory received the configuration verbatim, model path first.
    assert seg.captured["args"] == (str(model), 0.5, 0.4, 0.25, 20.0, SR)  # type: ignore[attr-defined]


def test_segmenter_reports_a_missing_model(tmp_path: Path) -> None:
    seg = _segmenter(tmp_path / "absent.onnx", _FakeDetector([]))
    assert seg.is_available() is False


# ----------------------------------------------------------------------------
# plan_windows — the fallback contract
# ----------------------------------------------------------------------------


def test_plan_windows_uses_vad_cuts_when_available(tmp_path: Path) -> None:
    model = tmp_path / "silero_vad.onnx"
    model.write_bytes(b"x")
    seg = _segmenter(model, _FakeDetector([(_s(0), _s(8)), (_s(9), _s(17)), (_s(18), _s(26))]))
    samples = np.zeros(_s(26), dtype=np.float32)

    windows, strategy = plan_windows(samples, sample_rate=SR, max_window_seconds=20, segmenter=seg)

    assert strategy == "vad"
    assert windows == [(_s(0), _s(17)), (_s(18), _s(26))]


def test_plan_windows_falls_back_to_fixed_slices_without_a_model(tmp_path: Path) -> None:
    seg = _segmenter(tmp_path / "absent.onnx", _FakeDetector([]))
    samples = np.zeros(_s(45), dtype=np.float32)

    windows, strategy = plan_windows(samples, sample_rate=SR, max_window_seconds=20, segmenter=seg)

    assert strategy == "fixed_no_vad"
    assert windows == fixed_windows(_s(45), sample_rate=SR, max_window_seconds=20)


def test_plan_windows_falls_back_when_no_segmenter_is_configured() -> None:
    samples = np.zeros(_s(30), dtype=np.float32)
    windows, strategy = plan_windows(samples, sample_rate=SR, max_window_seconds=20, segmenter=None)
    assert strategy == "fixed_no_vad"
    assert windows == [(0, _s(20)), (_s(20), _s(30))]


def test_plan_windows_falls_back_when_the_vad_raises(tmp_path: Path) -> None:
    model = tmp_path / "silero_vad.onnx"
    model.write_bytes(b"x")

    class _Boom(_FakeDetector):
        def flush(self) -> None:
            raise RuntimeError("onnx runtime exploded")

    seg = _segmenter(model, _Boom([]))
    samples = np.zeros(_s(30), dtype=np.float32)

    windows, strategy = plan_windows(samples, sample_rate=SR, max_window_seconds=20, segmenter=seg)

    assert strategy == "fixed_no_vad"
    assert len(windows) == 2


def test_plan_windows_still_decodes_a_silent_recording(tmp_path: Path) -> None:
    model = tmp_path / "silero_vad.onnx"
    model.write_bytes(b"x")
    seg = _segmenter(model, _FakeDetector([]))  # the VAD hears nothing
    samples = np.zeros(_s(30), dtype=np.float32)

    windows, strategy = plan_windows(samples, sample_rate=SR, max_window_seconds=20, segmenter=seg)

    assert strategy == "fixed_no_speech"
    assert windows == [(0, _s(20)), (_s(20), _s(30))]
