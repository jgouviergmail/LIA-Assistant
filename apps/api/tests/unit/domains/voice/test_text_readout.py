"""synthesize_user_text (A2) — zero audio is a FAILURE, never a 200; one MP3, never a heap.

Root cause of the prod "silent error" (2026-08-20): stream_direct_tts
swallows per-sentence provider errors by design (chat best-effort), so a
dead provider yields an EMPTY stream without raising — and the endpoint
answered 200 with zero bytes. Absence of an exception is not proof of
delivery: an empty readout must raise, loudly, with the phrase count.

And the readout answers ``audio/mpeg``: MP3 sentences join byte to byte, a WAV
per sentence (an engine configured for raw samples) does not — joined, a player
read the first sentence alone (ADR-345). Those are decoded and encoded once.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions_domains import UsageLimitExceededError
from src.core.field_names import FIELD_TTS_COST_EUR
from src.domains.voice.text_readout import synthesize_user_text


def _service_mock(chunks: list[bytes], mime_type: str = "audio/mpeg", paid: bool = True):
    service = SimpleNamespace()

    async def _stream(**_kwargs):
        for payload in chunks:
            yield SimpleNamespace(
                audio_base64=base64.b64encode(payload).decode("ascii"), mime_type=mime_type
            )

    service.stream_direct_tts = _stream
    service.speaks_on_a_paid_engine = AsyncMock(return_value=paid)
    service.count_speakable_sentences = lambda _text: len(chunks)
    service.close = AsyncMock()
    return service


@pytest.fixture(autouse=True)
def ceilings() -> Iterator[AsyncMock]:
    """Both ceilings, open."""
    with patch("src.domains.voice.text_readout.enforce_usage_limit", AsyncMock()) as asked:
        yield asked


@pytest.mark.unit
class TestTextReadout:
    async def test_returns_concatenated_audio(self):
        service = _service_mock([b"a", b"b"])
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext") as tracking,
        ):
            tracking.return_value.commit = AsyncMock()
            tracking.return_value.get_summary.return_value = {FIELD_TTS_COST_EUR: 0.002}

            readout = await synthesize_user_text(
                user_id=uuid4(), user_language="fr", text="Bonjour."
            )

        assert readout.audio == b"ab"
        assert readout.cost_eur == 0.002
        service.close.assert_awaited_once()

    async def test_fewer_sentences_said_than_the_text_holds_is_a_cut(self) -> None:
        service = _service_mock([b"a"])
        service.count_speakable_sentences = lambda _text: 3
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext") as tracking,
        ):
            tracking.return_value.commit = AsyncMock()
            tracking.return_value.get_summary.return_value = {FIELD_TTS_COST_EUR: 0.0}

            readout = await synthesize_user_text(
                user_id=uuid4(), user_language="fr", text="Un. Deux. Trois."
            )

        assert readout.cut is True

    async def test_what_was_said_is_billed_when_the_person_leaves_during_the_reading(self) -> None:
        service = _service_mock([])

        async def left_midway(**_kwargs: object) -> AsyncIterator[SimpleNamespace]:
            yield SimpleNamespace(
                audio_base64=base64.b64encode(b"a").decode("ascii"), mime_type="audio/mpeg"
            )
            raise asyncio.CancelledError

        service.stream_direct_tts = left_midway
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext") as tracking,
            pytest.raises(asyncio.CancelledError),
        ):
            tracking.return_value.commit = AsyncMock()

            await synthesize_user_text(user_id=uuid4(), user_language="fr", text="Bonjour.")

        tracking.return_value.commit.assert_awaited_once()
        service.close.assert_awaited_once()

    async def test_a_closed_ceiling_stops_a_paid_engine_before_it_speaks(
        self, ceilings: AsyncMock
    ) -> None:
        ceilings.side_effect = UsageLimitExceededError(user_id=uuid4(), reason="spent")
        service = _service_mock([b"a"])
        service.stream_direct_tts = MagicMock()
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext"),
            pytest.raises(UsageLimitExceededError),
        ):
            await synthesize_user_text(user_id=uuid4(), user_language="fr", text="Bonjour.")

        service.stream_direct_tts.assert_not_called()
        service.close.assert_awaited_once()

    async def test_a_free_engine_answers_to_no_ceiling(self, ceilings: AsyncMock) -> None:
        service = _service_mock([b"a"], paid=False)
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext") as tracking,
        ):
            tracking.return_value.commit = AsyncMock()
            tracking.return_value.get_summary.return_value = {FIELD_TTS_COST_EUR: 0.0}

            readout = await synthesize_user_text(
                user_id=uuid4(), user_language="fr", text="Bonjour."
            )

        ceilings.assert_not_awaited()
        assert readout.cost_eur == 0.0

    async def test_empty_stream_raises_instead_of_returning_silence(self):
        service = _service_mock([])
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext") as tracking,
        ):
            tracking.return_value.commit = AsyncMock()

            with pytest.raises(RuntimeError, match="no audio"):
                await synthesize_user_text(user_id=uuid4(), user_language="fr", text="Bonjour.")

        # The provider client is still closed — failure never leaks it.
        service.close.assert_awaited_once()
        # And a silent run is never committed as a paid success.
        tracking.return_value.commit.assert_not_awaited()

    async def test_mp3_sentences_are_joined_without_a_transcode(self):
        service = _service_mock([b"ID3a", b"ID3b"])
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext") as tracking,
            patch("src.domains.voice.text_readout.transcode", AsyncMock()) as transcode,
        ):
            tracking.return_value.commit = AsyncMock()
            tracking.return_value.get_summary.return_value = {FIELD_TTS_COST_EUR: 0.0}
            readout = await synthesize_user_text(
                user_id=uuid4(), user_language="fr", text="Un. Deux."
            )

        assert readout.audio == b"ID3aID3b"
        transcode.assert_not_awaited()

    async def test_wav_sentences_become_one_mp3(self):
        """Each sentence is decoded to one rate, the samples joined, ONE MP3 encoded."""
        decoded = {b"RIFF-one": b"\x01\x00", b"RIFF-two": b"\x02\x00"}

        async def fake_transcode(audio, *, output_format, args, timeout_s):
            if output_format == "s16le":
                return decoded[audio]
            assert output_format == "mp3"
            assert audio.startswith(b"RIFF") and audio.endswith(b"\x01\x00\x02\x00")
            return b"ID3-one-file"

        service = _service_mock([b"RIFF-one", b"RIFF-two"], mime_type="audio/wav")
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext") as tracking,
            patch("src.domains.voice.text_readout.transcode", side_effect=fake_transcode),
        ):
            tracking.return_value.commit = AsyncMock()
            tracking.return_value.get_summary.return_value = {FIELD_TTS_COST_EUR: 0.0}
            readout = await synthesize_user_text(
                user_id=uuid4(), user_language="fr", text="Un. Deux."
            )

        assert readout.audio == b"ID3-one-file"
        tracking.return_value.commit.assert_awaited_once()

    async def test_a_failed_encoding_is_a_failure_and_still_closes_the_service(self):
        from src.infrastructure.media.ffmpeg import FfmpegError

        service = _service_mock([b"RIFF-one"], mime_type="audio/wav")
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext") as tracking,
            patch(
                "src.domains.voice.text_readout.transcode",
                AsyncMock(side_effect=FfmpegError("codec refused", kind="failed")),
            ),
        ):
            tracking.return_value.commit = AsyncMock()
            with pytest.raises(FfmpegError):
                await synthesize_user_text(user_id=uuid4(), user_language="fr", text="Un.")

        service.close.assert_awaited_once()
        # The sentences were synthesised, and paid for, before the encoding failed.
        tracking.return_value.commit.assert_awaited_once()
