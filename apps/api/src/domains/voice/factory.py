"""
TTS Client Factory.

Creates TTS client instances based on the current voice mode (Standard/HD).
The mode is controlled by administrators and stored in the database.

Architecture:
- Standard mode: Edge TTS (free, high quality)
- HD mode: OpenAI/Gemini TTS (paid, premium quality)

Usage:
    from src.domains.voice.factory import get_tts_client, get_tts_config

    # Get client based on current admin-controlled mode
    client = await get_tts_client()

    # Get configuration (voice names, etc.) for current mode
    config = await get_tts_config()

Created: 2026-01-15
Updated: 2026-01-16 - Refactored to use Standard/HD mode architecture
"""

from dataclasses import dataclass
from typing import Literal

import structlog

from src.core.config import settings
from src.core.config.voice import VoiceTTSMode
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.client import EdgeTTSClient
from src.domains.voice.openai_tts_client import OpenAITTSClient
from src.domains.voice.protocol import TTSClient

logger = structlog.get_logger(__name__)

# Type alias for TTS providers
TTSProvider = Literal["edge", "openai", "gemini"]


@dataclass
class TTSConfig:
    """
    TTS configuration for the current mode.

    Contains all settings needed for TTS synthesis based on the
    current voice mode (Standard/HD).
    """

    mode: VoiceTTSMode
    provider: TTSProvider
    voice_male: str
    voice_female: str
    # Standard mode (Edge TTS) specific
    rate: str | None = None
    pitch: str | None = None
    volume: str | None = None
    # HD mode (OpenAI/Gemini) specific
    model: str | None = None
    speed: float | None = None
    response_format: str | None = None


async def get_voice_mode() -> VoiceTTSMode:
    """
    Get current voice TTS mode from cache/DB.

    Returns:
        "standard" or "hd"
    """
    from src.domains.system_settings.service import get_voice_tts_mode

    return await get_voice_tts_mode()


async def get_tts_config() -> TTSConfig:
    """
    Get TTS configuration for the current voice mode.

    Reads the current mode from the database (cached in Redis) and
    returns the appropriate configuration.

    Returns:
        TTSConfig with all settings for the current mode.
    """
    mode = await get_voice_mode()

    if mode == "standard":
        return TTSConfig(
            mode="standard",
            provider=settings.voice_tts_standard_provider,
            voice_male=settings.voice_tts_standard_voice_male,
            voice_female=settings.voice_tts_standard_voice_female,
            rate=settings.voice_tts_standard_rate,
            pitch=settings.voice_tts_standard_pitch,
            volume=settings.voice_tts_standard_volume,
        )
    else:  # hd
        return TTSConfig(
            mode="hd",
            provider=settings.voice_tts_hd_provider,
            voice_male=settings.voice_tts_hd_voice_male,
            voice_female=settings.voice_tts_hd_voice_female,
            model=settings.voice_tts_hd_model,
            speed=settings.voice_tts_hd_speed,
            response_format=settings.voice_tts_hd_response_format,
        )


async def get_tts_client(mode: VoiceTTSMode | None = None) -> TTSClient:
    """
    Get a TTS client instance based on the current voice mode.

    Factory function that creates the appropriate TTS client based on
    the admin-controlled voice mode setting.

    Args:
        mode: Optional mode override. If None, reads from database.
              Use this for testing or when you need a specific mode.

    Returns:
        TTSClient instance (EdgeTTSClient, OpenAITTSClient, or GeminiTTSClient).

    Example:
        # Use current mode from database
        client = await get_tts_client()

        # Force HD mode (for testing)
        client = await get_tts_client(mode="hd")

        # Synthesize audio
        audio = await client.synthesize("Hello world", voice_name="nova")
    """
    if mode is None:
        mode = await get_voice_mode()

    logger.debug("tts_factory_create", mode=mode)

    if mode == "standard":
        return _create_standard_client()
    else:  # hd
        return await _create_hd_client()


def _create_standard_client() -> TTSClient:
    """Create client for Standard mode (Edge TTS)."""
    logger.debug(
        "tts_factory_standard",
        provider=settings.voice_tts_standard_provider,
        voice_male=settings.voice_tts_standard_voice_male,
        voice_female=settings.voice_tts_standard_voice_female,
    )

    # EdgeTTSClient has more specific method signatures than TTSClient protocol
    # but is runtime-compatible (accepts all protocol-required arguments)
    return EdgeTTSClient(  # type: ignore[return-value]
        rate=settings.voice_tts_standard_rate,
        pitch=settings.voice_tts_standard_pitch,
        volume=settings.voice_tts_standard_volume,
    )


