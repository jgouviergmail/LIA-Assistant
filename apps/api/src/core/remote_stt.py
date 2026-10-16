"""Which remote engine transcribes, decided ONCE for the voice mode and the meetings (ADR-345).

The voice mode's remote transcription used to be ElevenLabs whatever the
administrator chose: the factory built the ElevenLabs client from the
``voice_transcription`` slot's MODEL while ignoring its PROVIDER, the profile
said « remote » was available when an ElevenLabs key existed, and the cost was
filed under ElevenLabs. A slot set to another engine sent that engine's model
name to ElevenLabs. Every reader now asks here: the slot (its provider is the
one that receives the audio), the deployment's kill switch for that provider,
and whether its key is configured.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from src.core.config import settings
from src.core.constants import (
    ELEVENLABS_PROVIDER_NAME,
    FISHAUDIO_PROVIDER_NAME,
    FISHAUDIO_STT_MAX_AUDIO_SECONDS,
    OPENAI_PROVIDER_NAME,
)
from src.core.llm_config_helper import get_llm_config_for_agent, get_provider_api_key

#: The remote engines LIA transcribes with — the voice mode's audio and a meeting's file.
REMOTE_STT_PROVIDERS: Final[tuple[str, ...]] = (
    ELEVENLABS_PROVIDER_NAME,
    OPENAI_PROVIDER_NAME,
    FISHAUDIO_PROVIDER_NAME,
)

#: The longest recording one request takes, where the vendor bounds it by DURATION
#: (OpenAI bounds it by size, which the meeting normalizer's bitrate already fits).
REMOTE_STT_MAX_AUDIO_SECONDS: Final[Mapping[str, int]] = MappingProxyType(
    {FISHAUDIO_PROVIDER_NAME: FISHAUDIO_STT_MAX_AUDIO_SECONDS}
)

#: Where an unconfigured timeout leaves a remote call (the voice mode's clip is short).
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0


@dataclass(frozen=True, slots=True)
class RemoteSttSlot:
    """The administrator's ``voice_transcription`` slot, as the remote engines read it.

    Attributes:
        provider: Who receives the audio.
        model: The model it is asked for.
        provider_config: The slot's provider JSON (ElevenLabs' regional host).
        timeout_seconds: The whole-call bound of a voice-mode transcription.
    """

    provider: str
    model: str
    provider_config: str | None
    timeout_seconds: float


def remote_stt_slot() -> RemoteSttSlot:
    """The effective ``voice_transcription`` slot (the code default, then the override)."""
    effective = get_llm_config_for_agent(settings, "voice_transcription")
    timeout = effective.timeout_seconds
    return RemoteSttSlot(
        provider=str(effective.provider),
        model=str(effective.model),
        provider_config=effective.provider_config,
        timeout_seconds=float(timeout) if timeout is not None else _DEFAULT_TIMEOUT_SECONDS,
    )


def remote_stt_enabled(provider: str) -> bool:
    """Whether the deployment lets ``provider`` transcribe (OpenAI has no switch)."""
    if provider == ELEVENLABS_PROVIDER_NAME:
        return bool(settings.elevenlabs_stt_enabled)
    if provider == FISHAUDIO_PROVIDER_NAME:
        return bool(settings.fishaudio_stt_enabled)
    return provider in REMOTE_STT_PROVIDERS


def request_cap_exceeded(provider: str, duration_seconds: float) -> int | None:
    """The per-request cap a recording of ``duration_seconds`` exceeds on ``provider``.

    Returns:
        The cap in seconds when the vendor bounds a request by duration and
        the recording is longer, else ``None``.
    """
    cap = REMOTE_STT_MAX_AUDIO_SECONDS.get(provider)
    return cap if cap is not None and duration_seconds > cap else None


def remote_stt_ready() -> bool:
    """Whether the voice mode's « remote » choice can transcribe now.

    Returns:
        ``True`` when the slot's provider is a remote engine LIA serves, the
        deployment lets it transcribe, and its key is configured.
    """
    provider = remote_stt_slot().provider
    return remote_stt_enabled(provider) and bool(get_provider_api_key(provider))


__all__ = [
    "REMOTE_STT_MAX_AUDIO_SECONDS",
    "REMOTE_STT_PROVIDERS",
    "RemoteSttSlot",
    "remote_stt_enabled",
    "remote_stt_ready",
    "remote_stt_slot",
    "request_cap_exceeded",
]
