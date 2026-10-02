"""Tests for Telegram voice message handler.

The decode boundary is ``transcode`` (the ffmpeg runner, tested on its own in
``tests/unit/infrastructure/media/test_ffmpeg_runner.py``); the CI runners carry
no ffmpeg, so these tests stop at that boundary and pin what crosses it.
"""

from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structlog.testing import capture_logs

from src.core.config import settings
from src.domains.voice.stt.protocol import STTResult
from src.infrastructure.channels.telegram import voice as voice_module
from src.infrastructure.channels.telegram.voice import (
    _TARGET_SAMPLE_RATE,
    MAX_VOICE_DURATION_SECONDS,
    _download_voice_file,
    transcribe_voice_message,
    voice_duration_cap_seconds,
)
from src.infrastructure.media.ffmpeg import FfmpegError, FfmpegFailure
from tests.support.structlog_capture import fresh_module_logger

MODULE = "src.infrastructure.channels.telegram.voice"
_PATCH_STT = "src.domains.voice.stt.sherpa_stt.SherpaSttService"

# Two samples of 16 kHz mono int16 PCM, as ffmpeg writes them.
_PCM = b"\x00\x00\x00\x40"


@pytest.fixture(autouse=True)
def _fresh_logger() -> Iterator[None]:
    """Keep ``capture_logs`` reliable under xdist — see ``tests/support``."""
    yield from fresh_module_logger(voice_module)


def _problems(logs: list[dict[str, object]]) -> list[tuple[object, object, object]]:
    """What reached WARNING or above: event, level and failure kind."""
    return [
        (entry["event"], entry["log_level"], entry.get("kind"))
        for entry in logs
        if entry["log_level"] in ("warning", "error")
    ]


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
        refused = FfmpegError("ffmpeg failed", kind="failed")

        with (
            patch(f"{MODULE}._download_voice_file", AsyncMock(return_value=b"not audio")),
            patch(f"{MODULE}.transcode", AsyncMock(side_effect=refused)),
            patch(_PATCH_STT, return_value=stt),
            capture_logs() as logs,
        ):
            result = await transcribe_voice_message(AsyncMock(), "file_123")

        assert result is None
        stt.transcribe_pcm_int16_async.assert_not_awaited()
        # The sender's file: a fact at WARNING, never an incident of ours.
        assert _problems(logs) == [("telegram_voice_decode_failed", "warning", "failed")]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["timed_out", "not_installed"])
    async def test_an_instance_fault_is_logged_as_ours(self, kind: FfmpegFailure) -> None:
        """A missing ffmpeg or a decode past its ceiling is the INSTANCE's: logged
        as a bad file, it answered every note « I could not understand » with
        nothing above DEBUG saying why."""
        stt = _stt_answering("never")
        broken = FfmpegError("ffmpeg unavailable", kind=kind)

        with (
            patch(f"{MODULE}._download_voice_file", AsyncMock(return_value=b"ogg")),
            patch(f"{MODULE}.transcode", AsyncMock(side_effect=broken)),
            patch(_PATCH_STT, return_value=stt),
            capture_logs() as logs,
        ):
            result = await transcribe_voice_message(AsyncMock(), "file_123")

        assert result is None
        stt.transcribe_pcm_int16_async.assert_not_awaited()
        assert _problems(logs) == [("telegram_voice_decode_unavailable", "error", kind)]

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


class TestVoiceDurationCap:
    """One cap for the gate, the decode and the refusal's wording: Telegram's
    ceiling, or the STT's when it is lower. Measured before it existed: with the
    STT's default (60 s), a 90-second note passed the 120-second gate, the STT
    refused it, and the person read « I could not understand » instead of
    « too long »."""

    def test_the_cap_is_the_lower_of_telegram_s_and_the_stt_s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "voice_stt_max_duration_seconds", 60)
        assert voice_duration_cap_seconds() == 60
        monkeypatch.setattr(settings, "voice_stt_max_duration_seconds", 300)
        assert voice_duration_cap_seconds() == MAX_VOICE_DURATION_SECONDS

    @pytest.mark.asyncio
    async def test_a_note_declared_past_the_cap_is_never_downloaded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "voice_stt_max_duration_seconds", 60)
        download = AsyncMock(return_value=b"ogg")

        with patch(f"{MODULE}._download_voice_file", download):
            result = await transcribe_voice_message(
                AsyncMock(), "file_123", voice_duration_seconds=90
            )

        assert result is None
        download.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_decode_holds_the_cap_whatever_the_sender_declared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The declared duration is the sender's word — missing here. ffmpeg
        stops one second past the cap, so the PCM stays bounded and a longer
        note is still told from one of exactly the cap."""
        monkeypatch.setattr(settings, "voice_stt_max_duration_seconds", 60)
        stt = _stt_answering("never")
        past_the_cap = b"\x00\x00" * (60 * _TARGET_SAMPLE_RATE + 1)
        transcode = AsyncMock(return_value=past_the_cap)

        with (
            patch(f"{MODULE}._download_voice_file", AsyncMock(return_value=b"ogg")),
            patch(f"{MODULE}.transcode", transcode),
            patch(_PATCH_STT, return_value=stt),
        ):
            result = await transcribe_voice_message(AsyncMock(), "file_123")

        assert result is None
        stt.transcribe_pcm_int16_async.assert_not_awaited()
        args = transcode.await_args.kwargs["args"]
        assert args[args.index("-t") + 1] == "61"

    @pytest.mark.asyncio
    async def test_a_note_of_exactly_the_cap_is_transcribed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "voice_stt_max_duration_seconds", 60)
        stt = _stt_answering("a full minute")
        at_the_cap = b"\x00\x00" * (60 * _TARGET_SAMPLE_RATE)

        with (
            patch(f"{MODULE}._download_voice_file", AsyncMock(return_value=b"ogg")),
            patch(f"{MODULE}.transcode", AsyncMock(return_value=at_the_cap)),
            patch(_PATCH_STT, return_value=stt),
        ):
            result = await transcribe_voice_message(
                AsyncMock(), "file_123", voice_duration_seconds=60
            )

        assert result == "a full minute"


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
