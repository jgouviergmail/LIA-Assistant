"""openWakeWord's features, batch and streaming, and the detection policy (ADR-329).

Three ONNX stages turn 16 kHz int16 audio into a score:

1. ``melspectrogram.onnx`` — a 512-sample window every 160 samples, 32 mel
   bins; the output is transformed by ``x / 10 + 2`` (openWakeWord's own
   transform, which brings it close to Google's TensorFlow front end).
2. ``embedding_model.onnx`` — 76 mel frames (760 ms) to one 96-dim embedding,
   every 8 frames (80 ms).
3. the language's classifier — the last 16 embeddings (1.28 s) to a score.

``FeatureExtractor`` computes them in batch for training; ``StreamingScorer``
reproduces openWakeWord's STREAMING arithmetic exactly (1 280-sample chunks, the
mel of the last 1 760 samples, a mel buffer seeded with ones), and is the
reference the browser engine is held to sample for sample (the golden
fixture). Its feature buffer starts at zeros instead of openWakeWord's random
embeddings, which no other runtime can reproduce: the ``WARMUP_CHUNKS`` gate
makes the difference unobservable, since no score is acted on before every
input of the classifier comes from real audio.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt
import onnxruntime as ort

from wakeword.banks import Int16Array

CHUNK = 1280
MEL_BINS = 32
MEL_WINDOW = 76
MEL_STEP = 8
MEL_LOOKBACK = 480
EMBEDDINGS = 16
EMBEDDING_DIM = 96
#: Samples one embedding window spans: 75 hops of 160 plus one 512-sample frame.
WINDOW_SAMPLES = (MEL_WINDOW - 1) * 160 + 512
#: The first chunk whose classifier input is entirely real audio: the mel window
#: holds no seeded frame from chunk 10 on, and 16 such embeddings exist at chunk 25.
WARMUP_CHUNKS = 25
#: In streaming, chunk ``t``'s embedding window starts on mel frame ``8t - 79``,
#: i.e. on frame 1 modulo 8; a batch window starts on frame 0 modulo 8. Dropping
#: the first 160 samples (one mel hop) puts the batch on the streaming grid, so
#: a model is trained on exactly the windows it scores in the browser, and batch
#: scores ARE streaming scores: batch score ``i`` is streaming chunk ``25 + i``.
STREAM_ALIGNMENT_SAMPLES = 160
#: Chunks after a detection during which nothing fires (2 s): one phrase, one wake.
REFRACTORY_CHUNKS = 25

FloatArray = npt.NDArray[np.float32]


@functools.cache
def _providers() -> tuple[str, ...]:
    """CUDA where the image carries it (the GPU image trains), the CPU everywhere else.

    The measurement and the golden fixture run in the CPU image: the arithmetic
    they certify is the one the browser's WASM runtime does. A CUDA provider is
    used to build training features only, where a 1e-6 difference is noise.
    """
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        return ("CPUExecutionProvider",)
    # The CUDA and cuDNN libraries come as pip wheels (torch's): loaded from there.
    ort.preload_dlls()
    return ("CUDAExecutionProvider", "CPUExecutionProvider")


def _session(path: Path, threads: int) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), options, providers=list(_providers()))


class FeatureExtractor:
    """The two shared stages, in batch."""

    def __init__(self, mel_path: Path, embedding_path: Path, threads: int = 8) -> None:
        self._mel = _session(mel_path, threads)
        self._embedding = _session(embedding_path, threads)
        self._mel_input = self._mel.get_inputs()[0].name
        self._embedding_input = self._embedding.get_inputs()[0].name

    def melspec(self, audio: Int16Array) -> FloatArray:
        """``(batch, samples)`` int16 to ``(batch, frames, 32)``, transformed."""
        batch = np.atleast_2d(audio).astype(np.float32)
        output = self._mel.run(None, {self._mel_input: batch})[0]
        spec: FloatArray = (output[:, 0] / 10.0 + 2.0).astype(np.float32)
        return spec

    def embed_spec(self, spec: FloatArray, batch_size: int = 4096) -> FloatArray:
        """``(batch, frames, 32)`` to ``(batch, windows, 96)``, a window every 8 frames."""
        count, frames = spec.shape[0], spec.shape[1]
        starts = range(0, frames - MEL_WINDOW + 1, MEL_STEP)
        if not starts:
            return np.zeros((count, 0, EMBEDDING_DIM), dtype=np.float32)
        windows = np.stack([spec[:, start : start + MEL_WINDOW] for start in starts], axis=1)
        flat = windows.reshape(-1, MEL_WINDOW, MEL_BINS, 1)
        out = [
            self._embedding.run(None, {self._embedding_input: flat[i : i + batch_size]})[0]
            for i in range(0, flat.shape[0], batch_size)
        ]
        embeddings: FloatArray = np.concatenate(out).reshape(count, len(starts), EMBEDDING_DIM)
        return embeddings

    def embed(self, audio: Int16Array, aligned: bool = True) -> FloatArray:
        """``(batch, samples)`` int16 to ``(batch, windows, 96)``, on the streaming grid."""
        batch = np.atleast_2d(audio)
        if aligned:
            batch = batch[:, STREAM_ALIGNMENT_SAMPLES:]
        return self.embed_spec(self.melspec(batch))

    def embed_long(self, audio: Int16Array, windows_per_segment: int = 2000) -> FloatArray:
        """One long recording to ``(windows, 96)`` on the streaming grid, exactly as at once.

        Segment ``k`` starts on the 1 280-sample grid and spans the samples its
        ``windows_per_segment`` windows read, so the concatenation equals the
        embedding of the whole array (the mel stage is frame-local).
        """
        audio = audio[STREAM_ALIGNMENT_SAMPLES:]
        span = WINDOW_SAMPLES + CHUNK * (windows_per_segment - 1)
        parts = []
        for start in range(0, max(0, audio.size - WINDOW_SAMPLES + 1), CHUNK * windows_per_segment):
            segment = np.asarray(audio[start : start + span], dtype=np.int16)
            if segment.size < WINDOW_SAMPLES:
                break
            parts.append(self.embed(segment[None], aligned=False)[0])
        if not parts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        return np.concatenate(parts)


class Classifier:
    """A language's classifier ONNX: ``(batch, 16, 96)`` to ``(batch,)`` scores."""

    def __init__(self, path: Path, threads: int = 8) -> None:
        self._session = _session(path, threads)
        self._input = self._session.get_inputs()[0].name

    def scores(self, windows: FloatArray, batch_size: int = 8192) -> FloatArray:
        """Scores of many windows."""
        out = [
            self._session.run(None, {self._input: windows[i : i + batch_size].astype(np.float32)})[
                0
            ]
            for i in range(0, windows.shape[0], batch_size)
        ]
        if not out:
            return np.zeros(0, dtype=np.float32)
        scores: FloatArray = np.concatenate(out).reshape(-1).astype(np.float32)
        return scores

    def stream_scores(self, embeddings: FloatArray) -> FloatArray:
        """The score at every embedding of a sequence (16 trailing ones per score)."""
        if embeddings.shape[0] < EMBEDDINGS:
            return np.zeros(0, dtype=np.float32)
        windows = np.lib.stride_tricks.sliding_window_view(embeddings, (EMBEDDINGS, EMBEDDING_DIM))[
            :, 0
        ]
        return self.scores(np.ascontiguousarray(windows))


