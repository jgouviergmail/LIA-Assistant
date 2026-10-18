"""Factory selecting the active STT backend per user preference.

The voice WebSocket handler asks for an :class:`SttServiceProtocol`
implementation; this module decides between the local Sherpa-onnx Whisper
service (free, on-server) and the remote engine of the administrator's
``voice_transcription`` slot (paid, billed per audio duration) — ElevenLabs,
OpenAI or Fish Audio (ADR-345) — based on the per-user ``voice_stt_mode``
preference embedded in the WebSocket ticket.

The remote engine is the SLOT's provider, read through
:func:`~src.core.remote_stt.remote_stt_slot` with its model, timeout
and provider config, and its encrypted key from the provider-key cache — the
same reading the meetings and the voice preferences use.
"""

from __future__ import annotations

import json
from typing import Literal

import structlog

from src.core.constants import (
    DEFAULT_ELEVENLABS_BASE_URL,
    ELEVENLABS_PROVIDER_NAME,
    FISHAUDIO_PROVIDER_NAME,
    OPENAI_PROVIDER_NAME,
)
from src.core.llm_config_helper import get_provider_api_key
from src.core.remote_stt import REMOTE_STT_PROVIDERS, RemoteSttSlot, remote_stt_slot
from src.domains.voice.stt.elevenlabs_stt import ElevenLabsSttService
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.fishaudio_stt import FishAudioSttService
from src.domains.voice.stt.openai_stt import OpenAISttService
from src.domains.voice.stt.protocol import SttFileTranscriberProtocol, SttServiceProtocol
from src.domains.voice.stt.sherpa_stt import SherpaSttService, get_stt_service

logger = structlog.get_logger(__name__)

VoiceSttMode = Literal["local", "remote"]


def _resolve_remote_base_url(provider_config_raw: object) -> str:
    """Pull a ``base_url`` out of the optional ``provider_config`` JSON.

    ``LLMAgentConfig.provider_config`` is a JSON string; admins may stash a
    custom ElevenLabs base URL there (e.g. ``api.eu.residency.elevenlabs.io``
    for EU residency). Anything malformed falls back to the global default.
    """
    if not provider_config_raw or not isinstance(provider_config_raw, str):
        return DEFAULT_ELEVENLABS_BASE_URL
    try:
        parsed = json.loads(provider_config_raw)
    except TypeError, ValueError:
        return DEFAULT_ELEVENLABS_BASE_URL
    if isinstance(parsed, dict):
        candidate = parsed.get("base_url")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return DEFAULT_ELEVENLABS_BASE_URL


RemoteSttService = ElevenLabsSttService | OpenAISttService | FishAudioSttService


def build_remote_stt(
    provider: str,
    *,
    api_key: str,
    model: str,
    timeout_seconds: float,
    provider_config: str | None = None,
) -> RemoteSttService:
    """One remote engine — it transcribes the voice mode's clip and a meeting's file.

    Args:
        provider: ``"elevenlabs"``, ``"openai"`` or ``"fishaudio"``.
        api_key: The provider key (from the encrypted key store).
        model: Provider model name.
        timeout_seconds: Whole-call HTTP timeout.
        provider_config: The ``voice_transcription`` slot's provider JSON, when
            the slot names this provider (ElevenLabs' regional host).

    Raises:
        STTProviderError: Unknown provider (a configuration defect, never a
            user error — surfaced as a classified code).
    """
    if provider == ELEVENLABS_PROVIDER_NAME:
        return ElevenLabsSttService(
            api_key=api_key,
            model=model,
            base_url=_resolve_remote_base_url(provider_config),
            timeout_seconds=timeout_seconds,
        )
    if provider == OPENAI_PROVIDER_NAME:
        return OpenAISttService(api_key=api_key, model=model, timeout_seconds=timeout_seconds)
    if provider == FISHAUDIO_PROVIDER_NAME:
        return FishAudioSttService(api_key=api_key, model=model, timeout_seconds=timeout_seconds)
    raise STTProviderError(
        code="provider_unknown", message=f"No remote STT engine for provider {provider!r}"
    )


def build_file_transcriber(
    provider: str, *, api_key: str, model: str, timeout_seconds: float
) -> SttFileTranscriberProtocol:
    """A whole-file transcriber for one remote provider (meetings, ADR-258).

    The ElevenLabs regional ``base_url`` override travels with the admin
    ``voice_transcription`` slot; it is honoured here exactly as on the
    WebSocket path so EU-residency deployments never leak audio to the US host.

    Args:
        provider: A provider of :data:`~src.core.remote_stt.REMOTE_STT_PROVIDERS`.
        api_key: The provider key (from the encrypted key store).
        model: Provider model name.
        timeout_seconds: Whole-call HTTP timeout (a meeting takes minutes).

    Raises:
        STTProviderError: Unknown provider (a configuration defect, never a
            user error — surfaced as a classified code).
    """
    slot = remote_stt_slot()
    return build_remote_stt(
        provider,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        provider_config=slot.provider_config if slot.provider == provider else None,
    )


def get_stt_service_for_mode(
    mode: VoiceSttMode, *, slot: RemoteSttSlot | None = None
) -> SttServiceProtocol:
    """Return the STT backend matching ``mode``.

    Args:
        mode: ``"local"`` (Sherpa-onnx, free) or ``"remote"`` (the
            ``voice_transcription`` slot's engine).
        slot: The slot the caller already read (its cost is filed under it),
            else read here.

    Raises:
        STTProviderError: when ``mode='remote'`` but the slot names no remote
            engine LIA serves (``provider_unknown``) or its provider's key is
            not configured (``<provider>_api_key_missing``: an administrator
            adds it under the Provider Keys before anyone can opt into remote).
    """
    if mode == "remote":
        slot = slot or remote_stt_slot()
        if slot.provider not in REMOTE_STT_PROVIDERS:
            raise STTProviderError(
                code="provider_unknown",
                message=f"No remote STT engine for provider {slot.provider!r}",
            )
        api_key = get_provider_api_key(slot.provider)
        if not api_key:
            raise STTProviderError(
                code=f"{slot.provider}_api_key_missing",
                message=(
                    f"The {slot.provider} API key is not configured. "
                    "Add it under Settings → Administration → LLM Configuration → "
                    "Provider API Keys."
                ),
            )
        logger.debug(
            "stt_factory_remote_resolved",
            provider=slot.provider,
            model=slot.model,
            timeout_seconds=slot.timeout_seconds,
        )
        return build_remote_stt(
            slot.provider,
            api_key=api_key,
            model=slot.model,
            timeout_seconds=slot.timeout_seconds,
            provider_config=slot.provider_config,
        )

    # "local" branch — singleton Sherpa instance, lazily initialised.
    sherpa: SherpaSttService = get_stt_service()
    return sherpa
