"""Hold this toolbox's features to openWakeWord, the reference (ADR-329).

Four claims every model and every measurement rest on, checked on seeded noise:

1. the batch embeddings equal openWakeWord's ``AudioFeatures.embed_clips``;
2. a long recording embedded segment by segment equals it embedded at once;
3. the streaming embeddings equal openWakeWord's own streaming ones, chunk by
   chunk, from the first chunk whose mel window holds no seeded frame;
4. the streaming SCORE at chunk ``t`` equals the batch score ``t - 25`` on the
   streaming grid — so a measurement made in batch is a measurement of what
   the browser runs.

Prints the largest difference of each and exits non-zero beyond the tolerance.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import torch
from openwakeword.utils import AudioFeatures

from wakeword.features import (
    CHUNK,
    WARMUP_CHUNKS,
    Classifier,
    StreamingFeatures,
    StreamingScorer,
)
from wakeword.sources import feature_models, fetch, read_lock
from wakeword.train import Net, _export_onnx, extractor

_TOLERANCE = 1e-4
#: Chunk ``t`` (1-based) reads mel frames ``8t - 79 .. 8t - 4``: none is a
#: seeded frame from chunk 10 on, where streaming embedding ``t`` is batch ``t - 10``.
_FIRST_REAL_CHUNK = 10


def _noise(seconds: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(seconds * 16_000)) * 3_000).clip(-32768, 32767).astype(np.int16)


def run() -> None:
    """Run the four checks; raise ``SystemExit`` on the first one beyond tolerance."""
    lock = read_lock()
    mel, embedding = (fetch(remote, lock) for remote in feature_models())
    fx = extractor()
    reference = AudioFeatures(
        melspec_model_path=str(mel), embedding_model_path=str(embedding), inference_framework="onnx"
    )
    results: dict[str, float] = {}

    clips = np.stack([_noise(2.0, seed) for seed in range(4)])
    ours = fx.embed(clips, aligned=False)
    theirs = reference.embed_clips(clips)
    results["batch vs embed_clips"] = float(np.abs(ours - theirs).max())

    long = _noise(30.0, 7)
    results["segmented vs whole"] = float(
        np.abs(fx.embed_long(long, windows_per_segment=7) - fx.embed(long[None])[0]).max()
    )

    stream = StreamingFeatures(fx)
    reference.reset()
    batch = fx.embed_long(long)
    worst_reference = worst_batch = 0.0
    for t, start in enumerate(range(0, long.size - CHUNK + 1, CHUNK), start=1):
        chunk = long[start : start + CHUNK]
        (mine,) = stream.push(chunk)
        reference(chunk)
        if t >= _FIRST_REAL_CHUNK:
            worst_reference = max(
                worst_reference, float(np.abs(mine - reference.feature_buffer[-1]).max())
            )
            worst_batch = max(worst_batch, float(np.abs(mine - batch[t - _FIRST_REAL_CHUNK]).max()))
    results["streaming vs openWakeWord streaming"] = worst_reference
    results["streaming vs batch grid"] = worst_batch

    with tempfile.TemporaryDirectory() as directory:
        torch.manual_seed(3)
        path = Path(directory) / "random.onnx"
        _export_onnx(Net(), path)
        classifier = Classifier(path, threads=2)
        scorer = StreamingScorer(fx, classifier)
        streamed = np.array(scorer.push(long))
        batched = classifier.stream_scores(batch)
        overlap = min(streamed.size - (WARMUP_CHUNKS - 1), batched.size)
        results["streaming score vs batch score"] = float(
            np.abs(
                streamed[WARMUP_CHUNKS - 1 : WARMUP_CHUNKS - 1 + overlap] - batched[:overlap]
            ).max()
        )

    failed = False
    for name, worst in results.items():
        verdict = "ok" if worst <= _TOLERANCE else "FAILED"
        failed |= verdict == "FAILED"
        print(f"{verdict:6} {name}: max |diff| = {worst:.3g}")
    if failed:
        raise SystemExit(1)
