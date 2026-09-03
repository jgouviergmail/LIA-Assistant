"""The local STT service routes long buffers through windows instead of truncating.

Regression for the defect measured 2026-09-02: sherpa-onnx decodes only the
first 30 s of a buffer, so a 45 s dictation lost its tail although the service
accepted up to 60 s. The service is built without a model (``object.__new__``)
and its recognizer replaced by a recorder, so the test pins the ROUTING — one
pass under the cap, several windows above it, every sample decoded once.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.voice.stt.sherpa_stt import SherpaSttService

pytestmark = pytest.mark.unit

SR = 16000


class _RecordingStream:
    def __init__(self) -> None:
        self.samples: list[float] = []
        self.result = SimpleNamespace(text="")

    def accept_waveform(self, sample_rate: int, samples: list[float]) -> None:
        assert sample_rate == SR
        self.samples = list(samples)
        self.result.text = f"w{len(samples)} "


class _RecordingRecognizer:
    def __init__(self) -> None:
        self.streams: list[_RecordingStream] = []

    def create_stream(self) -> _RecordingStream:
        stream = _RecordingStream()
        self.streams.append(stream)
        return stream

    def decode_stream(self, stream: _RecordingStream) -> None:
        assert stream.samples, "decode called on an empty stream"


def _service(recognizer: _RecordingRecognizer, *, single_pass: int = 25, window: int = 20) -> Any:
    svc = object.__new__(SherpaSttService)
    svc._sample_rate = SR
    svc._max_duration = 60
    svc._default_language = ""
    svc._single_pass_max_seconds = single_pass
    svc._window_seconds = window
    svc._segmenter = None  # no VAD model → fixed windows, deterministic
    svc._recognizers = {}
    svc._recognizers_lock = threading.Lock()
    svc._get_recognizer = lambda language: recognizer  # type: ignore[method-assign]
    return svc


def test_a_buffer_under_the_single_pass_cap_is_decoded_once() -> None:
    recognizer = _RecordingRecognizer()
    svc = _service(recognizer)
    samples = [0.0] * (20 * SR)

    text = svc.transcribe(samples, SR, "fr")

    assert len(recognizer.streams) == 1
    assert len(recognizer.streams[0].samples) == 20 * SR
    assert text == f"w{20 * SR}"


def test_a_45_second_buffer_is_decoded_in_windows_and_keeps_its_tail() -> None:
    recognizer = _RecordingRecognizer()
    svc = _service(recognizer)
    samples = [0.0] * (45 * SR)

    text = svc.transcribe(samples, SR, "fr")

    lengths = [len(s.samples) for s in recognizer.streams]
    assert lengths == [20 * SR, 20 * SR, 5 * SR]  # nothing beyond 30 s is dropped
    assert sum(lengths) == 45 * SR
    assert text == f"w{20 * SR} w{20 * SR} w{5 * SR}"


def test_every_window_stays_under_the_engine_limit() -> None:
    recognizer = _RecordingRecognizer()
    svc = _service(recognizer, single_pass=25, window=29)
    svc.transcribe([0.0] * (60 * SR), SR, "")

    assert all(len(s.samples) <= 29 * SR for s in recognizer.streams)
    assert sum(len(s.samples) for s in recognizer.streams) == 60 * SR


def test_the_duration_cap_still_rejects_oversized_buffers() -> None:
    recognizer = _RecordingRecognizer()
    svc = _service(recognizer)

    with pytest.raises(Exception, match="too long|duration|exceed"):
        svc.transcribe([0.0] * (61 * SR), SR, "")
    assert recognizer.streams == []
