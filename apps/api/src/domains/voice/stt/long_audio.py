"""Long-audio windowing for the local Whisper engine.

sherpa-onnx's Whisper decoder keeps only the first 30 s of a buffer and drops
the rest with a stderr log — measured 2026-09-02 on a 127.6 s recording, one of
seven sentinel words survived a single decode. Anything longer than one pass is
therefore cut into windows that (1) never exceed the engine limit and (2) end on
silences, so no word is split at a boundary. Silero VAD supplies the silences;
when the VAD model is unavailable the windows fall back to fixed slices —
degraded recall at the cuts, but never a silent truncation.

Three pure pieces (``build_windows``, ``fixed_windows``,
``transcribe_in_windows``) carry the logic and are unit-tested without any
model; :class:`SileroSegmenter` is the only piece that touches sherpa-onnx and
takes an injectable factory for the same reason.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

#: Half-open ``[start, end)`` sample offsets into the audio buffer.
SpeechSegment = tuple[int, int]

#: How a long buffer was cut: on VAD silences, in fixed slices because the VAD
#: was unavailable or failed, or in fixed slices because the VAD heard no speech
#: (the engine still decodes it — the threshold is a heuristic, not a verdict).
WindowStrategy = Literal["vad", "fixed_no_vad", "fixed_no_speech"]


def fixed_windows(
    total_samples: int, *, sample_rate: int, max_window_seconds: float
) -> list[SpeechSegment]:
    """Cut ``total_samples`` into consecutive slices of at most the window cap.

    Args:
        total_samples: Length of the buffer, in samples.
        sample_rate: Samples per second (> 0).
        max_window_seconds: Window cap in seconds (> 0).

    Returns:
        Contiguous windows covering the whole buffer; empty for an empty buffer.
    """
    _check_bounds(sample_rate, max_window_seconds)
    step = max(1, int(max_window_seconds * sample_rate))
    return [(start, min(start + step, total_samples)) for start in range(0, total_samples, step)]


def build_windows(
    segments: Sequence[SpeechSegment], *, sample_rate: int, max_window_seconds: float
) -> list[SpeechSegment]:
    """Group consecutive speech segments into windows cut only at silences.

    Segments are merged in order while the window (from the first segment's
    start to the current segment's end, silences included) stays within the
    cap — the audio between grouped segments is kept, since natural pauses help
    Whisper's punctuation. A single segment longer than the cap is sliced.

    Args:
        segments: Speech segments in chronological order.
        sample_rate: Samples per second (> 0).
        max_window_seconds: Window cap in seconds (> 0).

    Returns:
        Windows in chronological order; empty when there is no speech.
    """
    _check_bounds(sample_rate, max_window_seconds)
    max_samples = max(1, int(max_window_seconds * sample_rate))
    windows: list[SpeechSegment] = []
    current: SpeechSegment | None = None

    for start, end in segments:
        if end <= start:
            continue
        if end - start > max_samples:
            # A speech run longer than a window cannot end on a silence anyway:
            # close what we have and slice the run.
            if current is not None:
                windows.append(current)
                current = None
            windows.extend(
                (start + s, start + e)
                for s, e in fixed_windows(
                    end - start, sample_rate=sample_rate, max_window_seconds=max_window_seconds
                )
            )
            continue
        if current is None:
            current = (start, end)
        elif end - current[0] <= max_samples:
            current = (current[0], end)
        else:
            windows.append(current)
            current = (start, end)

    if current is not None:
        windows.append(current)
    return windows


def transcribe_in_windows(
    samples: np.ndarray,
    windows: Sequence[SpeechSegment],
    decode: Callable[[list[float]], str],
) -> str:
    """Decode each window and join the texts in order.

    Args:
        samples: Float32 mono samples in ``[-1, 1]``.
        windows: ``[start, end)`` offsets into ``samples``.
        decode: One decode call for one window (the engine's single pass).

    Returns:
        The joined transcription; empty when every window came back empty.
    """
    texts: list[str] = []
    for start, end in windows:
        text = decode(samples[start:end].tolist()).strip()
        if text:
            texts.append(text)
    return " ".join(texts)


class SileroSegmenter:
    """Speech segments from Silero VAD through sherpa-onnx.

    A fresh detector is built per call because the sherpa VAD object keeps
    streaming state; the configuration is cheap and the model is loaded by
    sherpa from disk each time — acceptable for a per-recording operation.

    Args:
        model_path: Path to ``silero_vad.onnx``.
        threshold: Speech probability threshold.
        min_silence_seconds: Silence that closes a speech segment.
        min_speech_seconds: Speech bursts shorter than this are ignored.
        max_speech_seconds: Speech runs are force-closed at this length so a
            single segment never exceeds a window.
        sample_rate: Samples per second of the buffers fed to ``segment``.
        vad_factory: Test seam — a callable ``(model_path, threshold,
            min_silence_seconds, min_speech_seconds, max_speech_seconds,
            sample_rate) -> (detector, window_size)`` replacing the sherpa
            constructor. The window size travels WITH the detector because the
            sherpa detector object does not expose it (it lives on the model
            config); the detector must expose ``accept_waveform``, ``empty``,
            ``front`` (``start``, ``samples``), ``pop`` and ``flush``.
    """

    def __init__(
        self,
        model_path: str,
        *,
        threshold: float,
        min_silence_seconds: float,
        min_speech_seconds: float,
        max_speech_seconds: float,
        sample_rate: int = 16000,
        vad_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._model_path = model_path
        self._threshold = threshold
        self._min_silence_seconds = min_silence_seconds
        self._min_speech_seconds = min_speech_seconds
        self._max_speech_seconds = max_speech_seconds
        self._sample_rate = sample_rate
        self._vad_factory = vad_factory or _sherpa_vad_factory

    @property
    def model_path(self) -> str:
        """Configured model path (for logs and availability checks)."""
        return self._model_path

    def is_available(self) -> bool:
        """Whether a VAD model file is present at the configured path."""
        return Path(self._model_path).is_file()

    def segment(self, samples: np.ndarray) -> list[SpeechSegment]:
        """Return speech segments as ``[start, end)`` sample offsets.

        Args:
            samples: Float32 mono samples in ``[-1, 1]`` at ``sample_rate``.

        Returns:
            Chronological speech segments; empty when no speech was detected.

        Raises:
            Exception: Whatever the detector raises — the caller decides the
                fallback (fixed windows), this class never hides a failure.
        """
        detector, window_size = self._vad_factory(
            self._model_path,
            self._threshold,
            self._min_silence_seconds,
            self._min_speech_seconds,
            self._max_speech_seconds,
            self._sample_rate,
        )
        window = int(window_size)
        if window <= 0:
            raise ValueError("VAD window size must be positive")
        segments: list[SpeechSegment] = []

        def _drain() -> None:
            while not detector.empty():
                front = detector.front
                start = int(front.start)
                segments.append((start, start + len(front.samples)))
                detector.pop()

        for offset in range(0, len(samples), window):
            chunk = samples[offset : offset + window]
            if len(chunk) < window:
                chunk = np.pad(chunk, (0, window - len(chunk)))
            detector.accept_waveform(chunk)
            _drain()
        detector.flush()
        _drain()
        total = len(samples)
        return [(s, min(e, total)) for s, e in segments if s < total]


def plan_windows(
    samples: np.ndarray,
    *,
    sample_rate: int,
    max_window_seconds: float,
    segmenter: SileroSegmenter | None,
) -> tuple[list[SpeechSegment], WindowStrategy]:
    """Decide how a long buffer is cut, VAD first, fixed slices as the fallback.

    Args:
        samples: Float32 mono samples.
        sample_rate: Samples per second.
        max_window_seconds: Window cap in seconds.
        segmenter: The VAD, or ``None`` when no model is configured.

    Returns:
        The windows and the strategy that produced them. Fixed slices are
        returned when the VAD is unavailable or fails (``fixed_no_vad``) and
        when it finds no speech at all (``fixed_no_speech`` — a whole recording
        of silence still deserves a decode: the VAD threshold is a heuristic,
        the engine is the judge).
    """
    fixed = fixed_windows(
        len(samples), sample_rate=sample_rate, max_window_seconds=max_window_seconds
    )
    if segmenter is None:
        return fixed, "fixed_no_vad"
    if not segmenter.is_available():
        logger.warning("stt_vad_model_missing", model_path=segmenter.model_path)
        return fixed, "fixed_no_vad"
    try:
        segments = segmenter.segment(samples)
    except Exception as exc:
        logger.warning(
            "stt_vad_segmentation_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return fixed, "fixed_no_vad"
    windows = build_windows(
        segments, sample_rate=sample_rate, max_window_seconds=max_window_seconds
    )
    if not windows:
        logger.debug("stt_vad_found_no_speech", samples=len(samples))
        return fixed, "fixed_no_speech"
    return windows, "vad"


def _check_bounds(sample_rate: int, max_window_seconds: float) -> None:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if max_window_seconds <= 0:
        raise ValueError("max_window_seconds must be positive")


def _sherpa_vad_factory(
    model_path: str,
    threshold: float,
    min_silence_seconds: float,
    min_speech_seconds: float,
    max_speech_seconds: float,
    sample_rate: int,
) -> tuple[Any, int]:
    """Build a sherpa-onnx ``VoiceActivityDetector`` (imported lazily).

    Returns:
        The detector and the number of samples it expects per
        ``accept_waveform`` call (``config.silero_vad.window_size``, which the
        detector object itself does not expose).
    """
    import sherpa_onnx

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = model_path
    config.silero_vad.threshold = threshold
    config.silero_vad.min_silence_duration = min_silence_seconds
    config.silero_vad.min_speech_duration = min_speech_seconds
    config.silero_vad.max_speech_duration = max_speech_seconds
    config.sample_rate = sample_rate
    # The internal ring buffer must hold at least one window of speech plus
    # the silences around it; two windows leave the detector headroom.
    buffer_seconds = max(30.0, 2 * max_speech_seconds)
    detector = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=buffer_seconds)
    return detector, int(config.silero_vad.window_size)
