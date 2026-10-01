"""Make a clean synthetic clip sound like a phone in a room (ADR-329).

openWakeWord's recipe, without its two augmentation libraries: the clip is
sped up or slowed (pitch moves with it), filtered by a random equaliser and,
half the time, by a phone-like band limit, reverberated through a SYNTHETIC
room (no impulse-response corpus is needed, so none has to be licensed), mixed
with a real background (music, noise, babble) or coloured noise at a random
signal-to-noise ratio, lightly distorted, and brought to a random level.

Everything draws from the generator it is handed, so a set is reproducible.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

from wakeword.banks import SAMPLE_RATE, Bank, Int16Array

FloatArray = npt.NDArray[np.float32]
Rng = np.random.Generator

#: Resampling factor: up to 20 % faster, 15 % slower (faster widened with the
#: synthesis rate, 2026-10-01: a phrase is said quickly more often than slowly).
_SPEED = (0.85, 1.2)
_RT60 = (0.12, 0.9)
_SNR_DB = (-3.0, 25.0)
_LEVEL_DBFS = (-35.0, -3.0)
#: Probabilities of each step (openWakeWord's, adapted).
_P_SPEED = 0.5
_P_EQ = 0.5
_P_PHONE = 0.4
_P_REVERB = 0.5
_P_BACKGROUND = 0.75
_P_COLOURED = 0.25
_P_DISTORTION = 0.15


def to_float(audio: Int16Array) -> FloatArray:
    """int16 to float32 in [-1, 1]."""
    return audio.astype(np.float32) / 32768.0


def to_int16(audio: FloatArray) -> Int16Array:
    """float32 to int16, clipped."""
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)


def speed(audio: FloatArray, rng: Rng) -> FloatArray:
    """Resample by a factor near one: faster and higher, or slower and lower."""
    factor = rng.uniform(*_SPEED)
    up = 100
    down = max(1, round(up * factor))
    return np.asarray(resample_poly(audio, up, down), dtype=np.float32)


def equalise(audio: FloatArray, rng: Rng) -> FloatArray:
    """Random tilt through two gentle shelves (±6 dB)."""
    low = butter(2, rng.uniform(250, 900), btype="lowpass", fs=SAMPLE_RATE, output="sos")
    high = butter(2, rng.uniform(1500, 4500), btype="highpass", fs=SAMPLE_RATE, output="sos")
    low_gain = 10 ** (rng.uniform(-6, 6) / 20) - 1
    high_gain = 10 ** (rng.uniform(-6, 6) / 20) - 1
    out = audio + low_gain * sosfilt(low, audio) + high_gain * sosfilt(high, audio)
    return np.asarray(out, dtype=np.float32)


def phone_band(audio: FloatArray, rng: Rng) -> FloatArray:
    """A small microphone: little below 150-350 Hz, little above 3.5-7.5 kHz."""
    band = butter(
        4,
        [rng.uniform(150, 350), rng.uniform(3500, 7500)],
        btype="bandpass",
        fs=SAMPLE_RATE,
        output="sos",
    )
    return np.asarray(sosfilt(band, audio), dtype=np.float32)


def synthetic_room(rng: Rng) -> FloatArray:
    """An impulse response: a direct path, sparse early reflections, a decaying tail.

    The tail is noise under an exponential envelope reaching -60 dB at RT60,
    darkened (air and walls absorb the highs first) by a low-pass on a copy that
    takes over as it decays.
    """
    rt60 = rng.uniform(*_RT60)
    length = int(min(1.0, rt60 * 1.1) * SAMPLE_RATE)
    t = np.arange(length) / SAMPLE_RATE
    tail = rng.standard_normal(length) * np.exp(-6.9078 * t / rt60)
    dark = sosfilt(butter(1, rng.uniform(2000, 6000), fs=SAMPLE_RATE, output="sos"), tail)
    blend = np.clip(t / max(rt60, 1e-3), 0.0, 1.0)
    tail = (1 - blend) * tail + blend * dark
    tail *= 10 ** (rng.uniform(-18, -6) / 20)  # the direct-to-reverberant ratio
    for _ in range(int(rng.integers(3, 9))):
        tail[int(rng.uniform(0.002, 0.04) * SAMPLE_RATE)] += rng.uniform(-0.5, 0.5)
    tail[0] = 1.0
    return np.asarray(tail / np.sqrt(np.sum(tail**2)), dtype=np.float32)


def reverberate(audio: FloatArray, rng: Rng) -> FloatArray:
    """Convolve with a synthetic room, keeping the direct path in place and the level."""
    wet = fftconvolve(audio, synthetic_room(rng))[: audio.size]
    peak_in = float(np.max(np.abs(audio))) or 1.0
    peak_out = float(np.max(np.abs(wet))) or 1.0
    return np.asarray(wet * (peak_in / peak_out), dtype=np.float32)


def coloured_noise(size: int, rng: Rng) -> FloatArray:
    """Noise whose spectrum falls (or rises) as 1/f^decay, decay in [-1, 2]."""
    spectrum = np.fft.rfft(rng.standard_normal(size))
    freqs = np.fft.rfftfreq(size)
    freqs[0] = freqs[1] if size > 1 else 1.0
    shaped = np.fft.irfft(spectrum / freqs ** (rng.uniform(-1, 2) / 2), n=size)
    return (shaped / (np.std(shaped) + 1e-9)).astype(np.float32)


def background_from(banks: list[Bank], size: int, rng: Rng) -> FloatArray:
    """A random stretch of a random bank, looped if the segment is short."""
    bank = banks[int(rng.integers(len(banks)))]
    segment = to_float(bank.segment(int(rng.integers(len(bank)))))
    if segment.size == 0:
        return np.zeros(size, dtype=np.float32)
    if segment.size < size:
        segment = np.tile(segment, size // segment.size + 1)
    start = int(rng.integers(segment.size - size + 1))
    return segment[start : start + size]


def mix_at_snr(signal: FloatArray, noise: FloatArray, snr_db: float, active: slice) -> FloatArray:
    """Add ``noise`` so the signal's ACTIVE part stands ``snr_db`` above it."""
    signal_power = float(np.mean(signal[active] ** 2)) + 1e-12
    noise_power = float(np.mean(noise**2)) + 1e-12
    scale = np.sqrt(signal_power / (noise_power * 10 ** (snr_db / 10)))
    return np.asarray(signal + noise * scale, dtype=np.float32)


