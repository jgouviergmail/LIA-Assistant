"""The local STT keeps ONE resident recognizer per worker, not one per language.

Measured on the production Raspberry Pi on 2026-09-12, in a throwaway process:
a whisper-small recognizer costs 516 MB to create and ~300 MB more after its
first decode; a second one, for a second language, another 634 MB; and the
service kept every language it had ever been asked for, in a singleton that
lives once PER uvicorn worker. Two voice sessions on two workers took the API
container from 4.2 to 7.0 GB against an 8 GiB ceiling. Deleting a recognizer
returned 1 166 MB to the OS, which is what makes a bounded cache worth having.

These tests drive the real constructor against a fake ``sherpa_onnx`` module
and empty model files, so they pin the cache's contract — lazy, bounded,
least-recently-used out, the gauge honest — without a model on disk.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from prometheus_client import REGISTRY

from src.domains.voice.stt.sherpa_stt import SherpaSttService

pytestmark = pytest.mark.unit

GAUGE = "voice_stt_recognizers_loaded"


class _Recognizer:
    def __init__(self, language: str) -> None:
        self.language = language


class _FakeSherpa(ModuleType):
    """``sherpa_onnx`` reduced to the factory the service calls."""

    def __init__(self) -> None:
        super().__init__("sherpa_onnx")
        self.loads: list[str] = []
        outer = self

        class OfflineRecognizer:
            @staticmethod
            def from_whisper(**kwargs: Any) -> _Recognizer:
                outer.loads.append(kwargs["language"])
                return _Recognizer(kwargs["language"])

        self.OfflineRecognizer = OfflineRecognizer


@pytest.fixture
def sherpa(monkeypatch: pytest.MonkeyPatch) -> _FakeSherpa:
    fake = _FakeSherpa()
    monkeypatch.setitem(sys.modules, "sherpa_onnx", fake)
    return fake


def _settings(tmp_path: Path, *, max_recognizers: int = 1, language: str = "") -> Any:
    for name in ("encoder.onnx", "decoder.onnx", "tokens.txt"):
        (tmp_path / name).write_bytes(b"")
    return SimpleNamespace(
        voice_stt_model_path=str(tmp_path),
        voice_stt_num_threads=1,
        voice_stt_language=language,
        voice_stt_task="transcribe",
        voice_stt_max_duration_seconds=60,
        voice_stt_single_pass_max_seconds=25,
        voice_stt_window_seconds=20,
        voice_stt_vad_model_path=str(tmp_path / "absent-vad.onnx"),
        voice_stt_vad_threshold=0.5,
        voice_stt_vad_min_silence_seconds=0.4,
        voice_stt_vad_min_speech_seconds=0.25,
        voice_stt_max_recognizers=max_recognizers,
    )


def _resident() -> float:
    value = REGISTRY.get_sample_value(GAUGE)
    assert value is not None, f"{GAUGE} is not registered"
    return value


class TestTheCacheIsLazyAndBounded:
    def test_construction_loads_no_model(self, sherpa: _FakeSherpa, tmp_path: Path) -> None:
        SherpaSttService(_settings(tmp_path))

        assert sherpa.loads == []
        assert _resident() == 0

    def test_the_same_language_is_loaded_once(self, sherpa: _FakeSherpa, tmp_path: Path) -> None:
        svc = SherpaSttService(_settings(tmp_path))

        first = svc._get_recognizer("fr")
        second = svc._get_recognizer("fr")

        assert first is second
        assert sherpa.loads == ["fr"]
        assert _resident() == 1

    def test_a_second_language_replaces_the_first_by_default(
        self, sherpa: _FakeSherpa, tmp_path: Path
    ) -> None:
        svc = SherpaSttService(_settings(tmp_path))

        auto = svc._get_recognizer("")
        french = svc._get_recognizer("fr")

        assert sherpa.loads == ["", "fr"]
        assert list(svc._recognizers) == ["fr"]
        assert svc._recognizers["fr"] is french
        assert auto not in svc._recognizers.values()
        assert _resident() == 1

    def test_a_handle_taken_before_the_eviction_stays_valid(
        self, sherpa: _FakeSherpa, tmp_path: Path
    ) -> None:
        """A decode in flight holds its own reference; the cache only drops its own."""
        svc = SherpaSttService(_settings(tmp_path))

        auto = svc._get_recognizer("")
        svc._get_recognizer("fr")

        assert isinstance(auto, _Recognizer) and auto.language == ""

    def test_the_evicted_model_is_released_before_the_next_one_is_created(
        self, sherpa: _FakeSherpa, tmp_path: Path
    ) -> None:
        """The peak is ONE model: create-then-evict would hold two for the load."""
        svc = SherpaSttService(_settings(tmp_path))
        resident_at_load: list[int] = []
        original = sherpa.OfflineRecognizer.from_whisper

        def counting(**kwargs: Any) -> _Recognizer:
            resident_at_load.append(len(svc._recognizers))
            return original(**kwargs)

        sherpa.OfflineRecognizer.from_whisper = staticmethod(counting)  # type: ignore[method-assign]
        svc._get_recognizer("")
        svc._get_recognizer("fr")

        assert resident_at_load == [0, 0]

    def test_coming_back_to_an_evicted_language_reloads_it(
        self, sherpa: _FakeSherpa, tmp_path: Path
    ) -> None:
        svc = SherpaSttService(_settings(tmp_path))

        svc._get_recognizer("")
        svc._get_recognizer("fr")
        svc._get_recognizer("")

        assert sherpa.loads == ["", "fr", ""]
        assert list(svc._recognizers) == [""]


class TestALargerCapIsLeastRecentlyUsed:
    def test_the_least_recently_used_language_leaves_first(
        self, sherpa: _FakeSherpa, tmp_path: Path
    ) -> None:
        svc = SherpaSttService(_settings(tmp_path, max_recognizers=2))

        svc._get_recognizer("")
        svc._get_recognizer("fr")
        svc._get_recognizer("")  # touch: "fr" is now the least recently used
        svc._get_recognizer("de")

        assert list(svc._recognizers) == ["", "de"]
        assert sherpa.loads == ["", "fr", "de"]
        assert _resident() == 2


class TestTranscribeGoesThroughTheCache:
    def test_the_default_language_is_the_cache_key_when_none_is_given(
        self, sherpa: _FakeSherpa, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc = SherpaSttService(_settings(tmp_path, language="fr"))
        monkeypatch.setattr(SherpaSttService, "_decode", staticmethod(lambda *a: "ok"))

        svc.transcribe([0.0] * 16000, 16000, "")
        svc.transcribe([0.0] * 16000, 16000, "fr")

        assert sherpa.loads == ["fr"]
