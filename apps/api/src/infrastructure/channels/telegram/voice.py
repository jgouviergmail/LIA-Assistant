"""
Voice message handler for Telegram.

Downloads OGG/Opus voice messages from Telegram, transcodes to
PCM float 16kHz mono via pydub+ffmpeg, and transcribes via SherpaSttService.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import TYPE_CHECKING

from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from telegram import Bot

logger = get_logger(__name__)

# Target sample rate for Sherpa STT
_TARGET_SAMPLE_RATE = 16000

# Maximum voice duration we'll process (seconds)
_MAX_VOICE_DURATION_SECONDS = 120


async def transcribe_voice_message(
    bot: Bot,
    voice_file_id: str,
    voice_duration_seconds: int | None = None,
) -> str | None:
    """
    Download a Telegram voice message and transcribe it to text.

    Pipeline: Telegram file API → OGG bytes → pydub AudioSegment
    → resample 16kHz mono → float PCM → SherpaSttService.transcribe_async()

    Args:
        bot: Telegram Bot instance (for file download).
        voice_file_id: Telegram file_id of the voice message.
        voice_duration_seconds: Duration in seconds (from Telegram metadata).
            Used for early rejection of overly long messages.

    Returns:
        Transcribed text, or None if transcription failed or was empty.
    """
    # Reject overly long voice messages
    if voice_duration_seconds and voice_duration_seconds > _MAX_VOICE_DURATION_SECONDS:
        logger.warning(
            "telegram_voice_too_long",
            duration=voice_duration_seconds,
            max_duration=_MAX_VOICE_DURATION_SECONDS,
        )
        return None

    try:
        # 1. Download OGG bytes from Telegram
        ogg_bytes = await _download_voice_file(bot, voice_file_id)
        if not ogg_bytes:
            return None

        # 2. Transcode OGG → PCM float samples (CPU-bound, run in executor)
        loop = asyncio.get_running_loop()
        samples = await loop.run_in_executor(
            None,
            _ogg_to_pcm_float,
            ogg_bytes,
        )

        if not samples:
            logger.warning("telegram_voice_empty_samples", file_id=voice_file_id[:12])
            return None

        # 3. Transcribe via Sherpa STT
        from src.core.config import settings
        from src.domains.voice.stt.sherpa_stt import SherpaSttService

        stt = SherpaSttService(settings)
        text = await stt.transcribe_async(
            audio_samples=samples,
            sample_rate=_TARGET_SAMPLE_RATE,
        )

        logger.info(
            "telegram_voice_transcribed",
            file_id=voice_file_id[:12],
            text_length=len(text) if text else 0,
            has_content=bool(text),
        )

        return text if text else None

    except Exception:
        logger.error(
            "telegram_voice_transcription_failed",
            file_id=voice_file_id[:12],
            exc_info=True,
        )
        return None


async def _download_voice_file(bot: Bot, file_id: str) -> bytes | None:
    """
    Download a voice file from Telegram.

    Includes file size validation to prevent DoS via memory exhaustion.

    Args:
        bot: Telegram Bot instance.
        file_id: Telegram file_id.

    Returns:
        Raw OGG bytes, or None on failure.
    """
    from src.core.constants import TELEGRAM_MAX_VOICE_FILE_SIZE

    try:
        tg_file = await bot.get_file(file_id)

        # Check file size from Telegram metadata before downloading
        if tg_file.file_size and tg_file.file_size > TELEGRAM_MAX_VOICE_FILE_SIZE:
            logger.warning(
                "telegram_voice_file_too_large",
                file_id=file_id[:12],
                file_size=tg_file.file_size,
                max_size=TELEGRAM_MAX_VOICE_FILE_SIZE,
            )
            return None

        buffer = BytesIO()
        await tg_file.download_to_memory(buffer)
        ogg_bytes = buffer.getvalue()

        # Double-check actual size after download
        if len(ogg_bytes) > TELEGRAM_MAX_VOICE_FILE_SIZE:
            logger.warning(
                "telegram_voice_download_exceeded_limit",
                file_id=file_id[:12],
                actual_size=len(ogg_bytes),
                max_size=TELEGRAM_MAX_VOICE_FILE_SIZE,
            )
            return None

        logger.debug(
            "telegram_voice_downloaded",
            file_id=file_id[:12],
            size_bytes=len(ogg_bytes),
        )
        return ogg_bytes

    except Exception:
        logger.error(
            "telegram_voice_download_failed",
            file_id=file_id[:12],
            exc_info=True,
        )
        return None


def _ogg_to_pcm_float(ogg_bytes: bytes) -> list[float]:
    """
    Convert OGG/Opus audio to PCM float samples at 16kHz mono.

    This is a CPU-bound operation — should be called via run_in_executor.

    Args:
        ogg_bytes: Raw OGG audio bytes.

    Returns:
        List of float samples normalized to [-1.0, 1.0].
    """
    from pydub import AudioSegment

    # Load OGG from bytes
    audio = AudioSegment.from_ogg(BytesIO(ogg_bytes))

    # Resample to 16kHz mono, 16-bit
    audio = audio.set_frame_rate(_TARGET_SAMPLE_RATE).set_channels(1).set_sample_width(2)

    # Convert to float samples [-1.0, 1.0]
    raw_data = audio.raw_data
    samples: list[float] = []
    for i in range(0, len(raw_data), 2):
        sample_int = int.from_bytes(raw_data[i : i + 2], byteorder="little", signed=True)
        samples.append(sample_int / 32768.0)

    return samples
