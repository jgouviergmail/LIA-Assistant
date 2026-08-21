"""TTS client factory — driven by Configuration LLM (``voice_tts`` type).

Reads the active ``voice_tts`` override from :class:`LLMConfigOverrideCache`
(merged with :data:`LLM_DEFAULTS`) and instantiates the matching client
(Edge / OpenAI / ElevenLabs / future Gemini). The voice IDs and provider-
specific tuning (speed, response_format, rate, pitch, volume, voice_settings,
…) live in the override's ``provider_config`` JSONB blob — see ADR-081.

Shape of the JSONB blob (all keys optional):

```json
{
  "voice_male": "fr-FR-RemyMultilingualNeural",
  "voice_female": "fr-FR-VivienneMultilingualNeural",
  "rate": "+10%",            // edge only
  "pitch": "+0Hz",           // edge only
  "volume": "+0%",           // edge only
  "speed": 1.1,              // openai only
  "response_format": "mp3",  // openai only
  "output_format": "mp3_44100_128",  // elevenlabs only
  "voice_settings": {        // elevenlabs only
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": true
  }
}
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import merge_config
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.voice.client import EdgeTTSClient
from src.domains.voice.elevenlabs_tts_client import ElevenLabsTTSClient
from src.domains.voice.openai_tts_client import OpenAITTSClient
from src.domains.voice.protocol import TTSClient

logger = structlog.get_logger(__name__)

TTSProvider = Literal["edge", "openai", "elevenlabs", "gemini"]

# Free providers — used by the cost tracker to skip useless lookups.
_FREE_PROVIDERS: frozenset[str] = frozenset({"edge"})


@dataclass
class TTSConfig:
    """Effective TTS configuration consumed by the voice service.

    ``model`` is mandatory (used both by the provider and by the cost
    tracker for pricing lookups). The remaining fields are populated
    from the JSONB ``provider_config`` blob — only the keys relevant
    to the active provider are filled, the rest stay None.

    Notes:
        - ``mode`` is preserved as a back-compat alias: ``"hd"`` for any
          paid provider, ``"standard"`` for free providers (Edge). Some
          downstream call sites still gate logic on ``mode == "hd"``.
        - ``is_paid`` is the precise modern flag — prefer it in new code.
    """

    provider: TTSProvider
    model: str
    voice_male: str
    voice_female: str
    # Edge-specific.
    rate: str | None = None
    pitch: str | None = None
    volume: str | None = None
    # OpenAI-specific.
    speed: float | None = None
    response_format: str | None = None
    # ElevenLabs-specific.
    output_format: str | None = None
    voice_settings: dict[str, Any] = field(default_factory=dict)

    @property
    def is_paid(self) -> bool:
        return self.provider not in _FREE_PROVIDERS

    @property
    def mode(self) -> Literal["standard", "hd"]:
        """Back-compat alias for legacy callers gating on ``mode == "hd"``."""
        return "hd" if self.is_paid else "standard"


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


async def get_tts_config() -> TTSConfig:
    """Read the active ``voice_tts`` config + parse the provider_config JSONB."""
    effective = _resolve_effective_config()
    extras = _parse_provider_config(effective.provider_config)

    voice_male = str(extras.get("voice_male") or _default_voice(effective.provider, "male"))
    voice_female = str(extras.get("voice_female") or _default_voice(effective.provider, "female"))

    return TTSConfig(
        provider=effective.provider,  # type: ignore[arg-type]
        model=effective.model,
        voice_male=voice_male,
        voice_female=voice_female,
        rate=_str_or_none(extras.get("rate")),
        pitch=_str_or_none(extras.get("pitch")),
        volume=_str_or_none(extras.get("volume")),
        speed=_float_or_none(extras.get("speed")),
        response_format=_str_or_none(extras.get("response_format")),
        output_format=_str_or_none(extras.get("output_format")),
        voice_settings=_dict_or_empty(extras.get("voice_settings")),
    )


async def get_tts_client() -> TTSClient:
    """Create the TTS client matching the active ``voice_tts`` config."""
    cfg = await get_tts_config()
    logger.debug(
        "tts_factory_resolved",
        provider=cfg.provider,
        model=cfg.model,
        voice_male=cfg.voice_male,
        voice_female=cfg.voice_female,
        is_paid=cfg.is_paid,
    )
    return _instantiate_client(cfg)


def get_tts_client_sync(cfg: TTSConfig) -> TTSClient:
    """Synchronous variant for non-async call sites holding a config already."""
    return _instantiate_client(cfg)


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _resolve_effective_config() -> LLMAgentConfig:
    defaults = LLM_DEFAULTS["voice_tts"]
    override = LLMConfigOverrideCache.get_override("voice_tts") or {}
    return merge_config(defaults, override)


def _parse_provider_config(raw: object) -> dict[str, Any]:
    if not raw or not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except TypeError, ValueError:
        logger.warning("tts_provider_config_invalid_json", raw_preview=str(raw)[:120])
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _str_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _default_voice(provider: str, gender: Literal["male", "female"]) -> str:
    """Conservative defaults so the factory never returns an empty voice_id."""
    if provider == "edge":
        return (
            "fr-FR-RemyMultilingualNeural"
            if gender == "male"
            else "fr-FR-VivienneMultilingualNeural"
        )
    if provider == "openai":
        return "echo" if gender == "male" else "nova"
    if provider == "elevenlabs":
        # The real default lives in the JSONB blob; fall back to the
        # popular built-in voice_id "Rachel" so a misconfigured account
        # still produces audible output instead of crashing.
        return "21m00Tcm4TlvDq8ikWAM"
    return ""


def _instantiate_client(cfg: TTSConfig) -> TTSClient:
    if cfg.provider == "edge":
        return EdgeTTSClient(  # type: ignore[return-value]
            rate=cfg.rate,
            pitch=cfg.pitch,
            volume=cfg.volume,
        )
    if cfg.provider == "openai":
        if not LLMConfigOverrideCache.get_api_key("openai"):
            logger.warning("openai_tts_missing_api_key_falling_back_to_edge")
            return _instantiate_client(_fallback_edge_config())
        return OpenAITTSClient(  # type: ignore[return-value]
            model=cfg.model,
            speed=cfg.speed,
            response_format=cfg.response_format,  # type: ignore[arg-type]
        )
    if cfg.provider == "elevenlabs":
        if not LLMConfigOverrideCache.get_api_key("elevenlabs"):
            logger.warning("elevenlabs_tts_missing_api_key_falling_back_to_edge")
            return _instantiate_client(_fallback_edge_config())
        return ElevenLabsTTSClient(
            model=cfg.model,
            output_format=cfg.output_format or "mp3_44100_128",
            voice_settings=cfg.voice_settings,
        )
    if cfg.provider == "gemini":
        # TODO: implement GeminiTTSClient when the provider lands a public
        # streaming TTS endpoint. Falling back to Edge keeps the voice
        # comments operational instead of crashing the response node.
        logger.warning("gemini_tts_not_implemented_falling_back_to_edge")
        return _instantiate_client(_fallback_edge_config())

    logger.error("tts_factory_unknown_provider", provider=cfg.provider)
    return _instantiate_client(_fallback_edge_config())


def _fallback_edge_config() -> TTSConfig:
    """Last-resort Edge config when the active override targets a paid
    provider whose API key is missing. Carries neutral SSML tuning
    (no rate/pitch/volume offset) so synthesis stays audible without
    surprising the listener.
    """
    return TTSConfig(
        provider="edge",
        model="edge-tts",
        voice_male=_default_voice("edge", "male"),
        voice_female=_default_voice("edge", "female"),
        rate="+0%",
        pitch="+0Hz",
        volume="+0%",
    )
