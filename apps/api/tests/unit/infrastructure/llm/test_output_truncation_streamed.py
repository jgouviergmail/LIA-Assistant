"""The provider's truncation verdict survives STREAMING (ADR-275, amended).

The ReAct loop never calls ``ainvoke``: it reads the model through
``stream_reasoning_events``, so the message it judges is the aggregate of a
stream. ``is_output_truncated`` reads ``response_metadata`` — these tests pin
that the aggregate still carries the provider's verdict there, through the two
mechanisms adapters use:

- the verdict on a chunk's own metadata (the OpenAI-compatible family, driven
  here through the production DeepSeek client over a fake SSE transport — the
  family of the 2026-09-25 incident);
- the verdict in the chunk's ``generation_info`` (the Gemini and Ollama
  adapters), which langchain-core merges into the message's metadata.

A library upgrade that loses either would make the loop's guard go blind in
silence — the exact failure this amendment exists to end.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.tools import tool

from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.llm.providers._deepseek_patched import ChatDeepSeekPatched
from src.infrastructure.llm.reasoning_stream import stream_reasoning_events

pytestmark = [pytest.mark.unit]


@tool
def get_weather(city: str) -> str:
    """Get the weather of a city."""
    return f"sunny in {city}"


def _sse_body(finish_reason: str) -> bytes:
    base = {"id": "x", "object": "chat.completion.chunk", "created": 1, "model": "m"}
    chunks: list[dict[str, Any]] = [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "abc "}}]},
        {
            **base,
            "choices": [{"index": 0, "delta": {"content": "abc"}, "finish_reason": finish_reason}],
        },
        {**base, "choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 20000}},
    ]
    lines = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    return f"{lines}data: [DONE]\n\n".encode()


def _provider(finish_reason: str) -> httpx.MockTransport:
    def answer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_body(finish_reason),
        )

    return httpx.MockTransport(answer)


class TestTheOpenAICompatibleStream:
    @pytest.mark.parametrize(("finish_reason", "cut"), [("length", True), ("stop", False)])
    async def test_the_streamed_aggregate_carries_the_verdict(
        self, finish_reason: str, cut: bool
    ) -> None:
        async with httpx.AsyncClient(transport=_provider(finish_reason)) as http:
            llm = ChatDeepSeekPatched(
                model="m",
                api_key="sk-test",
                api_base="http://provider.test/v1",
                streaming=True,
                stream_usage=True,
                max_tokens=20000,
                http_async_client=http,
            ).bind_tools([get_weather])

            message = await stream_reasoning_events(llm, [("user", "hi")], emit=lambda _text: None)

        assert is_output_truncated(message) is cut


class _VerdictInGenerationInfo(BaseChatModel):
    """Streams an answer whose LAST chunk carries the stop verdict in
    ``generation_info`` — where langchain-google-genai (``finish_reason``) and
    langchain-ollama (``done_reason``) put it."""

    verdict: dict[str, str]

    @property
    def _llm_type(self) -> str:
        return "verdict-in-generation-info"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError("the loop reads a stream, never a buffered call")

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        yield ChatGenerationChunk(message=AIMessageChunk(content="part one "))
        yield ChatGenerationChunk(
            message=AIMessageChunk(content="part two"), generation_info=dict(self.verdict)
        )


class TestAVerdictCarriedInGenerationInfo:
    @pytest.mark.parametrize(
        ("verdict", "cut"),
        [
            ({"finish_reason": "MAX_TOKENS"}, True),
            ({"done_reason": "length"}, True),
            ({"finish_reason": "STOP"}, False),
            ({"done_reason": "stop"}, False),
        ],
    )
    async def test_it_reaches_the_aggregated_message(
        self, verdict: dict[str, str], cut: bool
    ) -> None:
        message = await stream_reasoning_events(
            _VerdictInGenerationInfo(verdict=verdict), [("user", "hi")], emit=lambda _t: None
        )

        assert is_output_truncated(message) is cut
