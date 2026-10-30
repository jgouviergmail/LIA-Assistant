"""A model call is sent again only when the provider never ran it (spec 2026-10-21 E2, Q3 (a)).

Measured before the change (spec §0ter E2, local-server simulation of 2026-10-28): the
clients LIA builds sent THREE requests after a read timeout on the OpenAI wire and on
Anthropic, and Gemini six after a 500 or a 429 (34 s). A generation whose outcome is
unknown — a timeout, or a connection lost once the request may have left — may already
have run and been billed; sending it again buys it twice.

Where each SDK decides to send again (installed versions; Step 0 of the plan):

- **openai 2.x** (OpenAI, DeepSeek, Perplexity, Qwen): ``AsyncAPIClient.request`` catches
  ``httpx.TimeoutException`` in a branch of its own, apart from ``_should_retry`` (the
  status rule), and any other exception in a third. The seam is ``_send_request``: a
  failure after the send leaves it as an ``OpenAIError``, which the loop re-raises.
- **anthropic 0.122**: every attempt's exception goes through ``_should_retry_exception``,
  which walks the ``__cause__`` chain; the override keeps a transport failure retryable
  only when the request never reached the server.
- **google-genai 2.x** (Gemini): ``HttpRetryOptions.attempts`` counts the ORIGINAL
  request; LangChain writes ``max_retries`` into it. The relaunch budget is translated.
- **Ollama**: no retry loop of its own; nothing to change.

The oracle is the number of requests a real local server RECEIVED.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, get_args
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from src.core.config import settings
from src.infrastructure.llm.providers import adapter as adapter_module
from src.infrastructure.llm.providers.adapter import ProviderAdapter, ProviderType
from src.infrastructure.llm.providers.retry_policy import never_reached_the_server

pytestmark = [
    pytest.mark.unit,
    # google-genai's own 5xx path over aiohttp leaves `ClientResponse.json()` un-awaited
    # (google/genai/_api_client.py) — the vendor's coroutine, not LIA's; the Gemini status
    # test must still run, so only that exact warning is filtered.
    pytest.mark.filterwarnings(
        "ignore:coroutine 'ClientResponse.json' was never awaited:RuntimeWarning"
    ),
]

#: The read timeout every client is built with; the « slow » server answers after it.
TIMEOUT_S = 0.5


class _Server:
    """A provider that answers late, fails, refuses or cuts its stream — and counts."""

    def __init__(self) -> None:
        self.mode = "slow"
        self.hits: list[str] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802 - the http.server contract
                length = int(self.headers.get("content-length") or 0)
                self.rfile.read(length)
                server.hits.append(self.path)
                if server.mode == "slow":
                    time.sleep(TIMEOUT_S * 4)
                    return
                if server.mode == "disconnect":
                    # The request was read, then the line drops: it may be running.
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.close_connection = True
                    return
                if server.mode == "stream_cut":
                    self.send_response(200)
                    self.send_header("content-type", "text/event-stream")
                    self.end_headers()
                    self.wfile.write(b'data: {"partial": tr')
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                code = 500 if server.mode == "500" else 429
                body = b'{"error":{"message":"simulated","type":"server_error","code":500}}'
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("retry-after", "0")
                self.send_header("retry-after-ms", "0")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._http.server_address[1]
        threading.Thread(target=self._http.serve_forever, daemon=True).start()

    def count(self, mode: str) -> int:
        self.mode = mode
        return len(self.hits)

    def close(self) -> None:
        self._http.shutdown()
        self._http.server_close()


@pytest.fixture(scope="module")
def server() -> Iterator[_Server]:
    running = _Server()
    yield running
    running.close()


def _refused_port() -> int:
    """A loopback port nothing listens on: a connection there never reaches a server."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


#: One model per family; the OpenAI wire is built for each provider that rides it.
FAMILIES: dict[str, str] = {
    "openai": "gpt-4.1-mini",
    "deepseek": "deepseek-chat",
    "perplexity": "sonar",
    "qwen": "qwen-plus",
    "anthropic": "claude-haiku-4-5",
    "gemini": "gemini-2.5-flash",
    "ollama": "qwen3:4b",
}


