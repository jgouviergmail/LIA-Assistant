"""A 16-bit mono PCM buffer as a WAV file (one writer, two readers).

The OpenAI STT path sends raw PCM as WAV; the live voice sample hands the
browser a WAV it can play with a plain ``<audio>`` element. Both used to
need the same 44-byte RIFF header.
"""

from __future__ import annotations

import struct


def wav_header(pcm_len: int, sample_rate: int) -> bytes:
    """The 44-byte RIFF header of a 16-bit mono PCM payload of ``pcm_len`` bytes."""
    byte_rate = sample_rate * 2
    return b"".join(
        [
            b"RIFF",
            struct.pack("<I", 36 + pcm_len),
            b"WAVEfmt ",
            struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, byte_rate, 2, 16),
            b"data",
            struct.pack("<I", pcm_len),
        ]
    )


def wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    """The whole WAV file: header then samples."""
    return wav_header(len(pcm), sample_rate) + pcm


__all__ = ["wav_bytes", "wav_header"]
