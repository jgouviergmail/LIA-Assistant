"""The Claude hooks, driven through the REAL ``langchain-anthropic`` client (ADR-362).

No network: the client's ``_acreate`` is replaced by a scripted stream of the
SDK's own event types, so every line of ``ChatAnthropic`` between the provider
and LIA's usage reader runs as in production — the chunk builder, the stream
aggregation, the callbacks. That is the point: the stream hook leans on a
private method of the client, and a version that renames or reshapes it must
fail HERE rather than bill one-hour writes at the five-minute rate in silence.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from anthropic.types import (
    CacheCreation,
    Message,
    MessageDeltaUsage,
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    RawMessageDeltaEvent,
    RawMessageStartEvent,
    RawMessageStopEvent,
    TextBlock,
    TextDelta,
    Usage,
)
from anthropic.types.raw_message_delta_event import Delta
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import AsyncCallbackHandler, BaseCallbackHandler
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import LLMResult
from langchain_core.runnables import RunnableConfig

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.infrastructure.llm.prompt_cache_horizon import extended_prompt_cache_horizon
from src.infrastructure.llm.providers.anthropic_hooks import (
    install_claude_hooks,
    with_stream_write_breakdown,
)
from src.infrastructure.llm.reasoning_stream import stream_reasoning_events
from src.infrastructure.llm.usage_metadata import (
    STREAM_CACHE_WRITE_EXTENDED_KEY,
    STREAM_CACHE_WRITE_SHORT_KEY,
    tokens_from_response,
)
from src.infrastructure.observability.metrics_prompt_cache import (
    llm_cache_write_breakdown_missing_total,
)
from src.infrastructure.observability.token_extractor import TokenExtractor

pytestmark = pytest.mark.unit

MODEL = "claude-sonnet-5"


def _usage(*, written: int, short: int | None, extended: int | None) -> Usage:
    breakdown = (
        None
        if short is None or extended is None
        else CacheCreation(ephemeral_5m_input_tokens=short, ephemeral_1h_input_tokens=extended)
    )
    return Usage(
        input_tokens=1_000,
        output_tokens=1,
        cache_creation_input_tokens=written,
        cache_read_input_tokens=0,
        cache_creation=breakdown,
    )


def _message(usage: Usage, text: str = "") -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model=MODEL,
        content=[TextBlock(type="text", text=text)] if text else [],
        stop_reason="end_turn" if text else None,
        stop_sequence=None,
        usage=usage,
    )


def _stream_events(*, written: int, short: int | None, extended: int | None) -> list[Any]:
    """What the Messages API streams: the breakdown at the START only."""
    return [
        RawMessageStartEvent(
            type="message_start",
            message=_message(_usage(written=written, short=short, extended=extended)),
        ),
        RawContentBlockStartEvent(
            type="content_block_start", index=0, content_block=TextBlock(type="text", text="")
        ),
        RawContentBlockDeltaEvent(
            type="content_block_delta", index=0, delta=TextDelta(type="text_delta", text="Hi")
        ),
        RawContentBlockStopEvent(type="content_block_stop", index=0),
        RawMessageDeltaEvent(
            type="message_delta",
            delta=Delta(stop_reason="end_turn", stop_sequence=None),
            # The stream's END: the write total, never its breakdown.
            usage=MessageDeltaUsage(
                input_tokens=1_000,
                output_tokens=12,
                cache_creation_input_tokens=written,
                cache_read_input_tokens=0,
            ),
        ),
        RawMessageStopEvent(type="message_stop"),
    ]


class _Stream:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        for event in self._events:
            yield event


def _hooked(model: str = MODEL) -> ChatAnthropic:
    """A real Claude client carrying LIA's hooks; nothing is ever sent."""
    llm = ChatAnthropic(model=model, api_key="sk-test", max_tokens=64)
    install_claude_hooks(llm)
    return llm


def _client(response: Any) -> ChatAnthropic:
    """A real client whose transport is replaced by ``response``."""
    llm = _hooked()

    async def _acreate(payload: dict[str, Any]) -> Any:
        return _Stream(response) if payload.get("stream") else response

    object.__setattr__(llm, "_acreate", _acreate)
    return llm


class _CapturedEnd(AsyncCallbackHandler):
    """Keeps the ``LLMResult`` the callbacks see, as the turn's accounting does."""

    def __init__(self) -> None:
        self.results: list[LLMResult] = []

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self.results.append(response)


