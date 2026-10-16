"""An OpenAI synthesis failure is classified by the SDK's TYPE, and carries its facts alone.

The SDK's message is ``Error code: <status> - <body>``: the body may quote the
line refused (ADR-317), and reading it for words filed every message holding
« generate » as a rate limit. The real SDK runs here over a mock transport, so
each exception is built exactly as production builds it.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from openai import AsyncOpenAI
from structlog.testing import capture_logs

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.openai_tts_client import OpenAITTSClient

pytestmark = pytest.mark.unit

#: The line being voiced, echoed back by a refusal: it must never leave the client.
LINE = "the words of the person, quoted back"


@pytest.fixture(autouse=True)
def _configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, provider: "sk-test")
    )


async def _failed_with(answer: Callable[[httpx.Request], httpx.Response]) -> TTSProviderError:
    client = OpenAITTSClient()
    await client.close()
    client._client = AsyncOpenAI(
        api_key="sk-test",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    try:
        with pytest.raises(TTSProviderError) as caught:
            await client.synthesize(LINE, voice_name="nova")
    finally:
        await client.close()
    return caught.value


def _refusal(status: int, code: str | None, message: str = LINE) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"message": message, "type": "x", "param": "input", "code": code}}
    )


@pytest.mark.parametrize(
    ("status", "vendor_code", "code", "transient"),
    [
        (429, "rate_limit_exceeded", "provider_rate_limited", True),
        (401, "invalid_api_key", "provider_http_error", False),
        (403, "unsupported_country_region_territory", "provider_http_error", False),
        (400, None, "provider_http_error", False),
        (503, None, "provider_http_error", True),
    ],
)
async def test_a_refusal_is_classified_by_its_status(
    status: int, vendor_code: str | None, code: str, transient: bool
) -> None:
    error = await _failed_with(lambda _: _refusal(status, vendor_code))
    assert error.code == code and error.transient is transient
    assert error.details == {"status_code": status, "vendor_code": vendor_code}
    assert LINE not in str(error)


async def test_a_message_mentioning_generate_is_no_rate_limit() -> None:
    # « generate » holds « rate »: the substring rule filed this as a quota.
    error = await _failed_with(lambda _: _refusal(400, None, "could not generate the audio"))
    assert error.code == "provider_http_error" and not error.rate_limited


@pytest.mark.parametrize(
    ("raised", "code", "exception_type"),
    [
        (httpx.ConnectError("refused"), "provider_network_error", "APIConnectionError"),
        (httpx.ReadTimeout("slow"), "provider_timeout", "APITimeoutError"),
    ],
)
async def test_a_transport_failure_is_named_by_its_type(
    raised: Exception, code: str, exception_type: str
) -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        raise raised

    error = await _failed_with(fail)
    assert error.code == code and error.transient
    assert error.details == {"exception_type": exception_type}


async def test_the_log_line_carries_facts_never_the_vendor_text() -> None:
    with capture_logs() as logs:
        await _failed_with(lambda _: _refusal(400, "invalid_value"))
    [line] = [entry for entry in logs if entry["event"] == "openai_tts_error"]
    assert line["status_code"] == 400 and line["vendor_code"] == "invalid_value"
    assert "error" not in line and LINE not in repr(line)
