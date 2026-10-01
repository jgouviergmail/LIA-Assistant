"""The golden fixture the browser engine is held to (ADR-329).

A held-out TEST clip of the phrase, placed three seconds into a six-second
stream over a quiet noise floor, scored chunk by chunk by ``StreamingScorer``
(openWakeWord's streaming arithmetic, held to the reference by the selfcheck)
with the SHIPPED model, and the detections of the policy its manifest states.
The web suite replays the same audio through the TypeScript engine on ONNX
Runtime Web and must find the same scores and the same detections.

The fixture names the classifier's SHA-256: a model retrained without a new
fixture is caught by the web test, never compared in silence.
"""

from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path

import numpy as np

from wakeword.augment import to_int16
from wakeword.banks import SAMPLE_RATE, open_bank
from wakeword.export import MODEL_VERSION
from wakeword.features import Classifier, Policy, StreamingScorer
from wakeword.languages import LanguageSpec
from wakeword.paths import CORPORA, OUT_DIR
from wakeword.train import extractor

FIXTURES = Path("/fixtures")
_STREAM_SECONDS = 6.0
_CLIP_START_SECONDS = 3.0
_NOISE_DBFS = -55.0


def golden(spec: LanguageSpec) -> Path:
    """Write ``golden-<lang>.wav`` and ``golden-<lang>.json`` under ``/fixtures``."""
    model_dir = OUT_DIR / MODEL_VERSION / spec.code
    manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
    # The file the manifest names (content-addressed), checked as the browser checks it.
    classifier = manifest["files"]["classifier"]
    classifier_path = OUT_DIR / classifier["url"].removeprefix("/models/wake/")
    if hashlib.sha256(classifier_path.read_bytes()).hexdigest() != classifier["sha256"]:
        raise SystemExit(f"{classifier_path} does not match its manifest: export again")
    clip = np.asarray(open_bank(CORPORA, f"clips-{spec.code}-positive-test").segment(0))
    rng = np.random.default_rng(0)
    total = int(_STREAM_SECONDS * SAMPLE_RATE)
    stream = rng.standard_normal(total).astype(np.float32) * 10 ** (_NOISE_DBFS / 20)
    start = int(_CLIP_START_SECONDS * SAMPLE_RATE)
    end = min(total, start + clip.size)
    stream[start:end] += clip[: end - start].astype(np.float32) / 32768.0 * 0.5
    audio = to_int16(stream)

    scorer = StreamingScorer(extractor(), Classifier(classifier_path, threads=1))
    scores = np.array(scorer.push(audio), dtype=np.float32)
    policy = Policy(manifest["threshold"], manifest["patience"], manifest["refractory_chunks"])
    detections = [index + 1 for index in policy.detections(scores, first_chunk=1)]

    FIXTURES.mkdir(parents=True, exist_ok=True)
    with wave.open(str(FIXTURES / f"golden-{spec.code}.wav"), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(audio.tobytes())
    payload = {
        "language": spec.code,
        "classifier_sha256": hashlib.sha256(classifier_path.read_bytes()).hexdigest(),
        "scores": [round(float(score), 6) for score in scores],
        "detections": detections,
    }
    path = FIXTURES / f"golden-{spec.code}.json"
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"golden {spec.code}: {len(scores)} chunks, detections at {detections}")
    return path