async def _streamed(llm: ChatAnthropic, handler: _CapturedEnd | None = None) -> AIMessage:
    callbacks: list[BaseCallbackHandler] = [handler] if handler is not None else []
    config: RunnableConfig = {"callbacks": callbacks}
    aggregate = None
    async for chunk in llm.astream([HumanMessage(content="Hello")], config):
        aggregate = chunk if aggregate is None else aggregate + chunk
    assert aggregate is not None
    return AIMessage(
        content=aggregate.content,
        usage_metadata=aggregate.usage_metadata,
        response_metadata=aggregate.response_metadata,
    )


class TestTheStreamTellsWhichWritesWereForTheHour:
    async def test_a_streamed_response_reports_its_one_hour_writes(self) -> None:
        llm = _client(_stream_events(written=5_000, short=1_200, extended=3_800))
        tokens = tokens_from_response(await _streamed(llm))
        assert (tokens.cache_write, tokens.cache_write_extended) == (5_000, 3_800)
        # The prompt count is langchain's own (input + cache read + cache
        # creation), untouched: the copied breakdown adds no token anywhere.
        assert tokens.prompt == 6_000

    async def test_the_turns_accounting_reads_the_same_split(self) -> None:
        """``on_llm_end`` is where the turn's tracker and the metrics price a call."""
        handler = _CapturedEnd()
        llm = _client(_stream_events(written=5_000, short=1_200, extended=3_800))
        await _streamed(llm, handler)
        assert len(handler.results) == 1
        usage = TokenExtractor.extract(handler.results[0])
        assert usage is not None
        assert (usage.cache_write_tokens, usage.cache_write_extended_tokens) == (5_000, 3_800)

    async def test_a_stream_without_writes_is_left_as_langchain_built_it(self) -> None:
        llm = _client(_stream_events(written=0, short=0, extended=0))
        message = await _streamed(llm)
        usage = message.usage_metadata
        details = (usage.get("input_token_details") if usage is not None else None) or {}
        assert not any(key.startswith("stream_cache_write") for key in details)
        assert tokens_from_response(message).cache_write == 0

    async def test_a_start_that_names_no_breakdown_is_counted_and_read_as_short(self) -> None:
        """Fail CLOSED on the count, never on the call: the total stays exact,
        the missing split is a series an operator sees (expected 0)."""
        counter = llm_cache_write_breakdown_missing_total.labels(model=MODEL)
        before = counter._value.get()
        llm = _client(_stream_events(written=5_000, short=None, extended=None))
        tokens = tokens_from_response(await _streamed(llm))
        assert counter._value.get() == before + 1
        assert (tokens.cache_write, tokens.cache_write_extended) == (5_000, 0)

    def test_counts_already_on_the_stream_start_are_kept(self) -> None:
        """Today the client puts every count on the stream's END; a version that
        moved some to its START must not see them erased by the copy."""
        chunk = AIMessageChunk(
            content="",
            usage_metadata={
                "input_tokens": 1_000,
                "output_tokens": 0,
                "total_tokens": 1_000,
                "input_token_details": {"cache_read": 7},
            },
        )
        event = RawMessageStartEvent(
            type="message_start",
            message=_message(_usage(written=5_000, short=1_200, extended=3_800)),
        )
        usage = with_stream_write_breakdown(chunk, event).usage_metadata
        assert usage is not None
        assert (usage["input_tokens"], usage["total_tokens"]) == (1_000, 1_000)
        assert usage["input_token_details"] == {
            "cache_read": 7,
            STREAM_CACHE_WRITE_SHORT_KEY: 1_200,
            STREAM_CACHE_WRITE_EXTENDED_KEY: 3_800,
        }

    async def test_a_complete_response_carries_its_breakdown_without_the_hook(self) -> None:
        """Pinned: on a non-streamed call langchain copies the breakdown itself."""
        llm = _client(
            _message(_usage(written=5_000, short=1_200, extended=3_800), text="Hi"),
        )
        tokens = tokens_from_response(await llm.ainvoke([HumanMessage(content="Hello")]))
        assert (tokens.cache_write, tokens.cache_write_extended) == (5_000, 3_800)


