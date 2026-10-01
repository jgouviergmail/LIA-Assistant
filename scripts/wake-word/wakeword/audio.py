"""Small audio steps every synthesiser shares (ADR-329): one implementation each."""

from __future__ import annotations

from math import gcd

import numpy as np
import numpy.typing as npt
from scipy.signal import resample_poly

from wakeword.banks import SAMPLE_RATE, Int16Array

FloatArray = npt.NDArray[np.float32]

_FADE_SECONDS = 0.005
#: A 10 ms frame quieter than this, relative to the clip's loudest, is silence.
_TRIM_DB = -40.0
_TRIM_MARGIN_SECONDS = 0.03


def to_16k(audio: FloatArray, rate: int) -> FloatArray:
    """Resample to 16 kHz (polyphase, exact ratio)."""
    if rate == SAMPLE_RATE:
        return audio
    divisor = gcd(SAMPLE_RATE, rate)
    return np.asarray(resample_poly(audio, SAMPLE_RATE // divisor, rate // divisor), np.float32)


def trim(audio: FloatArray) -> FloatArray:
    """Cut the leading and trailing silence of a 16 kHz clip, keeping a short margin."""
    frame = SAMPLE_RATE // 100
    if audio.size < frame:
        return audio
    usable = audio[: audio.size // frame * frame].reshape(-1, frame)
    energy = np.sqrt(np.mean(usable.astype(np.float64) ** 2, axis=1)) + 1e-9
    loud = np.flatnonzero(20 * np.log10(energy / energy.max()) > _TRIM_DB)
    if loud.size == 0:
        return audio[:0]
    margin = int(_TRIM_MARGIN_SECONDS * SAMPLE_RATE)
    start = max(0, int(loud[0]) * frame - margin)
    end = min(audio.size, (int(loud[-1]) + 1) * frame + margin)
    return audio[start:end]


def faded(audio: FloatArray) -> FloatArray:
    """Short linear fades, so a cut never starts or ends on a click."""
    fade = min(int(_FADE_SECONDS * SAMPLE_RATE), audio.size // 2)
    if fade:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        audio[:fade] *= ramp
        audio[-fade:] *= ramp[::-1]
    return audio


def peak_int16(audio: FloatArray) -> Int16Array:
    """Peak-normalised int16 (the augmentation sets the level later)."""
    peak = float(np.max(np.abs(audio))) or 1.0
    return np.asarray(np.clip(audio / peak, -1.0, 1.0) * 32767.0, dtype=np.int16)
