"""synthesize_user_text (A2) — zero audio is a FAILURE, never a 200.

Root cause of the prod "silent error" (2026-08-20): stream_direct_tts
swallows per-sentence provider errors by design (chat best-effort), so a
dead provider yields an EMPTY stream without raising — and the endpoint
answered 200 with zero bytes. Absence of an exception is not proof of
delivery: an empty readout must raise, loudly, with the phrase count.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.voice.text_readout import synthesize_user_text


def _service_mock(chunks: list[bytes]):
    service = SimpleNamespace()

    async def _stream(**_kwargs):
        for payload in chunks:
            yield SimpleNamespace(audio_base64=base64.b64encode(payload).decode("ascii"))

    service.stream_direct_tts = _stream
    service.close = AsyncMock()
    return service


@pytest.mark.unit
class TestTextReadout:
    async def test_returns_concatenated_audio(self):
        service = _service_mock([b"a", b"b"])
        with (
            patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service),
            patch("src.domains.voice.text_readout.TrackingContext") as tracking,
        ):
            tracking.return_value.commit = AsyncMock()

            audio = await synthesize_user_text(user_id=uuid4(), user_language="fr", text="Bonjour.")

        assert audio == b"ab"
        service.close.assert_awaited_once()

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
