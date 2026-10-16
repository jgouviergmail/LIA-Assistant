"""An ElevenLabs refusal leaves the speech client as its facts, never its words (ADR-317).

The vendor validates a request the way FastAPI does: a 422 echoes the field it
refused, the line being voiced included. Measured shapes: ``detail.status``
(the legacy name) and ``detail.code`` (the documented one).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest
from structlog.testing import capture_logs

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice import elevenlabs_tts_client
from src.domains.voice.elevenlabs_tts_client import ElevenLabsTTSClient
from src.domains.voice.exceptions import TTSProviderError

pytestmark = pytest.mark.unit

#: The line being voiced, echoed back by the refusal: it must never leave the client.
LINE = "the words of the person, quoted back"


@asynccontextmanager
async def _free_slot(*_: object, **__: object) -> AsyncIterator[None]:
    yield


async def _refused_by(
    monkeypatch: pytest.MonkeyPatch, answer: Callable[[httpx.Request], httpx.Response]
) -> TTSProviderError:
    monkeypatch.setattr(
        LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, provider: "key")
    )
    # The account's allowance is proven elsewhere (test_provider_capacity.py).
    monkeypatch.setattr(elevenlabs_tts_client, "provider_slot", _free_slot)
    client = ElevenLabsTTSClient(timeout_seconds=5)
    await client.close()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    try:
        with pytest.raises(TTSProviderError) as caught:
            await client.synthesize(LINE, "voice")
    finally:
        await client.close()
    return caught.value


async def test_a_validation_refusal_echoing_the_line_never_carries_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {"detail": [{"loc": ["body", "text"], "msg": "too long", "input": LINE}]}
    with capture_logs() as logs:
        error = await _refused_by(monkeypatch, lambda _: httpx.Response(422, json=body))
    assert error.code == "provider_http_error" and not error.transient
    assert error.details == {"status_code": 422, "vendor_code": None}
    assert LINE not in str(error)
    [line] = [entry for entry in logs if entry["event"] == "elevenlabs_tts_http_error"]
    assert line["status_code"] == 422 and LINE not in repr(line)


async def test_a_refusal_names_the_vendor_code(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"detail": {"code": "invalid_api_key", "status": "invalid_api_key", "message": LINE}}
    error = await _refused_by(monkeypatch, lambda _: httpx.Response(401, json=body))
    assert error.code == "provider_http_error" and not error.transient
    assert error.details == {"status_code": 401, "vendor_code": "invalid_api_key"}
    assert LINE not in str(error)


async def test_a_quota_refusal_states_its_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"detail": {"status": "too_many_concurrent_requests", "message": LINE}}
    error = await _refused_by(
        monkeypatch, lambda _: httpx.Response(429, headers={"Retry-After": "4"}, json=body)
    )
    assert error.code == "provider_rate_limited" and error.rate_limited
    assert error.retry_after_seconds == 4.0
    assert error.details == {"status_code": 429, "vendor_code": "too_many_concurrent_requests"}
    assert LINE not in str(error)


async def test_a_server_failure_stays_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    error = await _refused_by(monkeypatch, lambda _: httpx.Response(503, text=LINE))
    assert error.code == "provider_http_error" and error.transient
    assert error.details == {"status_code": 503, "vendor_code": None}
    assert LINE not in str(error)
