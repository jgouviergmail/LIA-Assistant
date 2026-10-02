"""Tests for Telegram voice message handler.

The decode boundary is ``transcode`` (the ffmpeg runner, tested on its own in
``tests/unit/infrastructure/media/test_ffmpeg_runner.py``); the CI runners carry
no ffmpeg, so these tests stop at that boundary and pin what crosses it.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.voice.stt.protocol import STTResult
from src.infrastructure.channels.telegram.voice import (
    _TARGET_SAMPLE_RATE,
    MAX_VOICE_DURATION_SECONDS,
    _download_voice_file,
    transcribe_voice_message,
)
from src.infrastructure.media.ffmpeg import FfmpegError

MODULE = "src.infrastructure.channels.telegram.voice"
_PATCH_STT = "src.domains.voice.stt.sherpa_stt.SherpaSttService"

# Two samples of 16 kHz mono int16 PCM, as ffmpeg writes them.
_PCM = b"\x00\x00\x00\x40"


def _stt_answering(text: str) -> MagicMock:
    stt = MagicMock()
    stt.transcribe_pcm_int16_async = AsyncMock(
        return_value=STTResult(text=text, audio_duration_seconds=0.1, language_code=None)
    )
    return stt


# =============================================================================
# transcribe_voice_message
# =============================================================================


class TestTranscribeVoiceMessage:
    """Download → ffmpeg decode → STT, and every way out of it."""

    @pytest.mark.asyncio
    async def test_successful_transcription(self) -> None:
        stt = _stt_answering("Hello world")

        with (
            patch(f"{MODULE}._download_voice_file", AsyncMock(return_value=b"ogg")),
            patch(f"{MODULE}.transcode", AsyncMock(return_value=_PCM)),
            patch(_PATCH_STT, return_value=stt),
        ):
            result = await transcribe_voice_message(
                AsyncMock(), "file_123", voice_duration_seconds=5
            )

        assert result == "Hello world"
        stt.transcribe_pcm_int16_async.assert_awaited_once_with(
            _PCM, sample_rate=_TARGET_SAMPLE_RATE
        )

    @pytest.mark.asyncio
    async def test_ffmpeg_is_asked_for_the_format_the_stt_is_told(self) -> None:
        """Mono int16 at the very rate the STT reads: a mismatch would transcribe noise."""
        stt = _stt_answering("ok")
        transcode = AsyncMock(return_value=_PCM)

        with (
            patch(f"{MODULE}._download_voice_file", AsyncMock(return_value=b"ogg")),
            patch(f"{MODULE}.transcode", transcode),
            patch(_PATCH_STT, return_value=stt),
        ):
            await transcribe_voice_message(AsyncMock(), "file_123")

        decode = transcode.await_args
        assert decode.args == (b"ogg",)
        assert decode.kwargs["output_format"] == "s16le"
        args = decode.kwargs["args"]
        assert args[args.index("-ac") + 1] == "1"
        told = stt.transcribe_pcm_int16_async.await_args.kwargs["sample_rate"]
        assert args[args.index("-ar") + 1] == str(told)

    @pytest.mark.asyncio
    async def test_a_file_ffmpeg_cannot_read_is_dropped_without_the_stt(self) -> None:
        stt = _stt_answering("never")

        with (
            patch(f"{MODULE}._download_voice_file", AsyncMock(return_value=b"not audio")),
            patch(f"{MODULE}.transcode", AsyncMock(side_effect=FfmpegError("ffmpeg failed"))),
            patch(_PATCH_STT, return_value=stt),
        ):
            result = await transcribe_voice_message(AsyncMock(), "file_123")

        assert result is None
        stt.transcribe_pcm_int16_async.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_pcm_returns_none_without_the_stt(self) -> None:
        stt = _stt_answering("never")

        with (
            patch(f"{MODULE}._download_voice_file", AsyncMock(return_value=b"ogg")),
            patch(f"{MODULE}.transcode", AsyncMock(return_value=b"")),
            patch(_PATCH_STT, return_value=stt),
        ):
            result = await transcribe_voice_message(AsyncMock(), "file_123")

        assert result is None
        stt.transcribe_pcm_int16_async.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_transcription_returns_none(self) -> None:
        with (
            patch(f"{MODULE}._download_voice_file", AsyncMock(return_value=b"ogg")),
            patch(f"{MODULE}.transcode", AsyncMock(return_value=_PCM)),
            patch(_PATCH_STT, return_value=_stt_answering("")),
        ):
            result = await transcribe_voice_message(AsyncMock(), "file_123")

        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_too_long_voice(self) -> None:
        """Voice messages exceeding max duration should be rejected."""
        bot = AsyncMock()
        result = await transcribe_voice_message(
            bot, "file_123", voice_duration_seconds=MAX_VOICE_DURATION_SECONDS + 1
        )
        assert result is None

    @pytest.mark.asyncio
    @patch(
        "src.infrastructure.channels.telegram.voice._download_voice_file",
        return_value=None,
    )
    async def test_download_failure_returns_none(
        self,
        mock_download: AsyncMock,
    ) -> None:
        """Download failure should return None."""
        bot = AsyncMock()
        result = await transcribe_voice_message(bot, "file_123")
        assert result is None

    @pytest.mark.asyncio
    @patch(
        "src.infrastructure.channels.telegram.voice._download_voice_file",
        side_effect=RuntimeError("Network error"),
    )
    async def test_exception_returns_none(
        self,
        mock_download: AsyncMock,
    ) -> None:
        """Exceptions should be caught and return None."""
        bot = AsyncMock()
        result = await transcribe_voice_message(bot, "file_123")
        assert result is None

    @pytest.mark.asyncio
    async def test_none_duration_not_rejected(self) -> None:
        """None duration should not trigger rejection."""
        with (
            patch(
                "src.infrastructure.channels.telegram.voice._download_voice_file",
                return_value=None,
            ),
        ):
            bot = AsyncMock()
            result = await transcribe_voice_message(bot, "file_123", voice_duration_seconds=None)
            assert result is None  # Returns None from download failure, not duration check


# =============================================================================
# _download_voice_file — file size limit (DoS protection)
# =============================================================================


class TestDownloadVoiceFileSize:
    """Tests for voice file size limit in _download_voice_file."""

    @pytest.mark.asyncio
    async def test_rejects_file_exceeding_size_limit(self) -> None:
        """Files exceeding TELEGRAM_MAX_VOICE_FILE_SIZE should be rejected."""
        mock_bot = AsyncMock()
        mock_tg_file = MagicMock()
        mock_tg_file.file_size = 25 * 1024 * 1024  # 25 MB (over 20 MB limit)
        mock_bot.get_file = AsyncMock(return_value=mock_tg_file)

        result = await _download_voice_file(mock_bot, "file_oversized")

        assert result is None
        mock_tg_file.download_to_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_file_within_size_limit(self) -> None:
        """Files within the size limit should be downloaded successfully."""
        mock_bot = AsyncMock()
        mock_tg_file = AsyncMock()
        mock_tg_file.file_size = 500 * 1024  # 500 KB — well under limit
        ogg_content = b"fake_ogg_content"

        async def mock_download(buf: BytesIO) -> None:
            buf.write(ogg_content)

        mock_tg_file.download_to_memory = mock_download
        mock_bot.get_file = AsyncMock(return_value=mock_tg_file)

        result = await _download_voice_file(mock_bot, "file_ok")

        assert result == ogg_content

    @pytest.mark.asyncio
    async def test_none_file_size_allows_download(self) -> None:
        """When Telegram doesn't provide file_size, download should proceed."""
        mock_bot = AsyncMock()
        mock_tg_file = AsyncMock()
        mock_tg_file.file_size = None
        ogg_content = b"small_ogg"

        async def mock_download(buf: BytesIO) -> None:
            buf.write(ogg_content)

        mock_tg_file.download_to_memory = mock_download
        mock_bot.get_file = AsyncMock(return_value=mock_tg_file)

        result = await _download_voice_file(mock_bot, "file_no_size")

        assert result == ogg_content
