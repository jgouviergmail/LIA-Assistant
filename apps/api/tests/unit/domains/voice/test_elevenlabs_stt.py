"""Unit tests for the ElevenLabs Scribe Speech-To-Text adapter.

Uses ``httpx.MockTransport`` to isolate the service from the network
without monkey-patching the AsyncClient — the test verifies the exact
request shape (URL, headers, multipart fields) and the response handling
(success, 401/4xx/5xx, 429 + Retry-After, malformed body, timeout).
"""

from __future__ import annotations

import httpx
import pytest

from src.domains.voice.stt.elevenlabs_stt import ElevenLabsSttService
from src.domains.voice.stt.exceptions import STTProviderError

# A 200 ms PCM Int16 LE 16 kHz mono buffer (= 3200 samples × 2 bytes).
_DUMMY_PCM = b"\x00\x00" * 3200


def _build_service(
    transport: httpx.MockTransport,
    *,
    api_key: str = "sk-test",
    model: str = "scribe_v2",
    timeout_seconds: float = 30.0,
) -> ElevenLabsSttService:
    """Construct the service then patch its inner ``httpx.AsyncClient`` factory.

    The simplest portable mock is to monkey-patch the ``httpx.AsyncClient``
    constructor for the duration of the call. We do that by overriding the
    private ``_make_client`` if the service exposes it; otherwise we patch
    ``httpx.AsyncClient`` for the test.
    """
    return ElevenLabsSttService(api_key=api_key, model=model, timeout_seconds=timeout_seconds)


@pytest.fixture
def mock_async_client(monkeypatch):
    """Route ``httpx.AsyncClient`` (as used by the service) through a MockTransport.

    The service code does ``async with httpx.AsyncClient(timeout=...)``. We
    keep that exact code path; we only inject a ``transport=`` argument so
    every request hits ``state['handler']`` instead of the network. The
    real ``httpx.AsyncClient`` constructor is called underneath — no
    recursion. Each test sets ``state['handler']`` before invoking the
    service.
    """

    state: dict = {"handler": None, "calls": []}
    real_async_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        # Capture the request once it leaves the service so we can assert
        # on URL / headers / multipart fields without parsing the wire.
        original_handler = state["handler"]

        def _wrapping_handler(request: httpx.Request) -> httpx.Response:
            state["calls"].append(
                {
                    "url": str(request.url),
                    "headers": dict(request.headers),
                    "method": request.method,
                    # Keep the raw body for tests that need to inspect it.
                    "body": request.read(),
                }
            )
            assert original_handler is not None, "Test forgot to set state['handler']"
            return original_handler(request)

        kwargs.setdefault("transport", httpx.MockTransport(_wrapping_handler))
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("src.domains.voice.stt.elevenlabs_stt.httpx.AsyncClient", _factory)
    return state


# ----------------------------------------------------------------------
# Initialisation
# ----------------------------------------------------------------------


def test_constructor_rejects_empty_api_key():
    with pytest.raises(STTProviderError) as exc:
        ElevenLabsSttService(api_key="", model="scribe_v2")
    assert exc.value.code == "elevenlabs_api_key_missing"


# ----------------------------------------------------------------------
# Successful transcription
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_success(mock_async_client):
    """Happy path: 200 OK with text + audio_duration_secs returned."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "text": "Hello world",
                "audio_duration_secs": 1.5,
                "language_code": "en",
            },
        )

    mock_async_client["handler"] = handler

    service = _build_service(mock_async_client)
    result = await service.transcribe_pcm_int16_async(_DUMMY_PCM, sample_rate=16000, language="en")

    assert result.text == "Hello world"
    assert result.audio_duration_seconds == 1.5
    assert result.language_code == "en"
    # URL: POST {base_url}/speech-to-text
    assert captured["url"].endswith("/speech-to-text")
    # Auth header.
    assert captured["headers"]["xi-api-key"] == "sk-test"


@pytest.mark.asyncio
async def test_transcribe_omits_language_code_when_unsupported(mock_async_client):
    """Languages outside the LIA whitelist are dropped (auto-detect)."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "", "audio_duration_secs": 0.2})

    mock_async_client["handler"] = handler
    service = _build_service(mock_async_client)
    await service.transcribe_pcm_int16_async(_DUMMY_PCM, language="ja")

    body = mock_async_client["calls"][-1]["body"]
    # Only bytes-search to keep the test resilient to multipart boundary.
    assert b'name="language_code"' not in body
    assert b'name="model_id"' in body  # sanity: other fields still there


