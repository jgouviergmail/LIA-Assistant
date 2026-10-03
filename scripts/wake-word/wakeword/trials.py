"""A clip played as a stream, and what the browser's policy makes of it (ADR-329).

The measurement judges a model this way on TEST clips, and the training selects
its checkpoint the same way on VALIDATION clips: one implementation, so the
number a checkpoint is chosen on is the number the bench certifies. A clip is
placed 3 s into a 6 s stream (through a room and a phone half the time, at a
signal-to-noise ratio or over a faint hiss), and a detection counts when it
falls between the start of the phrase and one second after its end.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from wakeword import augment as aug
from wakeword.banks import SAMPLE_RATE, Bank
from wakeword.features import CHUNK, WARMUP_CHUNKS, Policy

STREAM_SECONDS = 6.0
CLIP_START_SECONDS = 3.0
AFTER_END_SECONDS = 1.0
SNR_CONDITIONS: dict[str, float | None] = {"clean": None, "20 dB": 20.0, "10 dB": 10.0, "5 dB": 5.0}
_CHUNK_SECONDS = CHUNK / SAMPLE_RATE


def stream(
    clip: np.ndarray, snr_db: float | None, backgrounds: list[Bank], rng: np.random.Generator
) -> tuple[np.ndarray, float, float]:
    """A 6-second stream with the clip at 3 s; returns it and the clip's span in seconds."""
    total = int(STREAM_SECONDS * SAMPLE_RATE)
    start = int(CLIP_START_SECONDS * SAMPLE_RATE)
    audio = aug.to_float(clip)
    if rng.random() < 0.5:
        audio = aug.equalise(audio, rng)
    window = np.zeros(total, dtype=np.float32)
    end = min(total, start + audio.size)
    window[start:end] = audio[: end - start]
    active = slice(start, end)
    if rng.random() < 0.5:
        window = aug.reverberate(window, rng)
    if snr_db is None:
        window = aug.mix_at_snr(window, rng.standard_normal(total).astype(np.float32), 60.0, active)
    else:
        window = aug.mix_at_snr(
            window, aug.background_from(backgrounds, total, rng), snr_db, active
        )
    if rng.random() < 0.4:
        window = aug.phone_band(window, rng)
    peak = float(np.max(np.abs(window))) or 1.0
    level = 10 ** (rng.uniform(-35.0, -6.0) / 20)
    return aug.to_int16(window * (level / peak)), start / SAMPLE_RATE, end / SAMPLE_RATE


Trial = tuple[np.ndarray, float, float]


#: Punctuation that changes a clip's prosody, not its form: « Dis Lia ! » and
#: « Dis Lia. » are one form; a comma (a pause) and a space stay.
_PROSODY_MARKS = re.compile(r"[!?.¡¿。！？]")


def form_of(text: str) -> str:
    """The written form of a clip's text: its words and pauses, without its prosody marks."""
    return " ".join(_PROSODY_MARKS.sub("", text).split())


def hit_latency(trial: Trial, policy: Policy) -> tuple[float | None, int]:
    """The latency of the detection inside the phrase's window (None: missed), and spurious ones."""
    scores, start, end = trial
    times = [(WARMUP_CHUNKS + i) * _CHUNK_SECONDS for i in policy.detections(scores, WARMUP_CHUNKS)]
    inside = [time for time in times if start <= time <= end + AFTER_END_SECONDS]
    return (inside[0] - end if inside else None), len(times) - len(inside)


def recall(trials: list[Trial], policy: Policy) -> dict[str, Any]:
    """The share of trials the policy detects in their phrase's window, and the median latency."""
    hits, latencies, spurious = 0, [], 0
    for trial in trials:
        latency, extra = hit_latency(trial, policy)
        spurious += extra
        if latency is not None:
            hits += 1
            latencies.append(latency)
    return {
        "recall": hits / len(trials),
        "median_latency_ms": round(float(np.median(latencies)) * 1000) if latencies else None,
        "spurious_detections": spurious,
        "trials": len(trials),
    }


def accept_rate(trials: list[Trial], policy: Policy) -> float:
    """The share of trials (near misses) on which the policy fires at all."""
    return sum(bool(policy.detections(scores, WARMUP_CHUNKS)) for scores, _, _ in trials) / len(
        trials
    )
