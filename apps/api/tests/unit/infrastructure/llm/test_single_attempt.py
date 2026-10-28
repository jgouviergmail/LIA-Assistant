"""The asynchronous provider transport, rather than its label, has one attempt."""

import gc
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from openai import APIStatusError, AsyncOpenAI
from pydantic import SecretStr

from src.infrastructure.llm.single_attempt import single_async_attempt

pytestmark = pytest.mark.unit


async def test_openai_503_is_one_http_request_without_mutating_the_cached_client() -> None:
    calls = 0

    async def refuse(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            503, json={"error": {"message": "inert fixture", "type": "server_error"}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as http:
        transport = AsyncOpenAI(api_key="inert", http_client=http, max_retries=4)
        original = ChatOpenAI(
            model="fictional",
            api_key=SecretStr("inert"),
            root_async_client=transport,
            async_client=transport.chat.completions,
            max_retries=4,
        )
        async with single_async_attempt(original) as bounded:
            with pytest.raises(APIStatusError):
                await bounded.ainvoke("inert text")
        assert calls == 1
        assert original.max_retries == 4 and original.root_async_client.max_retries == 4


async def test_anthropic_sdk_is_cloned_with_no_retry_and_unknown_clients_fail_closed() -> None:
    original = ChatAnthropic(model_name="fictional", api_key=SecretStr("inert"), max_retries=4)
    async with single_async_attempt(original) as bounded:
        assert isinstance(bounded, ChatAnthropic)
        assert bounded.max_retries == 0 and bounded._async_client.max_retries == 0
    assert original.max_retries == 4 and original._async_client.max_retries == 4
    with pytest.raises(ValueError, match="single_attempt_transport_unavailable"):
        async with single_async_attempt(object()):  # type: ignore[arg-type] — deliberately hostile integration
            pass


async def test_factory_claude_hooks_are_rebound_to_the_owned_copy() -> None:
    from src.infrastructure.llm.providers.anthropic_hooks import install_claude_hooks

    original = ChatAnthropic(model_name="fictional", api_key=SecretStr("inert"), max_tokens=1000)
    install_claude_hooks(original)
    async with single_async_attempt(original) as bounded:
        assert isinstance(bounded, ChatAnthropic)
        bounded.max_tokens = 123
        assert bounded._get_request_payload("inert text")["max_tokens"] == 123
    assert original._get_request_payload("inert text")["max_tokens"] == 1000


async def test_releasing_a_gemini_copy_never_closes_the_cached_instance_client() -> None:
    # The adapter's __del__ closes `self.client`; the copy borrows the cached
    # instance's client, so dropping the copy must leave that client open.
    original = ChatGoogleGenerativeAI(
        model="gemini-fictional", google_api_key=SecretStr("inert"), max_retries=4
    )
    client = original.client
    assert client is not None
    client.close = MagicMock()  # type: ignore[method-assign] — records a destructor call
    client.aio.aclose = AsyncMock()  # type: ignore[method-assign] — records a destructor call
    async with single_async_attempt(original) as bounded:
        assert isinstance(bounded, ChatGoogleGenerativeAI)
        assert bounded.client is client and bounded.max_retries == 0
    del bounded
    gc.collect()
    client.close.assert_not_called()
    client.aio.aclose.assert_not_called()
    assert original.client is client and original.max_retries == 4
