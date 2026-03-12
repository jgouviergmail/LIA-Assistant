"""
Voice domain for Text-to-Speech (TTS) functionality.

This domain provides:
- TTSClient: Protocol for TTS providers
- EdgeTTSClient: Microsoft Edge neural voices (free, high quality)
- OpenAITTSClient: OpenAI TTS API (paid, natural voices)
- TTSConfig: Configuration for current voice mode (Standard/HD)
- get_tts_client: Factory function for getting TTS client based on mode
- get_tts_config: Get TTS configuration for current voice mode
- VoiceCommentService: Service for generating and streaming voice comments
- Schemas: Pydantic models for voice requests/responses

Voice Mode (Admin-controlled):
- Standard: Edge TTS (free, high quality neural voices)
- HD: OpenAI/Gemini TTS (paid, premium quality)

Audio is streamed to the frontend as base64-encoded audio chunks.

Updated: 2025-12-29 - Migrated from Google Cloud TTS to Edge TTS
Updated: 2026-01-15 - Multi-provider TTS support (Edge, OpenAI)
Updated: 2026-01-16 - Standard/HD mode architecture (admin-controlled)
"""

from .client import EdgeTTSClient
from .factory import TTSConfig, get_tts_client, get_tts_config
from .openai_tts_client import OpenAITTSClient
from .protocol import TTSClient
from .schemas import VoiceAudioChunk, VoiceCommentRequest
from .service import VoiceCommentService

__all__ = [
    # Protocol
    "TTSClient",
    # Clients
    "EdgeTTSClient",
    "OpenAITTSClient",
    # Factory
    "TTSConfig",
    "get_tts_client",
    "get_tts_config",
    # Service
    "VoiceCommentService",
    # Schemas
    "VoiceCommentRequest",
    "VoiceAudioChunk",
]
