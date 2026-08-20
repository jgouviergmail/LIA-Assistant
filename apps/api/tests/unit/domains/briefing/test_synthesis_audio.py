"""POST /briefing/synthesis/audio — listen to the displayed synthesis (A2).

The frontend sends the text it already rendered; the endpoint streams the
TTS audio back. Bounded (settings-driven max chars), sanitized, and
cost-tracked like every paid voice path. No LLM: reading is free of
generation, the text is the one the user is looking at.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.session_dependencies import get_current_active_session
from src.domains.briefing.router import router

USER_ID = uuid.uuid4()


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(
        id=USER_ID, language="fr"
    )
    return TestClient(app)


def _voice_service_mock() -> MagicMock:
    service = MagicMock()

    async def _stream(**_kwargs):
        # Two chunks of fake MP3 bytes, base64-encoded like the real client.
        import base64

        for payload in (b"chunk-one", b"chunk-two"):
            yield SimpleNamespace(audio_base64=base64.b64encode(payload).decode("ascii"))

    service.stream_direct_tts = _stream
    service.close = AsyncMock()
    return service


@pytest.mark.unit
class TestSynthesisAudio:
    def test_streams_decoded_audio_bytes(self, client: TestClient):
        service = _voice_service_mock()
        with patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service):
            resp = client.post(
                "/briefing/synthesis/audio",
                json={"text": "Bonjour, voici votre journée."},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/mpeg")
        assert resp.content == b"chunk-onechunk-two"
        service.close.assert_awaited_once()

    def test_empty_text_is_rejected(self, client: TestClient):
        assert client.post("/briefing/synthesis/audio", json={"text": "   "}).status_code == 422

    def test_oversized_text_is_rejected(self, client: TestClient):
        too_long = "x" * (settings.briefing_audio_max_chars + 1)

        resp = client.post("/briefing/synthesis/audio", json={"text": too_long})

        assert resp.status_code == 422

    def test_service_is_closed_even_when_the_stream_fails(self, client: TestClient):
        service = MagicMock()

        async def _boom(**_kwargs):
            raise RuntimeError("tts down")
            yield  # pragma: no cover - generator shape

        service.stream_direct_tts = _boom
        service.close = AsyncMock()
        with patch("src.domains.voice.text_readout.VoiceCommentService", return_value=service):
            resp = client.post("/briefing/synthesis/audio", json={"text": "Bonjour."})

        assert resp.status_code >= 500
        service.close.assert_awaited_once()