@dataclass(slots=True)
class StreamingFeatures:
    """openWakeWord's streaming arithmetic: one embedding per 1 280-sample chunk."""

    extractor: FeatureExtractor
    _raw: Int16Array = field(default_factory=lambda: np.zeros(0, dtype=np.int16))
    _pending: Int16Array = field(default_factory=lambda: np.zeros(0, dtype=np.int16))
    _mel: FloatArray = field(default_factory=lambda: np.ones((MEL_WINDOW, MEL_BINS), np.float32))
    chunks: int = 0

    def push(self, samples: Int16Array) -> list[FloatArray]:
        """Feed samples of any length; one embedding per completed chunk."""
        self._pending = np.concatenate([self._pending, samples.astype(np.int16)])
        embeddings = []
        while self._pending.size >= CHUNK:
            chunk, self._pending = self._pending[:CHUNK], self._pending[CHUNK:]
            embeddings.append(self._chunk(chunk))
        return embeddings

    def _chunk(self, chunk: Int16Array) -> FloatArray:
        # The mel of the last 1 760 samples is 8 frames; of the very first
        # chunk (1 280 samples, nothing before it) it is 5 — openWakeWord's own.
        self._raw = np.concatenate([self._raw, chunk])[-(CHUNK + MEL_LOOKBACK) :]
        frames = self.extractor.melspec(self._raw[None])[0]
        self._mel = np.concatenate([self._mel, frames])[-MEL_WINDOW:]
        self.chunks += 1
        embedding: FloatArray = self.extractor.embed_spec(self._mel[None])[0, 0]
        return embedding


@dataclass(slots=True)
class StreamingScorer:
    """Streaming features, the last 16 embeddings (seeded with zeros), the classifier."""

    extractor: FeatureExtractor
    classifier: Classifier
    _features: StreamingFeatures | None = None
    _window: FloatArray = field(
        default_factory=lambda: np.zeros((EMBEDDINGS, EMBEDDING_DIM), np.float32)
    )

    def push(self, samples: Int16Array) -> list[float]:
        """Feed samples of any length; one raw score per completed chunk."""
        if self._features is None:
            self._features = StreamingFeatures(self.extractor)
        scores = []
        for embedding in self._features.push(samples):
            self._window = np.concatenate([self._window[1:], embedding[None]])
            scores.append(float(self.classifier.scores(self._window[None])[0]))
        return scores


@dataclass(frozen=True, slots=True)
class Policy:
    """When a score becomes a detection — the rule the browser applies too.

    Attributes:
        threshold: The score a chunk must reach.
        patience: Consecutive chunks at or above the threshold.
        refractory_chunks: Chunks after a detection during which nothing fires.
    """

    threshold: float
    patience: int = 1
    refractory_chunks: int = REFRACTORY_CHUNKS

    def detections(self, scores: FloatArray, first_chunk: int = 1) -> list[int]:
        """The 0-based indices of the chunks that fire, ``scores[0]`` being chunk ``first_chunk``.

        The browser runs this rule chunk by chunk: a chunk fires when it and the
        ``patience - 1`` before it reached the threshold, none of them in the
        warm-up, and the last detection is more than ``refractory_chunks`` back.
        Vectorised here (a dev stream is half a million chunks); the golden
        fixture holds the two implementations to the same answer.
        """
        above = np.asarray(scores) >= self.threshold
        warmup = max(0, WARMUP_CHUNKS - first_chunk)
        above[:warmup] = False
        if self.patience > 1:
            window = np.convolve(above.astype(np.int32), np.ones(self.patience, np.int32))
            above = window[: above.size] >= self.patience
        fired: list[int] = []
        last = -(self.refractory_chunks + 1)
        for index in np.flatnonzero(above):
            if index - last > self.refractory_chunks:
                fired.append(int(index))
                last = int(index)
        return fired