def _build(provider: str, port: int, *, streaming: bool = False) -> Any:
    url = f"http://127.0.0.1:{port}"
    kwargs: dict[str, Any] = {}
    if provider == "gemini":
        kwargs["base_url"] = url
    with (
        patch.object(
            adapter_module,
            "_require_api_key",
            lambda p: url if p == "ollama" else "sk-test",
        ),
        patch.object(adapter_module, "_get_base_url", lambda _p: f"{url}/v1"),
    ):
        llm = ProviderAdapter.create_llm(
            provider=provider,
            model=FAMILIES[provider],
            temperature=0.2,
            max_tokens=8,
            streaming=streaming,
            llm_type="response",
            timeout_seconds=TIMEOUT_S,
            **kwargs,
        )
    for name in ("root_client", "root_async_client"):
        client = getattr(llm, name, None)
        if client is not None:
            client.base_url = f"{url}/v1"
    if provider == "anthropic":
        llm._client.base_url = url
        llm._async_client.base_url = url
    if provider == "ollama":
        llm.base_url = url
    return llm


async def _call(llm: Any) -> str | None:
    try:
        await asyncio.wait_for(llm.ainvoke([HumanMessage(content="x")]), timeout=60)
    except Exception as error:  # noqa: BLE001 - the error class is part of the oracle
        return type(error).__name__
    return None


def test_every_provider_is_a_family_of_this_test() -> None:
    assert set(get_args(ProviderType)) == set(FAMILIES)


@pytest.mark.parametrize("provider", sorted(FAMILIES))
async def test_a_timeout_sends_one_request(server: _Server, provider: str) -> None:
    before = server.count("slow")
    error = await _call(_build(provider, server.port))

    assert len(server.hits) - before == 1
    assert error is not None


@pytest.mark.parametrize("provider", sorted(FAMILIES))
async def test_a_connection_lost_after_the_send_sends_one_request(
    server: _Server, provider: str
) -> None:
    # google-genai's aiohttp branch sent it again, once, whatever its retry options said.
    before = server.count("disconnect")
    error = await _call(_build(provider, server.port))

    assert len(server.hits) - before == 1
    assert error is not None


@pytest.mark.parametrize("provider", sorted(FAMILIES))
def test_a_synchronous_timeout_sends_one_request(server: _Server, provider: str) -> None:
    # google-genai's synchronous predicate retried an httpx timeout: three requests.
    before = server.count("slow")
    llm = _build(provider, server.port)
    with pytest.raises(Exception):  # noqa: B017 - the count is the oracle, not the class
        llm.invoke([HumanMessage(content="x")])

    assert len(server.hits) - before == 1


@pytest.mark.parametrize("status", ["500", "429"])
@pytest.mark.parametrize("provider", sorted(set(FAMILIES) - {"ollama"}))
async def test_a_transient_status_sends_at_most_the_budget(
    server: _Server, provider: str, status: str
) -> None:
    before = server.count(status)
    error = await _call(_build(provider, server.port))

    assert len(server.hits) - before == 1 + settings.llm_transient_retry_max
    assert error is not None


