"""Factory selecting the active STT backend per user preference.

The voice WebSocket handler asks for an :class:`SttServiceProtocol`
implementation; this module decides between the local Sherpa-onnx Whisper
service (free, on-server) and the remote ElevenLabs Scribe service (paid,
billed per audio duration), based on the per-user
``voice_stt_mode`` preference embedded in the WebSocket ticket.

The remote branch reads the active LLM config for the ``voice_transcription``
type (provider/model/timeout/provider_config) plus the encrypted ElevenLabs
API key, both surfaced via :class:`LLMConfigOverrideCache` (the same cache
used by the rest of the LLM stack — no extra round-trip).
"""

from __future__ import annotations

import json
from typing import Literal

import structlog

from src.core.constants import (
    DEFAULT_ELEVENLABS_BASE_URL,
    ELEVENLABS_PROVIDER_NAME,
    OPENAI_PROVIDER_NAME,
)
from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import merge_config
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.voice.stt.elevenlabs_stt import ElevenLabsSttService
from src.domains.voice.stt.exceptions import STTProviderError
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


def build_file_transcriber(
    provider: str, *, api_key: str, model: str, timeout_seconds: float
) -> SttFileTranscriberProtocol:
    """A whole-file transcriber for one remote provider (meetings, ADR-258).

    The ElevenLabs regional ``base_url`` override travels with the admin
    ``voice_transcription`` slot; it is honoured here exactly as on the
    WebSocket path so EU-residency deployments never leak audio to the US host.

    Args:
        provider: ``"elevenlabs"`` or ``"openai"``.
        api_key: The provider key (from the encrypted key store).
        model: Provider model name.
        timeout_seconds: Whole-call HTTP timeout (a meeting takes minutes).

    Raises:
        STTProviderError: Unknown provider (a configuration defect, never a
            user error — surfaced as a classified code).
    """
    if provider == ELEVENLABS_PROVIDER_NAME:
        defaults = LLM_DEFAULTS["voice_transcription"]
        overrides = LLMConfigOverrideCache.get_override("voice_transcription") or {}
        effective: LLMAgentConfig = merge_config(defaults, overrides)
        base_url = (
            _resolve_remote_base_url(effective.provider_config)
            if str(effective.provider) == ELEVENLABS_PROVIDER_NAME
            else DEFAULT_ELEVENLABS_BASE_URL
        )
        return ElevenLabsSttService(
            api_key=api_key, model=model, base_url=base_url, timeout_seconds=timeout_seconds
        )
    if provider == OPENAI_PROVIDER_NAME:
        return OpenAISttService(api_key=api_key, model=model, timeout_seconds=timeout_seconds)
    raise STTProviderError(
        code="provider_unknown", message=f"No file transcriber for provider {provider!r}"
    )


def get_stt_service_for_mode(mode: VoiceSttMode) -> SttServiceProtocol:
    """Return the STT backend matching ``mode``.

    Args:
        mode: ``"local"`` (Sherpa-onnx, free) or ``"remote"`` (ElevenLabs).

    Raises:
        STTProviderError: when ``mode='remote'`` but the ElevenLabs API key
            is not configured (admin must add it via the Pricing/Provider
            Keys admin UI before any user can opt into remote STT).
    """
    if mode == "remote":
        defaults = LLM_DEFAULTS["voice_transcription"]
        overrides = LLMConfigOverrideCache.get_override("voice_transcription") or {}
        effective: LLMAgentConfig = merge_config(defaults, overrides)

        api_key = LLMConfigOverrideCache.get_api_key("elevenlabs")
        if not api_key:
            raise STTProviderError(
                code="elevenlabs_api_key_missing",
                message=(
                    "ElevenLabs API key is not configured. "
                    "Add it under Settings → Tarification LLM Texte → Provider Keys."
                ),
            )

        base_url = _resolve_remote_base_url(effective.provider_config)
        logger.debug(
            "stt_factory_remote_resolved",
            model=effective.model,
            base_url=base_url,
            timeout_seconds=effective.timeout_seconds,
        )
        # ``timeout_seconds`` is optional on ``LLMAgentConfig``; the
        # ElevenLabs client expects a concrete float. The default keeps the
        # remote STT call bounded (matches the previous hard-coded 60 s).
        timeout = (
            float(effective.timeout_seconds) if effective.timeout_seconds is not None else 60.0
        )
        return ElevenLabsSttService(
            api_key=api_key,
            model=effective.model,
            base_url=base_url,
            timeout_seconds=timeout,
        )

    # "local" branch — singleton Sherpa instance, lazily initialised.
    sherpa: SherpaSttService = get_stt_service()
    return sherpa