def place(clip: FloatArray, total: int, end_jitter_s: float, rng: Rng) -> tuple[FloatArray, slice]:
    """Left-pad (or cut the head of) a clip so it ends ``0..end_jitter_s`` before the end."""
    out = np.zeros(total, dtype=np.float32)
    jitter = int(rng.uniform(0, end_jitter_s) * SAMPLE_RATE)
    end = total - jitter
    start = max(0, end - clip.size)
    out[start:end] = clip[clip.size - (end - start) :]
    return out, slice(start, end)


def augment(
    clip: Int16Array,
    total: int,
    backgrounds: list[Bank],
    rng: Rng,
    end_jitter_s: float = 0.2,
) -> Int16Array:
    """One augmented, fixed-length window ending with the clip."""
    audio = to_float(clip)
    if rng.random() < _P_SPEED:
        audio = speed(audio, rng)
    if rng.random() < _P_EQ:
        audio = equalise(audio, rng)
    window, active = place(audio, total, end_jitter_s, rng)
    if rng.random() < _P_REVERB:
        window = reverberate(window, rng)
    if backgrounds and rng.random() < _P_BACKGROUND:
        window = mix_at_snr(
            window, background_from(backgrounds, total, rng), rng.uniform(*_SNR_DB), active
        )
    if rng.random() < _P_COLOURED:
        window = mix_at_snr(window, coloured_noise(total, rng), rng.uniform(10, 30), active)
    if rng.random() < _P_PHONE:
        window = phone_band(window, rng)
    if rng.random() < _P_DISTORTION:
        drive = rng.uniform(1.0, 4.0)
        window = (np.tanh(window * drive) / np.tanh(drive)).astype(np.float32)
    peak = float(np.max(np.abs(window))) or 1.0
    level = 10 ** (rng.uniform(*_LEVEL_DBFS) / 20)
    return to_int16(window * (level / peak))