async def _create_hd_client() -> TTSClient:
    """
    Create client for HD mode (OpenAI/Gemini TTS).

    Falls back to Standard mode if required API key is missing.
    """
    provider = settings.voice_tts_hd_provider

    logger.debug(
        "tts_factory_hd",
        provider=provider,
        model=settings.voice_tts_hd_model,
        voice_male=settings.voice_tts_hd_voice_male,
        voice_female=settings.voice_tts_hd_voice_female,
    )

    if provider == "openai":
        # Verify API key is configured in DB
        if not LLMConfigOverrideCache.get_api_key("openai"):
            logger.warning(
                "openai_tts_no_api_key",
                message="OpenAI API key not configured in DB, falling back to Standard mode",
            )
            return _create_standard_client()

        # OpenAITTSClient has more specific method signatures than TTSClient protocol
        # but is runtime-compatible (accepts all protocol-required arguments)
        return OpenAITTSClient(  # type: ignore[return-value]
            model=settings.voice_tts_hd_model,
            speed=settings.voice_tts_hd_speed,
            response_format=settings.voice_tts_hd_response_format,
        )

    elif provider == "gemini":
        # Verify API key is configured
        if not settings.google_api_key:
            logger.warning(
                "gemini_tts_no_api_key",
                message="GOOGLE_AI_API_KEY not configured, falling back to Standard mode",
            )
            return _create_standard_client()

        # Import Gemini client lazily (not implemented yet)
        # TODO: Implement GeminiTTSClient when needed
        logger.warning(
            "gemini_tts_not_implemented",
            message="Gemini TTS client not yet implemented, falling back to Standard mode",
        )
        return _create_standard_client()

    else:
        logger.error(
            "tts_factory_unknown_hd_provider",
            provider=provider,
            message=f"Unknown HD provider '{provider}', falling back to Standard mode",
        )
        return _create_standard_client()


def get_tts_client_sync(mode: VoiceTTSMode) -> TTSClient:
    """
    Get a TTS client synchronously (for non-async contexts).

    Use this only when you already know the mode and can't use async.
    Prefer get_tts_client() in async contexts.

    Args:
        mode: Voice mode ("standard" or "hd")

    Returns:
        TTSClient instance
    """
    if mode == "standard":
        return _create_standard_client()
    else:  # hd
        provider = settings.voice_tts_hd_provider

        if provider == "openai":
            if not LLMConfigOverrideCache.get_api_key("openai"):
                return _create_standard_client()
            # OpenAITTSClient has more specific method signatures than TTSClient protocol
            # but is runtime-compatible (accepts all protocol-required arguments)
            return OpenAITTSClient(  # type: ignore[return-value]
                model=settings.voice_tts_hd_model,
                speed=settings.voice_tts_hd_speed,
                response_format=settings.voice_tts_hd_response_format,
            )

        # Fallback for gemini or unknown
        return _create_standard_client()


def get_available_modes() -> list[dict]:
    """
    Get list of available voice modes with their status.

    Returns:
        List of mode info dictionaries for admin UI.
    """
    return [
        {
            "mode": "standard",
            "name": "Standard",
            "description": "Microsoft Edge TTS - Free, high quality neural voices",
            "provider": settings.voice_tts_standard_provider,
            "available": True,  # Always available (no API key required)
            "cost": "Free",
        },
        {
            "mode": "hd",
            "name": "HD",
            "description": "OpenAI/Gemini TTS - Premium quality, natural sounding voices",
            "provider": settings.voice_tts_hd_provider,
            "available": _is_hd_available(),
            "cost": "Paid",
        },
    ]


def _is_hd_available() -> bool:
    """Check if HD mode is available (API key configured)."""
    provider = settings.voice_tts_hd_provider

    if provider == "openai":
        return bool(LLMConfigOverrideCache.get_api_key("openai"))
    elif provider == "gemini":
        # Gemini TTS uses GOOGLE_API_KEY (generic), not the LLM Gemini key
        return bool(settings.google_api_key)

    return False
