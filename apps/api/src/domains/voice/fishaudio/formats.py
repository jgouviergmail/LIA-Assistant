"""What a Fish Audio synthesis may be asked for, declared once.

The vendor takes a ``format`` (``mp3``, ``pcm``, ``wav``, ``opus``), a
``sample_rate`` and an ``mp3_bitrate``. LIA names one choice the way the
ElevenLabs client already does — ``codec_rate[_bitrate]`` — so the admin form
offers one list and the client reads one token. ``wav`` is not offered: streamed,
its RIFF header carries ``0xFFFFFFFF`` as its size (measured 2026-10-13), which
a strict reader refuses, and ``pcm`` wrapped once by LIA is the same lossless
audio. ``opus`` is not offered: no surface plays it.

The speaking rate the vendor accepts is [0.5, 2.0]; outside it, the whole line
is refused (measured: 422). A rate is therefore repaired, never sent out of
range — the ADR-184 doctrine for a bound that can be met mechanically.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal


@dataclass(frozen=True, slots=True)
class FishFormat:
    """One container a synthesis comes back in.

    Attributes:
        codec: ``mp3`` (encoded) or ``pcm`` (raw signed 16-bit mono samples).
        sample_rate: The rate the vendor encodes at.
        mp3_bitrate: The MP3 bitrate in kbps; ``None`` for ``pcm``.
    """

    codec: Literal["mp3", "pcm"]
    sample_rate: int
    mp3_bitrate: int | None = None

    def wire(self) -> dict[str, object]:
        """The request fields that ask for this container."""
        fields: dict[str, object] = {"format": self.codec, "sample_rate": self.sample_rate}
        if self.mp3_bitrate is not None:
            fields["mp3_bitrate"] = self.mp3_bitrate
        return fields


#: Every container LIA asks for, by the token the provider config stores.
FISH_OUTPUT_FORMATS: Final[Mapping[str, FishFormat]] = MappingProxyType(
    {
        "mp3_44100_64": FishFormat("mp3", 44100, 64),
        "mp3_44100_128": FishFormat("mp3", 44100, 128),
        "mp3_44100_192": FishFormat("mp3", 44100, 192),
        "pcm_16000": FishFormat("pcm", 16000),
        "pcm_24000": FishFormat("pcm", 24000),
        "pcm_44100": FishFormat("pcm", 44100),
    }
)
#: The vendor's own default container (``mp3`` at 128 kbps), named in LIA's vocabulary.
DEFAULT_FISH_OUTPUT_FORMAT: Final[str] = "mp3_44100_128"

#: The latency/quality trade-offs the vendor accepts (``normal`` is its default).
FISH_LATENCIES: Final[frozenset[str]] = frozenset({"normal", "balanced", "low"})

#: How a synthesis reaches the vendor: one HTTP request, or one session of its
#: WebSocket (ADR-345). HTTP is the default: measured on the free model, the socket
#: streams its audio but a sentence is returned whole, and its finish came no
#: sooner than an HTTP answer (later on a short sentence).
FISH_TRANSPORTS: Final[frozenset[str]] = frozenset({"http", "websocket"})
DEFAULT_FISH_TRANSPORT: Final[str] = "http"

#: The speaking-rate multiplier the vendor accepts, both ends included.
FISH_SPEED_MIN: Final[float] = 0.5
FISH_SPEED_MAX: Final[float] = 2.0


def bounded_speed(speed: float) -> float:
    """``speed`` brought inside the range the vendor accepts."""
    return min(max(speed, FISH_SPEED_MIN), FISH_SPEED_MAX)


__all__ = [
    "DEFAULT_FISH_OUTPUT_FORMAT",
    "DEFAULT_FISH_TRANSPORT",
    "FISH_LATENCIES",
    "FISH_OUTPUT_FORMATS",
    "FISH_SPEED_MAX",
    "FISH_SPEED_MIN",
    "FISH_TRANSPORTS",
    "FishFormat",
    "bounded_speed",
]
