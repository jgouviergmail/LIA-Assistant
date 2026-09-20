"""Small operations on raw 16-bit mono PCM (little-endian), shared by the voice paths."""

from __future__ import annotations

import array
import sys
from typing import Final

#: Below this absolute sample value a sample counts as silence (16-bit scale).
SILENCE_THRESHOLD: Final = 400
#: What is kept on each side of the first and last audible sample.
SILENCE_MARGIN_MS: Final = 120


def trim_silence(
    pcm: bytes,
    *,
    sample_rate: int,
    threshold: int = SILENCE_THRESHOLD,
    margin_ms: int = SILENCE_MARGIN_MS,
) -> bytes:
    """The audible span of ``pcm`` with a short margin on both sides.

    A live model's output stream is continuous (full duplex): silence precedes
    and follows the sentence for as long as the session stays open, and a
    sample must not play it.

    Args:
        pcm: 16-bit mono little-endian samples.
        sample_rate: Samples per second (sizes the margin).
        threshold: The absolute value from which a sample is audible.
        margin_ms: The silence kept around the audible span.

    Returns:
        The trimmed bytes — empty when nothing in ``pcm`` is audible.
    """
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if sys.byteorder != "little":
        samples.byteswap()
    audible = [index for index, value in enumerate(samples) if abs(value) >= threshold]
    if not audible:
        return b""
    margin = sample_rate * margin_ms // 1000
    start = max(0, audible[0] - margin)
    end = min(len(samples), audible[-1] + 1 + margin)
    kept = samples[start:end]
    if sys.byteorder != "little":
        kept.byteswap()
    return kept.tobytes()


__all__ = ["SILENCE_MARGIN_MS", "SILENCE_THRESHOLD", "trim_silence"]