@pytest.mark.asyncio
async def test_transcribe_passes_language_when_supported(mock_async_client):
    """Whitelisted ISO-639-1 codes are forwarded as-is to ElevenLabs."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "", "audio_duration_secs": 0.2})

    mock_async_client["handler"] = handler
    service = _build_service(mock_async_client)
    await service.transcribe_pcm_int16_async(_DUMMY_PCM, language="fr")

    body = mock_async_client["calls"][-1]["body"]
    assert b'name="language_code"' in body
    # The value 'fr' lives on the line after the empty-line separator.
    assert b"\r\nfr\r\n" in body


@pytest.mark.asyncio
async def test_empty_buffer_skips_request(mock_async_client):
    """Zero-length audio short-circuits without an HTTP call."""
    mock_async_client["handler"] = lambda r: httpx.Response(500)
    service = _build_service(mock_async_client)
    result = await service.transcribe_pcm_int16_async(b"", sample_rate=16000)
    assert result.text == ""
    assert result.audio_duration_seconds == 0.0
    assert mock_async_client["calls"] == []


# ----------------------------------------------------------------------
# Sample-rate guard
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejects_non_16khz_sample_rate(mock_async_client):
    mock_async_client["handler"] = lambda r: httpx.Response(500)
    service = _build_service(mock_async_client)
    with pytest.raises(STTProviderError) as exc:
        await service.transcribe_pcm_int16_async(_DUMMY_PCM, sample_rate=44100)
    assert exc.value.code == "provider_invalid_response"


# ----------------------------------------------------------------------
# Error mapping
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_maps_to_provider_rate_limited(mock_async_client):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "12"}, json={"detail": "rate"})

    mock_async_client["handler"] = handler
    service = _build_service(mock_async_client)
    with pytest.raises(STTProviderError) as exc:
        await service.transcribe_pcm_int16_async(_DUMMY_PCM)
    assert exc.value.code == "provider_rate_limited"
    assert exc.value.retry_after_seconds == 12.0


@pytest.mark.asyncio
async def test_4xx_maps_to_provider_http_error(mock_async_client):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "missing_permissions"})

    mock_async_client["handler"] = handler
    service = _build_service(mock_async_client)
    with pytest.raises(STTProviderError) as exc:
        await service.transcribe_pcm_int16_async(_DUMMY_PCM)
    assert exc.value.code == "provider_http_error"
    assert "401" in exc.value.message


@pytest.mark.asyncio
async def test_5xx_maps_to_provider_http_error(mock_async_client):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    mock_async_client["handler"] = handler
    service = _build_service(mock_async_client)
    with pytest.raises(STTProviderError) as exc:
        await service.transcribe_pcm_int16_async(_DUMMY_PCM)
    assert exc.value.code == "provider_http_error"


@pytest.mark.asyncio
async def test_invalid_json_maps_to_provider_invalid_response(mock_async_client):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    mock_async_client["handler"] = handler
    service = _build_service(mock_async_client)
    with pytest.raises(STTProviderError) as exc:
        await service.transcribe_pcm_int16_async(_DUMMY_PCM)
    assert exc.value.code == "provider_invalid_response"


@pytest.mark.asyncio
async def test_missing_required_fields_maps_to_invalid_response(mock_async_client):
    """200 OK but body lacks ``text``/``audio_duration_secs`` → invalid."""

    def handler(_: httpx.Request) -> httpx.Response:
        # missing audio_duration_secs
        return httpx.Response(200, json={"text": "hello"})

    mock_async_client["handler"] = handler
    service = _build_service(mock_async_client)
    with pytest.raises(STTProviderError) as exc:
        await service.transcribe_pcm_int16_async(_DUMMY_PCM)
    assert exc.value.code == "provider_invalid_response"


@pytest.mark.asyncio
async def test_timeout_maps_to_provider_timeout(mock_async_client):
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("read timeout")

    mock_async_client["handler"] = handler
    service = _build_service(mock_async_client)
    with pytest.raises(STTProviderError) as exc:
        await service.transcribe_pcm_int16_async(_DUMMY_PCM)
    assert exc.value.code == "provider_timeout"


# ----------------------------------------------------------------------
# Multipart payload shape
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multipart_carries_pcm_format_marker(mock_async_client):
    """The `file_format=pcm_s16le_16` marker is present in the multipart body."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "", "audio_duration_secs": 0.0})

    mock_async_client["handler"] = handler
    service = _build_service(mock_async_client)
    await service.transcribe_pcm_int16_async(_DUMMY_PCM)

    body = mock_async_client["calls"][-1]["body"]
    # Field names + values are present in the wire body.
    assert b'name="file_format"' in body
    assert b"\r\npcm_s16le_16\r\n" in body
    assert b'name="model_id"' in body
    assert b"\r\nscribe_v2\r\n" in body
    assert b'name="timestamps_granularity"' in body
    assert b"\r\nnone\r\n" in body
    assert b'name="tag_audio_events"' in body
    assert b"\r\nfalse\r\n" in body
