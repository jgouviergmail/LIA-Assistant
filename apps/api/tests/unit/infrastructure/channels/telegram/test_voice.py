"""Tests for Telegram voice message handler."""

from __future__ import annotations

import sys
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock pydub before importing voice module (pydub requires ffmpeg)
_mock_pydub = MagicMock()
sys.modules.setdefault("pydub", _mock_pydub)

from src.infrastructure.channels.telegram.voice import (  # noqa: E402
    _MAX_VOICE_DURATION_SECONDS,
    _TARGET_SAMPLE_RATE,
    _download_voice_file,
    _ogg_to_pcm_float,
    transcribe_voice_message,
)

# Patch targets at source modules
_PATCH_STT = "src.domains.voice.stt.sherpa_stt.SherpaSttService"


# =============================================================================
# transcribe_voice_message
# =============================================================================


class TestTranscribeVoiceMessage:
    """Tests for the full voice transcription pipeline."""

    @pytest.mark.asyncio
    @patch(
        "src.infrastructure.channels.telegram.voice._ogg_to_pcm_float",
        return_value=[0.1, 0.2, 0.3],
    )
    @patch(
        "src.infrastructure.channels.telegram.voice._download_voice_file",
        return_value=b"fake_ogg_bytes",
    )
    @patch(_PATCH_STT)
    async def test_successful_transcription(
        self,
        mock_stt_cls: MagicMock,
        mock_download: AsyncMock,
        mock_ogg_to_pcm: MagicMock,
    ) -> None:
        """Happy path: download → transcode → transcribe → return text."""
        mock_stt = mock_stt_cls.return_value
        mock_stt.transcribe_async = AsyncMock(return_value="Hello world")

        bot = AsyncMock()
        result = await transcribe_voice_message(bot, "file_123", voice_duration_seconds=5)

        assert result == "Hello world"
        mock_download.assert_called_once_with(bot, "file_123")
        mock_stt.transcribe_async.assert_called_once_with(
            audio_samples=[0.1, 0.2, 0.3],
            sample_rate=_TARGET_SAMPLE_RATE,
        )

    @pytest.mark.asyncio
    async def test_rejects_too_long_voice(self) -> None:
        """Voice messages exceeding max duration should be rejected."""
        bot = AsyncMock()
        result = await transcribe_voice_message(
            bot, "file_123", voice_duration_seconds=_MAX_VOICE_DURATION_SECONDS + 1
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
        "src.infrastructure.channels.telegram.voice._ogg_to_pcm_float",
        return_value=[],
    )
    @patch(
        "src.infrastructure.channels.telegram.voice._download_voice_file",
        return_value=b"fake_bytes",
    )
    async def test_empty_samples_returns_none(
        self,
        mock_download: AsyncMock,
        mock_ogg_to_pcm: MagicMock,
    ) -> None:
        """Empty PCM samples should return None."""
        bot = AsyncMock()
        result = await transcribe_voice_message(bot, "file_123")
        assert result is None

    @pytest.mark.asyncio
    @patch(
        "src.infrastructure.channels.telegram.voice._ogg_to_pcm_float",
        return_value=[0.1, 0.2],
    )
    @patch(
        "src.infrastructure.channels.telegram.voice._download_voice_file",
        return_value=b"fake_bytes",
    )
    @patch(_PATCH_STT)
    async def test_empty_transcription_returns_none(
        self,
        mock_stt_cls: MagicMock,
        mock_download: AsyncMock,
        mock_ogg_to_pcm: MagicMock,
    ) -> None:
        """Empty transcription result should return None."""
        mock_stt = mock_stt_cls.return_value
        mock_stt.transcribe_async = AsyncMock(return_value="")

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


# =============================================================================
# _ogg_to_pcm_float
# =============================================================================


def _setup_mock_audio_segment(raw_data: bytes) -> MagicMock:
    """Configure a mock AudioSegment for testing _ogg_to_pcm_float."""
    mock_audio = MagicMock()
    mock_audio.set_frame_rate.return_value = mock_audio
    mock_audio.set_channels.return_value = mock_audio
    mock_audio.set_sample_width.return_value = mock_audio
    mock_audio.raw_data = raw_data
    _mock_pydub.AudioSegment.from_ogg.return_value = mock_audio
    return mock_audio


class TestOggToPcmFloat:
    """Tests for OGG to PCM float conversion."""

    def test_converts_to_16khz_mono(self) -> None:
        """Should set frame rate to 16kHz, channels to 1, sample width to 2."""
        # 2 samples: 0x0000 (0.0) and 0x4000 (0.5)
        mock_audio = _setup_mock_audio_segment(b"\x00\x00\x00\x40")

        result = _ogg_to_pcm_float(b"fake_ogg")

        mock_audio.set_frame_rate.assert_called_once_with(_TARGET_SAMPLE_RATE)
        mock_audio.set_channels.assert_called_once_with(1)
        mock_audio.set_sample_width.assert_called_once_with(2)
        assert len(result) == 2
        assert result[0] == pytest.approx(0.0, abs=0.001)
        assert result[1] == pytest.approx(0.5, abs=0.001)

    def test_normalizes_samples(self) -> None:
        """Samples should be normalized to [-1.0, 1.0] range."""
        # Max positive: 0x7FFF = 32767
        _setup_mock_audio_segment(b"\xff\x7f")

        result = _ogg_to_pcm_float(b"fake_ogg")

        assert len(result) == 1
        assert result[0] == pytest.approx(32767 / 32768.0, abs=0.001)

    def test_empty_audio(self) -> None:
        """Empty audio should return empty list."""
        _setup_mock_audio_segment(b"")

        result = _ogg_to_pcm_float(b"fake_ogg")
        assert result == []
