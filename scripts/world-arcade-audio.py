"""Render LIA's original, gentle 1980s-style arcade score to a seamless mono WAV.

Offline authoring only: no runtime synthesis, dependency, provider or credential.
Master/encode the resulting WAV before replacing the public MP3 and provenance.
"""

from __future__ import annotations

import argparse
from array import array
from math import exp, pi, sin, tanh
from pathlib import Path
from random import Random
import sys
import wave

SAMPLE_RATE = 32_000
BPM = 128
BEAT = 60 / BPM
BARS = 16
LENGTH = round(BARS * 4 * BEAT * SAMPLE_RATE)
TAU = 2 * pi


def note(
    samples: array,
    midi: int,
    start: float,
    duration: float,
    level: float,
    instrument: str,
) -> None:
    """Soft envelopes and limited harmonics retain chip character without sharp edges."""
    frequency = 440 * 2 ** ((midi - 69) / 12)
    begin = round(start * SAMPLE_RATE)
    count = round(duration * SAMPLE_RATE)
    for i in range(count):
        time = i / SAMPLE_RATE
        phase = TAU * frequency * time
        if instrument == "pulse":
            value = sin(phase) + 0.11 * sin(phase * 3) + 0.025 * sin(phase * 5)
        else:
            value = sin(phase) - 0.09 * sin(phase * 3) + 0.03 * sin(phase * 5)
        envelope = min(1, time / 0.012) * min(1, (duration - time) / 0.055)
        envelope *= exp(-1.2 * time / duration)
        samples[(begin + i) % LENGTH] += value * envelope * level


def percussion(samples: array, random: Random, start: float, kick: bool) -> None:
    count = round((0.12 if kick else 0.075) * SAMPLE_RATE)
    begin = round(start * SAMPLE_RATE)
    low_noise = 0.0
    for i in range(count):
        time = i / SAMPLE_RATE
        envelope = min(1, time / 0.003) * exp(-time * (38 if kick else 65))
        if kick:
            value = sin(TAU * (65 * time + 1.1 * (1 - exp(-time * 30)))) * 0.035
        else:
            low_noise += 0.18 * (random.uniform(-1, 1) - low_noise)
            value = low_noise * 0.024
        samples[(begin + i) % LENGTH] += value * envelope


def compose() -> array:
    samples = array("f", [0.0]) * LENGTH
    random = Random(1986)
    chords = [(48, 60, 64, 67), (45, 57, 60, 64), (41, 57, 60, 65), (43, 59, 62, 67)]
    phrases = [
        [(72, 0.5), (76, 0.5), (79, 1), (76, 0.5), (74, 0.5), (72, 1)],
        [(69, 0.5), (72, 0.5), (76, 1), (79, 0.5), (76, 0.5), (72, 1)],
        [(69, 0.5), (72, 0.5), (77, 0.5), (76, 0.5), (74, 1), (72, 1)],
        [(71, 0.5), (74, 0.5), (79, 1), (77, 0.5), (74, 0.5), (71, 1)],
        [(76, 1), (79, 0.5), (81, 0.5), (79, 1), (76, 1)],
        [(76, 0.5), (72, 0.5), (69, 1), (72, 0.5), (76, 0.5), (79, 1)],
        [(77, 1), (76, 0.5), (72, 0.5), (69, 1), (72, 1)],
        [(74, 0.5), (71, 0.5), (67, 1), (71, 0.5), (74, 0.5), (79, 1)],
    ]
    for bar in range(BARS):
        start = bar * 4 * BEAT
        chord = chords[bar % len(chords)]
        # A restrained triangle bass and broken chords leave space around the tune.
        for beat in range(4):
            note(
                samples,
                chord[0] + (7 if beat % 2 else 0),
                start + beat * BEAT,
                0.72 * BEAT,
                0.045,
                "triangle",
            )
            percussion(samples, random, start + beat * BEAT, kick=beat % 2 == 0)
        for step, index in enumerate([1, 2, 3, 2, 1, 3, 2, 3]):
            note(
                samples,
                chord[index] + 12,
                start + step * BEAT / 2,
                0.32 * BEAT,
                0.012,
                "triangle",
            )
        position = 0.0
        for midi, beats in phrases[bar % len(phrases)]:
            note(
                samples,
                midi,
                start + position * BEAT,
                beats * BEAT * 0.88,
                0.066,
                "pulse",
            )
            position += beats
    # Circular, short delay tails make the authored bar cycle seamless.
    dry = samples[:]
    for i, value in enumerate(dry):
        samples[(i + round(0.14 * SAMPLE_RATE)) % LENGTH] += value * 0.10
        samples[(i + round(0.28 * SAMPLE_RATE)) % LENGTH] += value * 0.045
    return samples


def write_wav(path: Path) -> None:
    samples = compose()
    pcm = array("h", (round(tanh(value) * 32700) for value in samples))
    if sys.byteorder != "little":
        pcm.byteswap()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm.tobytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Intermediate WAV destination.")
    write_wav(parser.parse_args().output)
