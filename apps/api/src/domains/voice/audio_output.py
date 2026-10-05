"""Playable container metadata, without changing a TTS client's wire bytes.

The radio probes and decodes each line before its one final MP3 encoding.
Headerless PCM/u-law needs its configured rate and encoding in a WAV header;
encoded responses pass through unchanged. No sample is decoded or resampled.
"""

from __future__ import annotations

import base64
import struct

from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.protocol import RawAudioSpec, RawAudioTTSClient, TTSClient
from src.infrastructure.media.pcm import wav_container


def _raw_spec(client: TTSClient) -> RawAudioSpec | None:
    return client.raw_audio_spec if isinstance(client, RawAudioTTSClient) else None


def mix_audio_format(client: TTSClient) -> str:
    """The extension of the audio once it is made readable by a mixer."""
    return "wav" if _raw_spec(client) is not None else client.audio_format


def _ulaw_container(audio: bytes, sample_rate: int) -> bytes:
    """Mono G.711 u-law in RIFF/WAVE, with its sample count and odd-byte pad."""
    fmt = struct.pack("<HHIIHHH", 7, 1, sample_rate, sample_rate, 1, 8, 0)
    body = (
        b"WAVEfmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"fact"
        + struct.pack("<II", 4, len(audio))
        + b"data"
        + struct.pack("<I", len(audio))
        + audio
        + (b"\x00" if len(audio) % 2 else b"")
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


def audio_for_mix(client: TTSClient, audio: bytes) -> bytes:
    """Wrap raw samples in WAV; retain encoded responses byte for byte.

    Billing stays with the synthesis, before this local operation. Refuse a
    malformed raw response without asking the provider to produce it again.
    """
    spec = _raw_spec(client)
    if spec is None:
        return audio
    if not audio or spec.sample_rate <= 0 or (spec.encoding == "pcm_s16le" and len(audio) % 2):
        raise TTSProviderError("provider_invalid_response", "Incomplete raw TTS audio samples.")
    if spec.encoding == "ulaw":
        return _ulaw_container(audio, spec.sample_rate)
    return wav_container(audio, sample_rate=spec.sample_rate)


async def synthesize_playable_base64(
    client: TTSClient, text: str, voice_name: str | None = None, **kwargs: object
) -> str:
    """Keep encoded synthesis unchanged; wrap raw samples once for browser decoding.

    The provider is called once. Its raw response and billing contract remain
    unchanged; only the presentation container carries the configured rate.
    """
    if _raw_spec(client) is None:
        return await client.synthesize_base64(text=text, voice_name=voice_name, **kwargs)
    audio = await client.synthesize(text=text, voice_name=voice_name, **kwargs)
    return base64.b64encode(audio_for_mix(client, audio)).decode("ascii")
