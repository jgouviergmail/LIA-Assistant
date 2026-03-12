"""
Speech-to-Text Module (Sherpa-onnx).

Provides offline, multi-language transcription using Sherpa-onnx.
Model: Whisper Small INT8 (99+ languages including FR/EN/DE/ES/IT/ZH)

Components:
- SherpaSttService: Core transcription service with async support
- get_stt_service(): Singleton accessor

Usage:
    from src.domains.voice.stt import get_stt_service

    stt = get_stt_service()
    text = await stt.transcribe_async(audio_samples)

Reference: plan zippy-drifting-valley.md (section 2.4.3)
Created: 2026-02-01
"""

from src.domains.voice.stt.sherpa_stt import SherpaSttService, get_stt_service

__all__ = [
    "SherpaSttService",
    "get_stt_service",
]
