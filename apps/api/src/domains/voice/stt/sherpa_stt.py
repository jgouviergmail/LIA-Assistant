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
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from src.core.config import get_settings
from src.core.constants import STT_EXECUTOR_MAX_WORKERS, STT_EXECUTOR_THREAD_PREFIX
from src.core.exceptions import (
    STTError,
    raise_stt_audio_too_long,
    raise_stt_error,
    raise_stt_model_not_found,
)
from src.domains.voice.stt.long_audio import (
    SileroSegmenter,
    plan_windows,
    transcribe_in_windows,
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
    from src.domains.voice.stt.protocol import STTResult

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
    Maintains a cache of recognizers keyed by language code so that each
    user's preferred language is used as a Whisper language hint, improving
    transcription accuracy.

    Attributes:
        _recognizers: Dict of language → OfflineRecognizer instances
        _sample_rate: Expected audio sample rate (16000 Hz)

    Example:
        stt = get_stt_service()
        text = await stt.transcribe_async(audio_float_samples, language="fr")
    """

    def __init__(self, settings: Settings) -> None:
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

            self._sherpa_onnx = sherpa_onnx
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
        self._encoder_file = model_path / "encoder.onnx"
        self._decoder_file = model_path / "decoder.onnx"
        self._tokens_file = model_path / "tokens.txt"

        if not self._encoder_file.exists():
            raise_stt_model_not_found(str(self._encoder_file))
        if not self._decoder_file.exists():
            raise_stt_model_not_found(str(self._decoder_file))
        if not self._tokens_file.exists():
            raise_stt_model_not_found(str(self._tokens_file))

        # Store settings for recognizer creation
        self._num_threads = settings.voice_stt_num_threads
        self._default_language = settings.voice_stt_language
        self._task = settings.voice_stt_task

        # Cache of recognizers keyed by language code (thread-safe)
        # Each language gets its own recognizer with the appropriate language hint.
        # Whisper uses the language parameter to bias transcription output.
        # Type is Any because sherpa_onnx is imported dynamically at runtime
        # and has no official Python type stubs (see github.com/k2-fsa/sherpa-onnx).
        self._recognizers: dict[str, Any] = {}
        self._recognizers_lock = threading.Lock()

        # Pre-initialize the default language recognizer
        self._get_recognizer(self._default_language)

        self._sample_rate = 16000  # Sherpa-onnx requires 16kHz
        self._max_duration = settings.voice_stt_max_duration_seconds

        # Long audio: the engine decodes only the first 30 s of a buffer
        # (measured 2026-09-02), so anything above the single-pass cap is cut
        # into VAD-aligned windows — see ``long_audio.py``.
        self._single_pass_max_seconds = settings.voice_stt_single_pass_max_seconds
        self._window_seconds = settings.voice_stt_window_seconds
        self._segmenter = SileroSegmenter(
            settings.voice_stt_vad_model_path,
            threshold=settings.voice_stt_vad_threshold,
            min_silence_seconds=settings.voice_stt_vad_min_silence_seconds,
            min_speech_seconds=settings.voice_stt_vad_min_speech_seconds,
            max_speech_seconds=float(self._window_seconds),
            sample_rate=self._sample_rate,
        )

        logger.info(
            "stt_service_initialized",
            model="whisper-small",
            model_path=str(model_path),
            num_threads=self._num_threads,
            default_language=self._default_language or "auto-detect",
            task=self._task,
            max_duration_seconds=self._max_duration,
            single_pass_max_seconds=self._single_pass_max_seconds,
            window_seconds=self._window_seconds,
            vad_available=self._segmenter.is_available(),
        )

    def _get_recognizer(self, language: str) -> Any:
        """
        Get or create an OfflineRecognizer for the given language.

        Recognizers are cached by language code. Thread-safe via lock.

        Args:
            language: ISO 639-1 language code (e.g. 'fr', 'en', 'de').
                      Empty string means auto-detect.

        Returns:
            Sherpa-onnx OfflineRecognizer instance for the requested language
        """
        with self._recognizers_lock:
            if language in self._recognizers:
                return self._recognizers[language]

            recognizer = self._sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(self._encoder_file),
                decoder=str(self._decoder_file),
                tokens=str(self._tokens_file),
                num_threads=self._num_threads,
                language=language,
                task=self._task,
            )
            self._recognizers[language] = recognizer

            logger.info(
                "stt_recognizer_created",
                language=language or "auto-detect",
                total_recognizers=len(self._recognizers),
            )

            return recognizer

    def transcribe(
        self,
        audio_samples: list[float],
        sample_rate: int = 16000,
        language: str = "",
    ) -> str:
        """
        Transcribe audio samples to text (SYNCHRONOUS).

        WARNING: This method blocks the thread during transcription.
        Use transcribe_async() in async contexts.

        Args:
            audio_samples: PCM float samples normalized [-1.0, 1.0]
            sample_rate: Audio sample rate (must be 16000)
            language: ISO 639-1 language code for transcription hint.
                      Empty string means auto-detect (default).

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

        # Use language-specific or default recognizer
        effective_language = language or self._default_language
        recognizer = self._get_recognizer(effective_language)

        try:
            if duration_seconds > self._single_pass_max_seconds:
                return self._transcribe_long(
                    recognizer, audio_samples, sample_rate, duration_seconds
                )
            return self._decode(recognizer, audio_samples, sample_rate)

        except Exception as e:
            stt_errors_total.labels(error_type="decode_error").inc()
            logger.error(
                "stt_transcription_failed",
                error=str(e),
                error_type=type(e).__name__,
                audio_samples_count=len(audio_samples),
                language=effective_language or "auto-detect",
            )
            raise_stt_error(
                detail=f"Transcription failed: {e}",
                operation="transcribe",
            )

    @staticmethod
    def _decode(recognizer: Any, audio_samples: list[float], sample_rate: int) -> str:
        """One engine pass — the engine keeps at most 30 s of what it is given.

        Args:
            recognizer: Sherpa-onnx OfflineRecognizer.
            audio_samples: PCM float samples normalized [-1.0, 1.0].
            sample_rate: Audio sample rate.

        Returns:
            Stripped transcription of this pass (may be empty).
        """
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, audio_samples)
        recognizer.decode_stream(stream)
        text: str = stream.result.text.strip()
        return text

    def _transcribe_long(
        self,
        recognizer: Any,
        audio_samples: list[float],
        sample_rate: int,
        duration_seconds: float,
    ) -> str:
        """Cut a buffer longer than one engine pass into windows and decode each.

        Windows end on VAD silences when the Silero model is available and fall
        back to fixed slices otherwise — degraded at the cuts, never truncated.
        The fallback is counted so an image shipped without the VAD model is
        visible on the voice dashboard rather than discovered in a transcript.

        Args:
            recognizer: Sherpa-onnx OfflineRecognizer.
            audio_samples: PCM float samples normalized [-1.0, 1.0].
            sample_rate: Audio sample rate.
            duration_seconds: Buffer duration (for the log only).

        Returns:
            The joined transcription of every window.
        """
        samples = np.asarray(audio_samples, dtype=np.float32)
        windows, strategy = plan_windows(
            samples,
            sample_rate=sample_rate,
            max_window_seconds=float(self._window_seconds),
            segmenter=self._segmenter,
        )
        if strategy == "fixed_no_vad":
            stt_errors_total.labels(error_type="vad_unavailable").inc()
        logger.info(
            "stt_long_audio_windowed",
            duration_seconds=round(duration_seconds, 1),
            windows=len(windows),
            strategy=strategy,
        )
        return transcribe_in_windows(
            samples,
            windows,
            lambda clip: self._decode(recognizer, clip, sample_rate),
        )

    async def transcribe_async(
        self,
        audio_samples: list[float],
        sample_rate: int = 16000,
        language: str = "",
    ) -> str:
        """
        Transcribe audio samples to text (ASYNC, non-blocking).

        Uses ThreadPoolExecutor to run CPU-bound transcription
        without blocking the async event loop.

        Args:
            audio_samples: PCM float samples normalized [-1.0, 1.0]
            sample_rate: Audio sample rate (must be 16000)
            language: ISO 639-1 language code for transcription hint.
                      Empty string means auto-detect (default).

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
                loop = asyncio.get_running_loop()
                text = await loop.run_in_executor(
                    _stt_executor,
                    self.transcribe,
                    audio_samples,
                    sample_rate,
                    language,
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

    async def transcribe_unbounded_pcm_async(
        self,
        pcm_int16_bytes: bytes,
        *,
        language: str | None,
        on_window: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> str:
        """Transcribe a recording of ANY length, one window at a time (meetings, ADR-258).

        The WebSocket cap (``voice_stt_max_duration_seconds``) protects a live
        dictation; a meeting is a background job, so this path skips the cap and
        instead yields to the event loop between windows and reports progress —
        a lease heartbeat rides on ``on_window``. Windows follow the same
        VAD-aligned policy as the live path.

        Args:
            pcm_int16_bytes: Raw 16 kHz int16 mono PCM.
            language: ISO-639-1 hint, ``None`` = the configured default.
            on_window: Awaited after each decoded window with ``(index, total)``.

        Returns:
            The joined transcription.
        """
        if not pcm_int16_bytes:
            return ""
        samples = np.frombuffer(pcm_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        windows, strategy = plan_windows(
            samples,
            sample_rate=self._sample_rate,
            max_window_seconds=float(self._window_seconds),
            segmenter=self._segmenter,
        )
        if strategy == "fixed_no_vad":
            stt_errors_total.labels(error_type="vad_unavailable").inc()
        logger.info(
            "stt_unbounded_windowed",
            duration_seconds=round(len(samples) / self._sample_rate, 1),
            windows=len(windows),
            strategy=strategy,
        )
        recognizer = self._get_recognizer(language or self._default_language)
        loop = asyncio.get_running_loop()
        texts: list[str] = []
        for index, (start, end) in enumerate(windows):
            clip = samples[start:end].tolist()
            text = await loop.run_in_executor(
                _stt_executor, self._decode, recognizer, clip, self._sample_rate
            )
            if text:
                texts.append(text)
            if on_window is not None:
                await on_window(index + 1, len(windows))
        return " ".join(texts)

    async def transcribe_pcm_int16_async(
        self,
        pcm_int16_bytes: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> STTResult:
        """Conform to ``SttServiceProtocol``.

        Converts the raw PCM Int16 LE buffer (the format streamed by the
        WebSocket frontend) into a normalised float32 list expected by
        Sherpa-onnx, then reuses :meth:`transcribe_async`. The audio
        duration is computed from the buffer length (deterministic for raw
        PCM).
        """
        # Local imports to keep the module-level surface narrow.
        import numpy as np

        from src.domains.voice.stt.protocol import STTResult

        if not pcm_int16_bytes:
            return STTResult(text="", audio_duration_seconds=0.0, language_code=language)

        audio_np = np.frombuffer(pcm_int16_bytes, dtype=np.int16)
        audio_float = (audio_np.astype(np.float32) / 32768.0).tolist()
        duration_seconds = len(audio_np) / float(sample_rate) if sample_rate else 0.0

        text = await self.transcribe_async(
            audio_float,
            sample_rate=sample_rate,
            language=language or "",
        )
        return STTResult(
            text=text,
            audio_duration_seconds=duration_seconds,
            language_code=language or None,
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
