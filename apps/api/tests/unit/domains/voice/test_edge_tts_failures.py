"""A failed synthesis is classified by the exception's TYPE, never by its message."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import aiohttp
import edge_tts
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from src.domains.voice.client import EdgeTTSClient
from src.domains.voice.exceptions import TTSProviderError

pytestmark = pytest.mark.unit


def failing_with(error: Exception) -> type:
    """An ``edge_tts.Communicate`` stand-in whose stream raises ``error``."""

    class _Failing:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        async def stream(self) -> AsyncIterator[dict[str, object]]:
            raise error
            yield {}  # pragma: no cover — makes this an async generator

    return _Failing


@pytest.mark.parametrize(
    ("error", "code"),
    [
        # The service answering without audio (1 synthesis in 24, measured).
        (
            edge_tts.exceptions.NoAudioReceived("No audio was received."),
            "provider_invalid_response",
        ),
        (TimeoutError(), "provider_timeout"),
        (aiohttp.ClientConnectionError(), "provider_network_error"),
        (ConnectionResetError(), "provider_network_error"),
        (edge_tts.exceptions.UnexpectedResponse("unexpected"), "provider_http_error"),
        # A message that merely MENTIONS a connection decides nothing.
        (RuntimeError("could not connect"), "provider_http_error"),
    ],
)
async def test_the_code_is_read_from_the_exception_type(error: Exception, code: str) -> None:
    with (
        patch("src.domains.voice.client.edge_tts.Communicate", failing_with(error)),
        pytest.raises(TTSProviderError) as caught,
    ):
        await EdgeTTSClient().synthesize(text="bonjour", voice_name="fr-FR-DeniseNeural")
    assert caught.value.code == code
    assert caught.value.transient  # every one of these may pass on a second attempt


@pytest.mark.parametrize(
    ("status", "transient"), [(0, True), (403, False), (429, True), (503, True)]
)
async def test_a_websocket_refusal_keeps_the_status_that_decides_retry(
    status: int, transient: bool
) -> None:
    error = aiohttp.WSServerHandshakeError(
        aiohttp.RequestInfo(
            URL("https://example.test/tts"), "GET", CIMultiDictProxy(CIMultiDict())
        ),
        (),
        status=status,
        message="handshake refused",
    )
    with (
        patch("src.domains.voice.client.edge_tts.Communicate", failing_with(error)),
        pytest.raises(TTSProviderError) as caught,
    ):
        await EdgeTTSClient().synthesize(text="bonjour", voice_name="fr-FR-DeniseNeural")

    assert isinstance(caught.value.details, dict)
    assert caught.value.details["status_code"] == (status or None)
    assert caught.value.transient is transient
