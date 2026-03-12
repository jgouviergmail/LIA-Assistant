"""
Sherpa-onnx Speech-to-Text Service.

Provides offline, multi-language transcription using Whisper Small INT8 model.
Follows codebase patterns: singleton, structured logging, metrics.

Key Features:
- 100% offline (no API costs)
- Multi-language: 99+ languages including FR/EN/DE/ES/IT/ZH
- Async-safe via ThreadPoolExecutor (CPU-bound work)
- Thread-safe for concurrent transcriptions

Model: csukuangfj/sherpa-onnx-whisper-small (~375 MB INT8)
Languages: French, English, German, Spanish, Italian, Chinese, and 90+ more

Usage:
    stt = get_stt_service()
    text = await stt.transcribe_async(audio_samples)

Reference: plan zippy-drifting-valley.md (section 2.4.3)
Created: 2026-02-01
Updated: 2026-02-01 - Migrated from SenseVoice to Whisper for French support
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.config import get_settings
from src.core.constants import STT_EXECUTOR_MAX_WORKERS, STT_EXECUTOR_THREAD_PREFIX
from src.core.exceptions import (
    STTError,
    raise_stt_audio_too_long,
    raise_stt_error,
    raise_stt_model_not_found,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_voice import (
    stt_audio_duration_seconds,
    stt_errors_total,
    stt_transcription_duration_seconds,
    stt_transcriptions_total,
)

if TYPE_CHECKING:
    from src.core.config import Settings

logger = get_logger(__name__)

# Thread pool for CPU-bound STT transcription
# Prevents blocking the async event loop during decode
_stt_executor = ThreadPoolExecutor(
    max_workers=STT_EXECUTOR_MAX_WORKERS,
    thread_name_prefix=STT_EXECUTOR_THREAD_PREFIX,
)


class SherpaSttService:
    """
    Speech-to-Text service using Sherpa-onnx OfflineRecognizer.

    Model: Whisper Small INT8 (multi-language: 99+ languages)
    Supports: French, English, German, Spanish, Italian, Chinese, and more.

    Thread-safe via ThreadPoolExecutor for async operations.
    Each instance holds its own recognizer for isolation.

    Attributes:
        _recognizer: Sherpa-onnx OfflineRecognizer instance
        _sample_rate: Expected audio sample rate (16000 Hz)

    Example:
        stt = get_stt_service()
        text = await stt.transcribe_async(audio_float_samples)
    """

    def __init__(self, settings: "Settings") -> None:
        """
        Initialize STT service with Sherpa-onnx Whisper model.

        Args:
            settings: Application settings with model configuration

        Raises:
            STTModelNotFoundError: If model files not found
        """
        # Lazy import to avoid import errors when sherpa_onnx not installed
        try:
            import sherpa_onnx
        except ImportError as e:
            logger.error(
                "sherpa_onnx_import_failed",
                error=str(e),
                hint="Install sherpa-onnx: pip install sherpa-onnx",
            )
            raise_stt_error(
                detail="Sherpa-onnx not installed",
                operation="init",
            )

        model_path = Path(settings.voice_stt_model_path)

        # Validate model directory exists
        if not model_path.exists():
            logger.error(
                "stt_model_not_found",
                model_path=str(model_path),
            )
            raise_stt_model_not_found(str(model_path))

        # Validate required Whisper model files
        encoder_file = model_path / "encoder.onnx"
        decoder_file = model_path / "decoder.onnx"
        tokens_file = model_path / "tokens.txt"

        if not encoder_file.exists():
            raise_stt_model_not_found(str(encoder_file))
        if not decoder_file.exists():
            raise_stt_model_not_found(str(decoder_file))
        if not tokens_file.exists():
            raise_stt_model_not_found(str(tokens_file))

        # Initialize recognizer with Whisper model
        # Whisper supports 99+ languages including French
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=str(encoder_file),
            decoder=str(decoder_file),
            tokens=str(tokens_file),
            num_threads=settings.voice_stt_num_threads,
            language=settings.voice_stt_language,
            task=settings.voice_stt_task,
        )

        self._sample_rate = 16000  # Sherpa-onnx requires 16kHz
        self._max_duration = settings.voice_stt_max_duration_seconds

        logger.info(
            "stt_service_initialized",
            model="whisper-small",
            model_path=str(model_path),
            num_threads=settings.voice_stt_num_threads,
            language=settings.voice_stt_language or "auto-detect",
            task=settings.voice_stt_task,
            max_duration_seconds=self._max_duration,
        )

    def transcribe(self, audio_samples: list[float], sample_rate: int = 16000) -> str:
        """
        Transcribe audio samples to text (SYNCHRONOUS).

        WARNING: This method blocks the thread during transcription.
        Use transcribe_async() in async contexts.

        Args:
            audio_samples: PCM float samples normalized [-1.0, 1.0]
            sample_rate: Audio sample rate (must be 16000)

        Returns:
            Transcribed text (may be empty if no speech detected)

        Raises:
            STTError: On transcription failure
        """
        if sample_rate != self._sample_rate:
            logger.warning(
                "stt_sample_rate_mismatch",
                expected=self._sample_rate,
                received=sample_rate,
            )

        # Check duration limit
        duration_seconds = len(audio_samples) / sample_rate
        if duration_seconds > self._max_duration:
            stt_errors_total.labels(error_type="audio_too_long").inc()
            raise_stt_audio_too_long(
                duration_seconds=duration_seconds,
                max_seconds=self._max_duration,
            )

        try:
            # Create stream and feed audio
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, audio_samples)

            # Decode
            self._recognizer.decode_stream(stream)

            # Get result
            text: str = stream.result.text.strip()

            return text

        except Exception as e:
            stt_errors_total.labels(error_type="decode_error").inc()
            logger.error(
                "stt_transcription_failed",
                error=str(e),
                error_type=type(e).__name__,
                audio_samples_count=len(audio_samples),
            )
            raise_stt_error(
                detail=f"Transcription failed: {e}",
                operation="transcribe",
            )

    async def transcribe_async(
        self,
        audio_samples: list[float],
        sample_rate: int = 16000,
    ) -> str:
        """
        Transcribe audio samples to text (ASYNC, non-blocking).

        Uses ThreadPoolExecutor to run CPU-bound transcription
        without blocking the async event loop.

        Args:
            audio_samples: PCM float samples normalized [-1.0, 1.0]
            sample_rate: Audio sample rate (must be 16000)

        Returns:
            Transcribed text (may be empty if no speech detected)

        Raises:
            STTError: On transcription failure
        """
        # Calculate audio duration for metrics
        audio_duration = len(audio_samples) / sample_rate
        stt_audio_duration_seconds.observe(audio_duration)

        try:
            with stt_transcription_duration_seconds.time():
                loop = asyncio.get_event_loop()
                text = await loop.run_in_executor(
                    _stt_executor,
                    self.transcribe,
                    audio_samples,
                    sample_rate,
                )

            stt_transcriptions_total.labels(status="success").inc()

            logger.debug(
                "stt_transcription_completed",
                audio_duration_seconds=round(audio_duration, 2),
                text_length=len(text),
                has_content=bool(text),
            )

            return text

        except Exception as e:
            stt_transcriptions_total.labels(status="error").inc()
            logger.error(
                "stt_async_transcription_failed",
                audio_duration_seconds=round(audio_duration, 2),
                error=str(e),
                error_type=type(e).__name__,
            )
            # Re-raise if already an STTError (or subclass), otherwise wrap
            if isinstance(e, STTError):
                raise
            raise_stt_error(
                detail=f"Async transcription failed: {e}",
                operation="transcribe_async",
            )

    @property
    def sample_rate(self) -> int:
        """Get required sample rate for audio input."""
        return self._sample_rate

    @property
    def max_duration_seconds(self) -> int:
        """Get maximum allowed audio duration."""
        return self._max_duration


@lru_cache
def get_stt_service() -> SherpaSttService:
    """
    Get singleton SherpaSttService instance.

    Lazily initializes the service on first call.
    Subsequent calls return the same instance.

    Returns:
        SherpaSttService singleton

    Raises:
        STTModelNotFoundError: If model not found
        STTError: If initialization fails
    """
    settings = get_settings()

    # Check if STT is enabled
    if not settings.voice_stt_enabled:
        logger.warning("stt_service_disabled")
        raise_stt_error(
            detail="STT service is disabled",
            operation="get_service",
        )

    return SherpaSttService(settings)


def clear_stt_service_cache() -> None:
    """
    Clear the STT service singleton cache.

    Useful for testing or when model needs to be reloaded.
    """
    get_stt_service.cache_clear()
    logger.info("stt_service_cache_cleared")