async def test_ollama_never_sends_twice(server: _Server) -> None:
    before = server.count("500")
    await _call(_build("ollama", server.port))
    assert len(server.hits) - before == 1


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
async def test_a_refused_connection_is_sent_again_within_the_budget(provider: str) -> None:
    import httpx

    attempts: list[str] = []
    original = httpx.AsyncHTTPTransport.handle_async_request

    async def counted(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        return await original(self, request)

    with patch.object(httpx.AsyncHTTPTransport, "handle_async_request", counted):
        error = await _call(_build(provider, _refused_port()))

    assert len(attempts) == 1 + settings.llm_transient_retry_max
    assert error is not None


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
async def test_a_stream_cut_after_its_first_bytes_sends_one_request(
    server: _Server, provider: str
) -> None:
    before = server.count("stream_cut")
    llm = _build(provider, server.port, streaming=True)
    try:
        async for _chunk in llm.astream([HumanMessage(content="x")]):
            pass
    except (
        Exception
    ):  # noqa: BLE001, S110 - the cut may surface as an error; the count is the oracle
        pass

    assert len(server.hits) - before == 1


async def test_a_client_built_outside_the_factory_follows_the_policy(server: _Server) -> None:
    """An image or a spoken answer is a billed generation too: one request on a timeout."""
    import openai

    from src.infrastructure.llm.providers.retry_policy import adopt_relaunch_policy

    client = adopt_relaunch_policy(
        openai.AsyncOpenAI(
            api_key="sk-test", base_url=f"http://127.0.0.1:{server.port}/v1", timeout=TIMEOUT_S
        )
    )
    before = server.count("slow")
    try:
        with pytest.raises(openai.APITimeoutError):
            await client.images.generate(model="gpt-image-1", prompt="x")
    finally:
        await client.close()

    assert len(server.hits) - before == 1


def test_only_a_failure_before_the_send_reaches_no_server() -> None:
    import httpx

    request = httpx.Request("POST", "http://127.0.0.1/x")
    assert never_reached_the_server(httpx.ConnectError("refused", request=request))
    assert never_reached_the_server(httpx.ConnectTimeout("slow dns", request=request))
    assert never_reached_the_server(httpx.PoolTimeout("pool", request=request))
    assert not never_reached_the_server(httpx.ReadTimeout("late", request=request))
    assert not never_reached_the_server(httpx.RemoteProtocolError("cut", request=request))
    wrapped = RuntimeError("sdk")
    wrapped.__cause__ = httpx.ConnectError("refused", request=request)
    assert never_reached_the_server(wrapped)


def test_a_synchronous_refused_connection_is_sent_again_within_the_budget() -> None:
    import httpx

    attempts: list[str] = []
    original = httpx.HTTPTransport.handle_request

    def counted(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        return original(self, request)

    llm = _build("openai", _refused_port())
    with patch.object(httpx.HTTPTransport, "handle_request", counted):
        with pytest.raises(Exception):  # noqa: B017 - the count is the oracle
            llm.invoke([HumanMessage(content="x")])

    assert len(attempts) == 1 + settings.llm_transient_retry_max


@pytest.mark.parametrize("asynchronous", [True, False])
def test_gemini_sends_a_refused_connection_again_within_the_budget(asynchronous: bool) -> None:
    """The transport re-raises a failure that never left as it is, for the SDK's predicate."""
    import httpx

    attempts: list[str] = []
    sync_original = httpx.HTTPTransport.handle_request
    async_original = httpx.AsyncHTTPTransport.handle_async_request

    def counted(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        return sync_original(self, request)

    async def async_counted(
        self: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        attempts.append(str(request.url))
        return await async_original(self, request)

    llm = _build("gemini", _refused_port())
    with (
        patch.object(httpx.HTTPTransport, "handle_request", counted),
        patch.object(httpx.AsyncHTTPTransport, "handle_async_request", async_counted),
    ):
        if asynchronous:
            assert asyncio.run(_call(llm)) is not None
        else:
            with pytest.raises(Exception):  # noqa: B017 - the count is the oracle
                llm.invoke([HumanMessage(content="x")])

    assert len(attempts) == 1 + settings.llm_transient_retry_max


def test_adopting_a_client_twice_keeps_its_policy() -> None:
    import openai

    from src.infrastructure.llm.providers.retry_policy import adopt_relaunch_policy

    client = adopt_relaunch_policy(openai.OpenAI(api_key="sk-test"))
    adopted = type(client)

    assert type(adopt_relaunch_policy(client)) is adopted
    assert adopted is not openai.OpenAI
    client.close()


def test_a_client_class_no_adoption_declares_is_left_and_said() -> None:
    import openai
    import structlog

    from src.infrastructure.llm.providers.retry_policy import adopt_relaunch_policy

    class Wrapped(openai.OpenAI):
        """A release that wraps its client: not a class the policy declares."""

    client = Wrapped(api_key="sk-test")
    with structlog.testing.capture_logs() as logs:
        adopt_relaunch_policy(client)

    assert type(client) is Wrapped
    assert any(
        log["event"] == "llm_relaunch_policy_unadopted" and log["client"] == "Wrapped"
        for log in logs
    )
    client.close()
