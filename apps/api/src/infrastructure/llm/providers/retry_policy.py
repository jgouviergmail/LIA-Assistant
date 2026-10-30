"""When a model call may be sent again — one declared policy for every family.

Spec 2026-10-21 E2, owner decision Q3 (a) of 2026-10-28: a generation whose outcome is
unknown is never relaunched automatically. Measured before this module (local-server
simulation, 2026-10-28): the clients LIA builds sent THREE requests after a read timeout
on the OpenAI wire and on Anthropic — a request that may have run and been billed,
bought again twice — and Gemini six after a 500 or a 429 (34 s).

The policy, whatever the family:

- **never after a timeout**, nor after any transport failure once the request may have
  been sent: the provider may already be generating;
- **at most ``LLM_TRANSIENT_RETRY_MAX`` relaunches** after a 429, a 5xx (each SDK's own
  status rule, ``x-should-retry`` and ``Retry-After`` honoured) or a connection that
  never reached the provider (``ConnectError``, ``ConnectTimeout``, ``PoolTimeout``);
- **a stream is never relaunched once its first byte arrived**: no SDK does — the body
  is read after the request returns, outside their retry loop;
- **retry at one layer only**: a caller's own loop (the structured-output door, the
  compaction) asks ``client_retries.caller_may_relaunch``, which leaves every call to a
  client owning its retries and never sends again a call that may have reached the
  provider; the agents' retry middleware, which cannot see the model, relaunches only a
  call that never left.

Each family receives it through the one seam its SDK offers (the module of tests
``test_retry_policy.py`` records where each SDK decides):

- the OpenAI wire (OpenAI, DeepSeek, Perplexity, Qwen): ``_send_request`` turns a failure
  after the send into an ``OpenAIError``, which the SDK's loop re-raises unretried;
- Anthropic: ``_should_retry_exception`` keeps a transport failure retryable only when
  the request never reached the server;
- Gemini: ``HttpRetryOptions.attempts`` counts the original request, so the budget is
  translated; and its transport is the httpx one, where a failure after the send leaves
  as a ``TimeoutError`` or a ``ConnectionError`` its predicate never retries — its aiohttp
  branch sent a request again, once, after a lost connection whatever the options said,
  and its synchronous predicate retried a read timeout (measured: 2 and 3 requests);
- Ollama: no retry loop of its own.

The SDK clients LangChain builds are given the policy by ADOPTION: their class becomes a
subclass adding only the decision, so every copy the SDK makes of them (``with_options``,
the single-attempt lender) keeps it, and no parameter is rebuilt beside LangChain's own.
A client LIA builds itself for a billed generation (an image, a spoken answer) is adopted
through ``adopt_relaunch_policy``.
"""

from __future__ import annotations

from typing import Any, TypeVar

import anthropic
import httpx
import openai
from google.genai import _api_client as genai_transport
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai.chat_models.base import BaseChatOpenAI

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.utils.request_outcome import error_chain, never_reached_the_server

logger = get_logger(__name__)

_Client = TypeVar("_Client")


def _openai_verdict(
    error: httpx.TransportError, request: httpx.Request
) -> openai.APIConnectionError:
    """A failure once sent, as the error the OpenAI SDK's loop re-raises without sending again."""
    if isinstance(error, httpx.TimeoutException):
        return openai.APITimeoutError(request=request)
    return openai.APIConnectionError(request=request)


class _PolicyOpenAI(openai.OpenAI):
    """The OpenAI-wire client, sending a request again only when it never left."""

    def _send_request(
        self, request: httpx.Request, *, stream: bool, **kwargs: Any
    ) -> httpx.Response:
        try:
            return super()._send_request(request, stream=stream, **kwargs)
        except httpx.TransportError as error:
            if never_reached_the_server(error):
                raise
            raise _openai_verdict(error, request) from error


class _PolicyAsyncOpenAI(openai.AsyncOpenAI):
    """The asynchronous OpenAI-wire client, sending a request again only when it never left."""

    async def _send_request(
        self, request: httpx.Request, *, stream: bool, **kwargs: Any
    ) -> httpx.Response:
        try:
            return await super()._send_request(request, stream=stream, **kwargs)
        except httpx.TransportError as error:
            if never_reached_the_server(error):
                raise
            raise _openai_verdict(error, request) from error


def _anthropic_verdict(
    verdict: tuple[bool, httpx.Response | None], error: BaseException
) -> tuple[bool, httpx.Response | None]:
    """The SDK's verdict, refused for a transport failure once the request may have left."""
    retry, response = verdict
    transport = any(isinstance(link, anthropic.APIConnectionError) for link in error_chain(error))
    if retry and response is None and transport and not never_reached_the_server(error):
        return False, None
    return verdict


class _PolicyAnthropic(anthropic.Anthropic):
    """The Anthropic client, sending a request again only when it never left."""

    def _should_retry_exception(self, err: BaseException) -> tuple[bool, httpx.Response | None]:
        return _anthropic_verdict(super()._should_retry_exception(err), err)


