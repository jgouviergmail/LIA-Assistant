"""One asynchronous HTTP attempt, without mutating a factory-cached client."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai.chat_models.base import BaseChatOpenAI
from openai import AsyncOpenAI

from src.infrastructure.llm.providers.anthropic_hooks import install_claude_hooks


@asynccontextmanager
async def single_async_attempt(llm: BaseChatModel) -> AsyncIterator[BaseChatModel]:
    """Lend a one-attempt copy of a factory-cached model for the duration of one call.

    The copy keeps the cached instance's transport and connection pool. Gemini's
    adapter closes ``self.client`` when an instance is garbage-collected, and the
    copy shares that client: its borrowed reference is released when the call
    ends, so the cached instance keeps an open client for every concurrent and
    later caller.

    Args:
        llm: The factory-cached chat model; never mutated.

    Yields:
        A copy that performs exactly one HTTP attempt and runs no factory callback.

    Raises:
        ValueError: The provider exposes no transport whose retries can be bounded.
    """
    bounded = _bounded_copy(llm)
    try:
        yield bounded
    finally:
        if isinstance(bounded, ChatGoogleGenerativeAI):
            # Released, not reconfigured: bypass the model's assignment hooks.
            object.__setattr__(bounded, "client", None)


def _bounded_copy(llm: BaseChatModel) -> BaseChatModel:
    """Copy ``llm`` with its provider retries disabled and no factory callback.

    Args:
        llm: The factory-cached chat model; never mutated.

    Returns:
        The bounded copy.

    Raises:
        ValueError: The provider exposes no transport whose retries can be bounded.
    """
    if isinstance(llm, BaseChatOpenAI) and isinstance(llm.root_async_client, AsyncOpenAI):
        transport = llm.root_async_client.with_options(max_retries=0)
        return llm.model_copy(
            update={
                "max_retries": 0,
                "root_async_client": transport,
                "async_client": transport.chat.completions,
                "callbacks": [],
            }
        )
    if isinstance(llm, ChatAnthropic) and isinstance(llm._async_client, AsyncAnthropic):
        clone = llm.model_copy(update={"max_retries": 0, "callbacks": []})
        # This is a cached_property in the installed native client, not a model field.
        clone.__dict__["_async_client"] = llm._async_client.with_options(max_retries=0)
        # Factory hooks are closures over their original instance. Reinstall
        # them from the class methods so every payload follows the owned copy.
        for hook in ("_get_request_payload", "_make_message_chunk_from_anthropic_event"):
            clone.__dict__.pop(hook, None)
        install_claude_hooks(clone)
        return clone
    if isinstance(llm, ChatGoogleGenerativeAI):
        # The installed adapter writes this into request HttpRetryOptions;
        # google-genai maps zero to one total attempt, including the initial one.
        return llm.model_copy(update={"max_retries": 0, "callbacks": []})
    if isinstance(llm, ChatOllama):
        # Native Ollama/httpx has no retry loop of its own.
        return llm.model_copy(update={"callbacks": []})
    raise ValueError("single_attempt_transport_unavailable")
