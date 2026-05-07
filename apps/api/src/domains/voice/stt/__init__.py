"""
Speech-to-Text Module.

Two backends:
- ``SherpaSttService`` — local Sherpa-onnx Whisper (free, on-server).
- ``ElevenLabsSttService`` — remote ElevenLabs Scribe (paid, audio-billed).

Both implement :class:`SttServiceProtocol` (single async method that takes a
raw PCM Int16 LE buffer and returns an :class:`STTResult`). The
:func:`get_stt_service_for_mode` factory selects the right backend based on
the per-user ``voice_stt_mode`` preference embedded in the WebSocket ticket.

Usage:
    from src.domains.voice.stt import get_stt_service_for_mode

    stt = get_stt_service_for_mode(ticket["voice_stt_mode"])
    result = await stt.transcribe_pcm_int16_async(buffer, language="fr")
"""

from src.domains.voice.stt.elevenlabs_stt import ElevenLabsSttService
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.factory import VoiceSttMode, get_stt_service_for_mode
from src.domains.voice.stt.protocol import STTResult, SttServiceProtocol
from src.domains.voice.stt.sherpa_stt import SherpaSttService, get_stt_service

__all__ = [
    "ElevenLabsSttService",
    "STTProviderError",
    "STTResult",
    "SherpaSttService",
    "SttServiceProtocol",
    "VoiceSttMode",
    "get_stt_service",
    "get_stt_service_for_mode",
]