class _PolicyAsyncAnthropic(anthropic.AsyncAnthropic):
    """The asynchronous Anthropic client, sending a request again only when it never left."""

    def _should_retry_exception(self, err: BaseException) -> tuple[bool, httpx.Response | None]:
        return _anthropic_verdict(super()._should_retry_exception(err), err)


def _genai_verdict(error: httpx.TransportError) -> Exception:
    """A failure once sent, as an error google-genai's retry predicate never retries."""
    if isinstance(error, httpx.TimeoutException):
        return TimeoutError(f"model call timed out once sent ({type(error).__name__})")
    return ConnectionError(f"model call lost once sent ({type(error).__name__})")


class _PolicyGenaiTransport(genai_transport.BaseApiClient):
    """google-genai's transport, sending a request again only when it never left."""

    def _use_aiohttp(self) -> bool:
        # Its aiohttp branch re-sends after a lost connection, outside every option.
        return False

    def _request_once(
        self, http_request: genai_transport.HttpRequest, stream: bool = False
    ) -> genai_transport.HttpResponse:
        try:
            return super()._request_once(http_request, stream)
        except httpx.TransportError as error:
            if never_reached_the_server(error):
                raise
            raise _genai_verdict(error) from error

    async def _async_request_once(
        self, http_request: genai_transport.HttpRequest, stream: bool = False
    ) -> genai_transport.HttpResponse:
        try:
            return await super()._async_request_once(http_request, stream)
        except httpx.TransportError as error:
            if never_reached_the_server(error):
                raise
            raise _genai_verdict(error) from error


#: Each SDK client class LangChain builds, and the class that adds the policy to it.
_ADOPTIONS: dict[type, type] = {
    openai.OpenAI: _PolicyOpenAI,
    openai.AsyncOpenAI: _PolicyAsyncOpenAI,
    anthropic.Anthropic: _PolicyAnthropic,
    anthropic.AsyncAnthropic: _PolicyAsyncAnthropic,
    genai_transport.BaseApiClient: _PolicyGenaiTransport,
}


def _adopt(client: object) -> None:
    """Give an SDK client the policy's class, in place.

    A client class no adoption declares is left as it is and SAID (a LangChain release
    that wraps its client): refusing it would refuse every model call of the family.
    """
    if type(client) in _ADOPTIONS.values():
        return
    policy = _ADOPTIONS.get(type(client))
    if policy is None:
        logger.warning("llm_relaunch_policy_unadopted", client=type(client).__name__)
        return
    # The subclass adds a decision and no state: every copy the SDK makes keeps it.
    object.__setattr__(client, "__class__", policy)


def _adopt_with_budget(client: object, relaunches: int) -> None:
    """Adopt an OpenAI-wire or Anthropic client and give it its relaunch budget."""
    _adopt(client)
    setattr(client, "max_retries", relaunches)  # noqa: B010 - an SDK attribute read per request


def adopt_relaunch_policy(client: _Client) -> _Client:
    """Give an OpenAI or Anthropic SDK client LIA builds itself the one relaunch policy.

    For a billed generation outside the chat factory — an image, a spoken answer — whose
    SDK would otherwise send it again twice after a timeout.

    Args:
        client: An ``openai`` or ``anthropic`` client, synchronous or not.

    Returns:
        The same client, under the policy and ``LLM_TRANSIENT_RETRY_MAX``.
    """
    _adopt_with_budget(client, settings.llm_transient_retry_max)
    return client


def apply_relaunch_policy(llm: BaseChatModel) -> BaseChatModel:
    """Give a chat model built by the adapter the one relaunch policy of its family.

    Args:
        llm: The model ``ProviderAdapter.create_llm`` built.

    Returns:
        The same model, its client(s) under the policy. A model class no family declares
        is returned as it is (``test_retry_policy`` holds every ``ProviderType`` to a
        family, measured on a real local server).
    """
    relaunches = settings.llm_transient_retry_max
    if isinstance(llm, BaseChatOpenAI):
        for client in (llm.root_client, llm.root_async_client):
            if client is not None:
                _adopt_with_budget(client, relaunches)
        llm.max_retries = relaunches
    elif isinstance(llm, ChatAnthropic):
        _adopt_with_budget(llm._client, relaunches)
        _adopt_with_budget(llm._async_client, relaunches)
        llm.max_retries = relaunches
    elif isinstance(llm, ChatGoogleGenerativeAI):
        if llm.client is not None:
            _adopt(llm.client._api_client)  # `client.aio` shares it
        # LangChain writes it into HttpRetryOptions.attempts, which counts the original
        # request; zero is one attempt in google-genai.
        llm.max_retries = relaunches + 1 if relaunches else 0
    elif not isinstance(llm, ChatOllama):  # Ollama has no retry loop of its own
        logger.warning("llm_relaunch_policy_unadopted", model_class=type(llm).__name__)
    return llm


__all__ = ["adopt_relaunch_policy", "apply_relaunch_policy", "never_reached_the_server"]
