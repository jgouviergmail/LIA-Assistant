"""TTS client factory — driven by Configuration LLM (one TTS slot per surface).

Reads a TTS slot's override from :class:`LLMConfigOverrideCache` (merged with
:data:`LLM_DEFAULTS`) and instantiates the matching client (Edge / OpenAI /
ElevenLabs / Gemini / Fish Audio). The chat's voice comments read ``voice_tts``; another
surface names its own slot. The voice IDs and provider-specific tuning (speed,
response_format, rate, pitch, volume, voice_settings, …) live in the override's
``provider_config`` JSONB blob — see ADR-081.

Shape of the JSONB blob (all keys optional):

```json
{
  "voice_male": "fr-FR-RemyMultilingualNeural",
  "voice_female": "fr-FR-VivienneMultilingualNeural",
  "rate": "+10%",            // edge only
  "pitch": "+0Hz",           // edge only
  "volume": "+0%",           // edge only
  "speed": 1.1,              // openai, fishaudio
  "response_format": "mp3",  // openai only
  "output_format": "mp3_44100_128",  // elevenlabs, fishaudio
  "latency": "balanced",     // fishaudio only
  "transport": "http",       // fishaudio only: http | websocket
  "voice_settings": {        // elevenlabs only
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": true
  }
}
```

A provider no client serves or a missing key: a STRICT caller gets a
:class:`TTSProviderError` and chooses what to do; a lenient caller (the chat's
voice comments, which must keep speaking) gets Edge, and the substitution is
logged. Nothing substitutes an engine for a strict caller. A substituted client
travels WITH the configuration it was built from (:func:`serve_tts`): the
configured engine's voice ids mean nothing to Edge, so a caller reading its
voices from the configuration it asked for heard silence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, NamedTuple, get_args

import structlog

from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import merge_config
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.voice.client import EdgeTTSClient
from src.domains.voice.elevenlabs_tts_client import ElevenLabsTTSClient
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.families import TTS_FAMILIES, TtsBilling, family_of
from src.domains.voice.fishaudio.tts_client import FishAudioTTSClient
from src.domains.voice.gemini_tts_client import GeminiOutputFormat, GeminiTTSClient
from src.domains.voice.openai_tts_client import OpenAITTSClient
from src.domains.voice.protocol import TTSClient

logger = structlog.get_logger(__name__)

TTSProvider = Literal["edge", "openai", "elevenlabs", "gemini", "fishaudio"]

#: The chat's voice-comment slot — the default for every legacy caller.
DEFAULT_TTS_SLOT = "voice_tts"

# Every provider the configuration may name is declared by a family, and every
# family is a provider the configuration may name (ADR-085, checked at import).
if set(get_args(TTSProvider)) != set(TTS_FAMILIES):
    raise RuntimeError(
        f"TTS providers {sorted(get_args(TTSProvider))} and TTS families "
        f"{sorted(TTS_FAMILIES)} disagree"
    )


@dataclass
class TTSConfig:
    """Effective TTS configuration consumed by a voice surface.

    ``model`` is mandatory (used both by the provider and by the cost
    tracker for pricing lookups). The remaining fields are populated
    from the JSONB ``provider_config`` blob — only the keys relevant
    to the active provider are filled, the rest stay None.

    Notes:
        - ``provider`` is the configured id as stored: a value no family
          serves is kept verbatim so the factory can refuse or replace it
          explicitly, never silently narrowed to a known one.
        - ``is_paid`` says whether the engine bills (an unknown one does).
        - ``extras`` is the parsed blob itself, for a surface that reads a
          key of its own (a radio's cast).
    """

    provider: str
    model: str
    voice_male: str
    voice_female: str
    # Edge-specific.
    rate: str | None = None
    pitch: str | None = None
    volume: str | None = None
    # OpenAI and Fish Audio.
    speed: float | None = None
    # OpenAI-specific.
    response_format: str | None = None
    # ElevenLabs and Fish Audio.
    output_format: str | None = None
    # ElevenLabs-specific.
    voice_settings: dict[str, Any] = field(default_factory=dict)
    # Fish Audio-specific: the latency/quality trade-off, and how a request travels.
    latency: str | None = None
    transport: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def is_paid(self) -> bool:
        family = family_of(self.provider)
        return family is None or family.billing is not TtsBilling.FREE


class ServedTts(NamedTuple):
    """A client, and the configuration it was built from.

    Attributes:
        config: Edge's configuration when Edge stands in for the configured
            engine — the voices and the model a caller reads come from here.
        client: The client that speaks.
    """

    config: TTSConfig
    client: TTSClient


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


async def get_tts_config(slot: str = DEFAULT_TTS_SLOT) -> TTSConfig:
    """Read a TTS slot's active config and parse its provider_config JSONB.

    Args:
        slot: The TTS slot (a key of ``LLM_DEFAULTS`` whose kind is ``tts``).

    Returns:
        The effective configuration.
    """
    return tts_config_from_effective(_resolve_effective_config(slot))


def tts_config_from_effective(effective: LLMAgentConfig) -> TTSConfig:
    """Parse a resolved slot identically for runtime and committed library references."""
    extras = _parse_provider_config(effective.provider_config)

    voice_male = str(extras.get("voice_male") or _default_voice(effective.provider, "male"))
    voice_female = str(extras.get("voice_female") or _default_voice(effective.provider, "female"))

    return TTSConfig(
        provider=effective.provider,
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
        latency=_str_or_none(extras.get("latency")),
        transport=_str_or_none(extras.get("transport")),
        extras=extras,
    )


async def get_tts_client(
    slot: str = DEFAULT_TTS_SLOT,
    *,
    strict: bool = False,
    gemini_output: GeminiOutputFormat = "mp3",
) -> TTSClient:
    """Create the TTS client matching a slot's active config.

    Args:
        slot: The TTS slot to read.
        strict: Refuse instead of substituting another engine.
        gemini_output: The container a Gemini client returns.

    Returns:
        A client for the configured engine (or Edge, for a lenient caller).

    Raises:
        TTSProviderError: For a strict caller whose engine cannot be served.
    """
    cfg = await get_tts_config(slot)
    logger.debug(
        "tts_factory_resolved",
        slot=slot,
        provider=cfg.provider,
        model=cfg.model,
        is_paid=cfg.is_paid,
    )
    return serve_tts(cfg, strict=strict, gemini_output=gemini_output).client


def get_tts_client_sync(
    cfg: TTSConfig,
    *,
    strict: bool = False,
    gemini_output: GeminiOutputFormat = "mp3",
) -> TTSClient:
    """Synchronous variant for call sites holding a config already.

    Args:
        cfg: The effective configuration.
        strict: Refuse instead of substituting another engine.
        gemini_output: The container a Gemini client returns.

    Returns:
        The client.

    Raises:
        TTSProviderError: For a strict caller whose engine cannot be served.
    """
    return serve_tts(cfg, strict=strict, gemini_output=gemini_output).client


def serve_tts(
    cfg: TTSConfig,
    *,
    strict: bool = False,
    gemini_output: GeminiOutputFormat = "mp3",
) -> ServedTts:
    """The client serving ``cfg``, with the configuration it was built from.

    Args:
        cfg: The effective configuration.
        strict: Refuse instead of substituting another engine.
        gemini_output: The container a Gemini client returns.

    Returns:
        ``cfg`` and its client, or — for a lenient caller whose engine cannot
        be served — Edge's own configuration and client.

    Raises:
        TTSProviderError: For a strict caller whose engine cannot be served.
    """
    reason = unservable_reason(cfg)
    if reason is None:
        return ServedTts(cfg, _instantiate_client(cfg, gemini_output=gemini_output))
    if strict:
        raise TTSProviderError(
            code="tts_unavailable",
            message=f"TTS provider {cfg.provider!r} cannot be served: {reason}",
            details={"provider": cfg.provider, "reason": reason},
        )
    logger.warning("tts_factory_falling_back_to_edge", provider=cfg.provider, reason=reason)
    fallback = _fallback_edge_config()
    return ServedTts(fallback, _instantiate_client(fallback))


def served_config(cfg: TTSConfig) -> TTSConfig:
    """The configuration that speaks for a lenient caller, decided without a client.

    ``cfg`` itself, or Edge's when ``cfg`` cannot be served — the engine
    :func:`serve_tts` would build. A page that offers the voices LIA speaks
    with reads them here, so it offers the voices of the engine that speaks.

    Args:
        cfg: The effective configuration.

    Returns:
        The configuration a lenient :func:`serve_tts` builds its client from.
    """
    return cfg if unservable_reason(cfg) is None else _fallback_edge_config()


def unservable_reason(cfg: TTSConfig) -> str | None:
    """Why ``cfg`` cannot be served, or ``None`` when it can.

    The factory's own test, public for a caller that must decide BEFORE it
    builds a client (a radio start refuses rather than airing in silence).

    Args:
        cfg: The effective configuration.

    Returns:
        ``no_client`` or ``api_key_missing``; None when served.
    """
    family = family_of(cfg.provider)
    if family is None:
        return "no_client"
    if family.billing is not TtsBilling.FREE and not LLMConfigOverrideCache.get_api_key(
        cfg.provider
    ):
        return "api_key_missing"
    return None


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _resolve_effective_config(slot: str) -> LLMAgentConfig:
    defaults = LLM_DEFAULTS[slot]
    override = LLMConfigOverrideCache.get_override(slot) or {}
    return merge_config(defaults, override)


def _parse_provider_config(raw: object) -> dict[str, Any]:
    if not raw or not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except TypeError, ValueError:
        logger.warning("tts_provider_config_invalid_json", raw_length=len(str(raw)))
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
    if provider == "gemini":
        return "Puck" if gender == "male" else "Kore"
    if provider == "fishaudio":
        # Two licensed French voices of the vendor's library, like Edge's
        # defaults (read 2026-10-13); the vendor detects the language from the
        # text, so they speak the other five languages too.
        return (
            "fce1bed339724d91b5c9c4d01bb6e796"
            if gender == "male"
            else "eab784f1248946f3a34581aad44ce579"
        )
    return ""


def _instantiate_client(cfg: TTSConfig, *, gemini_output: GeminiOutputFormat = "mp3") -> TTSClient:
    """Build the client of a SERVABLE config (checked by the caller)."""
    if cfg.provider == "openai":
        return OpenAITTSClient(  # type: ignore[return-value]
            model=cfg.model,
            speed=cfg.speed,
            response_format=cfg.response_format,  # type: ignore[arg-type]
        )
    if cfg.provider == "elevenlabs":
        return ElevenLabsTTSClient(
            model=cfg.model,
            output_format=cfg.output_format or "mp3_44100_128",
            voice_settings=cfg.voice_settings,
        )
    if cfg.provider == "gemini":
        return GeminiTTSClient(model=cfg.model, output_format=gemini_output)
    if cfg.provider == "fishaudio":
        return FishAudioTTSClient(
            model=cfg.model,
            output_format=cfg.output_format,
            latency=cfg.latency,
            speed=cfg.speed,
            transport=cfg.transport,
        )
    return EdgeTTSClient(  # type: ignore[return-value]
        rate=cfg.rate,
        pitch=cfg.pitch,
        volume=cfg.volume,
    )


def _fallback_edge_config() -> TTSConfig:
    """Last-resort Edge config for a lenient caller whose engine cannot be served.

    Carries neutral SSML tuning (no rate/pitch/volume offset) so synthesis
    stays audible without surprising the listener.
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
