"""
Voice message handler for Telegram.

Downloads OGG/Opus voice messages from Telegram, decodes them to 16 kHz mono
PCM through ffmpeg (a bounded subprocess: the event loop never decodes), and
transcribes them via SherpaSttService.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from src.core.config import settings
from src.core.constants import TELEGRAM_MAX_VOICE_FILE_SIZE, TELEGRAM_VOICE_DECODE_TIMEOUT_SECONDS
from src.infrastructure.media.ffmpeg import FfmpegError, transcode
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from telegram import Bot

logger = get_logger(__name__)

# Target sample rate for Sherpa STT
_TARGET_SAMPLE_RATE = 16000
# int16 mono: two bytes a sample.
_PCM_BYTES_PER_SECOND = 2 * _TARGET_SAMPLE_RATE

# Telegram's own ceiling for a voice note (seconds). The STT's may be lower:
# read the cap through `voice_duration_cap_seconds`, never this constant.
MAX_VOICE_DURATION_SECONDS = 120


def voice_duration_cap_seconds() -> int:
    """The longest voice note a transcription accepts — one cap for the gate,
    the decode and the refusal's wording.

    Telegram's own ceiling, or the STT's (``voice_stt_max_duration_seconds``)
    when it is lower. Measured before this function: with the STT's default
    (60 s), a 90-second note passed the 120-second gate, the STT refused it, and
    the person was told « I could not understand » instead of « too long ».

    Returns:
        The cap, in seconds.
    """
    return min(MAX_VOICE_DURATION_SECONDS, settings.voice_stt_max_duration_seconds)


async def transcribe_voice_message(
    bot: Bot,
    voice_file_id: str,
    voice_duration_seconds: int | None = None,
) -> str | None:
    """
    Download a Telegram voice message and transcribe it to text.

    Pipeline: Telegram file API → OGG bytes → ffmpeg (16 kHz mono int16 PCM)
    → SherpaSttService.transcribe_pcm_int16_async()

    Args:
        bot: Telegram Bot instance (for file download).
        voice_file_id: Telegram file_id of the voice message.
        voice_duration_seconds: Duration in seconds (from Telegram metadata).
            The sender's word: it refuses a note early, and the decode holds
            the cap whatever it says.

    Returns:
        Transcribed text, or None if transcription failed or was empty.
    """
    cap = voice_duration_cap_seconds()
    if voice_duration_seconds and voice_duration_seconds > cap:
        logger.warning(
            "telegram_voice_too_long",
            duration=voice_duration_seconds,
            max_duration=cap,
        )
        return None

    try:
        # 1. Download OGG bytes from Telegram
        ogg_bytes = await _download_voice_file(bot, voice_file_id)
        if not ogg_bytes:
            return None

        # 2. Decode OGG/Opus → 16 kHz mono PCM (ffmpeg, bounded)
        try:
            pcm = await _decode_to_pcm(ogg_bytes, max_seconds=cap)
        except FfmpegError as exc:
            if exc.kind == "failed":
                # A file ffmpeg cannot read is the sender's, not a defect of ours.
                logger.warning(
                    "telegram_voice_decode_failed", file_id=voice_file_id[:12], kind=exc.kind
                )
            else:
                # ffmpeg missing or past its ceiling is the instance's.
                logger.error(
                    "telegram_voice_decode_unavailable", file_id=voice_file_id[:12], kind=exc.kind
                )
            logger.debug("telegram_voice_decode_detail", file_id=voice_file_id[:12], error=str(exc))
            return None

        if not pcm:
            logger.warning("telegram_voice_empty_samples", file_id=voice_file_id[:12])
            return None

        decoded_seconds = len(pcm) / _PCM_BYTES_PER_SECOND
        if decoded_seconds > cap:
            logger.warning(
                "telegram_voice_too_long",
                duration=round(decoded_seconds, 1),
                declared=voice_duration_seconds,
                max_duration=cap,
            )
            return None

        # 3. Transcribe via Sherpa STT
        from src.domains.voice.stt.sherpa_stt import SherpaSttService

        stt = SherpaSttService(settings)
        result = await stt.transcribe_pcm_int16_async(pcm, sample_rate=_TARGET_SAMPLE_RATE)
        text = result.text

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


async def _decode_to_pcm(ogg_bytes: bytes, *, max_seconds: int) -> bytes:
    """
    Decode a voice note to the PCM the STT reads: 16 kHz, mono, int16 LE.

    ffmpeg runs as a subprocess under a ceiling, so a wedged codec cannot hold
    the worker and nothing decodes on the event loop. It stops one second past
    ``max_seconds``: the output stays bounded whatever duration the note
    declares, and a note longer than the cap is still told from one of exactly
    the cap.

    Args:
        ogg_bytes: The voice note as Telegram serves it (OGG/Opus).
        max_seconds: The longest note a transcription accepts.

    Returns:
        Raw PCM samples, two bytes each.

    Raises:
        FfmpegError: When ffmpeg cannot decode the file, is missing, or runs
            past its ceiling.
    """
    return await transcode(
        ogg_bytes,
        output_format="s16le",
        args=["-ac", "1", "-ar", str(_TARGET_SAMPLE_RATE), "-t", str(max_seconds + 1)],
        timeout_s=TELEGRAM_VOICE_DECODE_TIMEOUT_SECONDS,
    )


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