class TestTheRequestHook:
    def test_every_request_body_goes_through_the_payload_policy(self) -> None:
        llm = _hooked()
        system = "Static rules.\n" * 50 + f"{DYNAMIC_CONTEXT_MARKER}\nToday: 2026-10-22"
        payload = llm._get_request_payload(
            [SystemMessage(content=system), HumanMessage(content="Hello")]
        )
        first = payload["system"][0]
        assert first["cache_control"] == {"type": "ephemeral"}
        assert DYNAMIC_CONTEXT_MARKER not in first["text"]

    def test_an_invoke_time_breakpoint_is_owned_by_the_policy(self) -> None:
        """``cache_control`` passed to the call would land on the last message."""
        llm = _hooked()
        payload = llm._get_request_payload(
            [HumanMessage(content="Hello")], cache_control={"type": "ephemeral"}
        )
        assert "cache_control" not in payload
        last = payload["messages"][-1]["content"]
        assert isinstance(last, str) or all("cache_control" not in block for block in last)

    def test_the_lifetime_the_caller_declared_reaches_the_policy(self) -> None:
        """The scope around ONE call decides; the next call outside it is short."""
        llm = _hooked()
        system = "Static rules.\n" * 50 + f"{DYNAMIC_CONTEXT_MARKER}\nToday: 2026-10-22"
        request = [SystemMessage(content=system), HumanMessage(content="Hello")]
        with extended_prompt_cache_horizon(True):
            inside = llm._get_request_payload(request)
        outside = llm._get_request_payload(request)
        assert inside["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
        assert outside["system"][0]["cache_control"] == {"type": "ephemeral"}

    async def test_the_declared_lifetime_crosses_the_event_stream(self) -> None:
        """The ReAct node calls its model through ``astream_events``: the scope
        declared around that call must reach the request body built inside it."""
        sent: list[dict[str, Any]] = []
        llm = _hooked()

        async def _acreate(payload: dict[str, Any]) -> Any:
            sent.append(payload)
            return _Stream(_stream_events(written=0, short=0, extended=0))

        object.__setattr__(llm, "_acreate", _acreate)
        system = "Static rules.\n" * 50 + f"{DYNAMIC_CONTEXT_MARKER}\nToday: 2026-10-22"
        request = [SystemMessage(content=system), HumanMessage(content="Hello")]
        with extended_prompt_cache_horizon(True):
            await stream_reasoning_events(llm, request, emit=lambda _text: None)
        await stream_reasoning_events(llm, request, emit=lambda _text: None)
        assert [payload["system"][0]["cache_control"] for payload in sent] == [
            {"type": "ephemeral", "ttl": "1h"},
            {"type": "ephemeral"},
        ]

    @staticmethod
    def _history(origin: str, *blocks: dict[str, Any]) -> list[BaseMessage]:
        answer = AIMessage(content=list(blocks), response_metadata={"model_name": origin})
        return [HumanMessage(content="Capital of France?"), answer, HumanMessage(content="Italy?")]

    def test_earlier_thinking_reaches_the_model_that_wrote_it_and_no_other(self) -> None:
        """ADR-362, through the real client's formatting: a generation that keeps
        prior thinking without binding it gets its own back; one that binds it
        gets none (its history changed since)."""
        thinking = {"type": "thinking", "thinking": "", "signature": "sig"}
        text = {"type": "text", "text": "Paris."}
        keeper = _hooked("claude-sonnet-5")
        binder = _hooked("claude-opus-5-5")
        kept = keeper._get_request_payload(self._history("claude-sonnet-5", thinking, text))
        removed = binder._get_request_payload(self._history("claude-opus-5-5", thinking, text))
        assert [block["type"] for block in kept["messages"][1]["content"]] == ["thinking", "text"]
        assert [block["type"] for block in removed["messages"][1]["content"]] == ["text"]

    def test_an_assistant_message_left_with_nothing_is_dropped_by_the_client(self) -> None:
        """The API refuses an empty assistant message; the client drops it."""
        binder = _hooked("claude-opus-5-5")
        thinking = {"type": "thinking", "thinking": "", "signature": "sig"}
        payload = binder._get_request_payload(self._history("claude-opus-5-5", thinking))
        assert [message["role"] for message in payload["messages"]] == ["user", "user"]

    def test_an_object_without_the_client_internals_is_left_alone(self) -> None:
        bare = SimpleNamespace()
        install_claude_hooks(bare)
        assert vars(bare) == {}
