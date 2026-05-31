"""Parity tests for ``get_structured_output(reasoning_emit=...)``.

Guarantees the reasoning-streaming wiring (Voie B) is zero-regression:
- with ``reasoning_emit`` set, the returned parsed/aggregated result is the
  SAME as the plain ``ainvoke`` path (native + JSON-mode);
- reasoning deltas are forwarded to the emit callback;
- when streaming yields no terminal output, it falls back to ``ainvoke``.

No network/LLM: a fake model implements both ``astream_events`` and ``ainvoke``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel, Field

from src.infrastructure.llm.structured_output import get_structured_output


class SimpleDecision(BaseModel):
    reasoning: str = Field(description="why")
    action: str = Field(description="what")
    confidence: float = Field(ge=0, le=1)


_DECISION = SimpleDecision(reasoning="user wants search", action="search", confidence=0.9)
_DECISION_JSON = json.dumps(_DECISION.model_dump())


def _events(*, output: Any, reasoning: list[str], terminal: str) -> list[dict[str, Any]]:
    """Build an astream_events sequence: reasoning chunks + a ROOT terminal event."""
    evs: list[dict[str, Any]] = []
    for frag in reasoning:
        evs.append(
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": AIMessageChunk(
                        content="", additional_kwargs={"reasoning_content": frag}
                    )
                },
                "parent_ids": ["root"],
            }
        )
    evs.append({"event": terminal, "data": {"output": output}, "parent_ids": []})
    return evs


class _FakeStructuredLLM:
    """Stands in for ``llm.with_structured_output(...)`` — native path."""

    def __init__(self) -> None:
        self.ainvoke_calls = 0

    async def astream_events(self, _messages: Any, **_kw: Any) -> AsyncIterator[dict[str, Any]]:
        for ev in _events(output=_DECISION, reasoning=["think ", "more"], terminal="on_chain_end"):
            yield ev

    async def ainvoke(self, _messages: Any, **_kw: Any) -> SimpleDecision:
        self.ainvoke_calls += 1
        return _DECISION


class _FakeNativeLLM:
    def __init__(self) -> None:
        self.structured = _FakeStructuredLLM()

    def with_structured_output(self, _schema: Any, **_kw: Any) -> _FakeStructuredLLM:
        return self.structured


class _FakeJsonModeLLM:
    """Raw LLM for the JSON-mode fallback path (deepseek thinking)."""

    def __init__(self) -> None:
        self.ainvoke_calls = 0

    async def astream_events(self, _messages: Any, **_kw: Any) -> AsyncIterator[dict[str, Any]]:
        msg = AIMessageChunk(content=_DECISION_JSON)
        for ev in _events(output=msg, reasoning=["step1 ", "step2"], terminal="on_chat_model_end"):
            yield ev

    async def ainvoke(self, _messages: Any, **_kw: Any) -> AIMessageChunk:
        self.ainvoke_calls += 1
        return AIMessageChunk(content=_DECISION_JSON)


class _FakeBoundToolLLM:
    """Stands in for ``llm.bind_tools([schema], tool_choice="auto")`` — streams
    reasoning, then emits the schema as a tool call (OpenAI auto-tool path)."""

    def __init__(self, *, emit_tool_call: bool) -> None:
        self._emit_tool_call = emit_tool_call

    async def astream_events(self, _messages: Any, **_kw: Any) -> AsyncIterator[dict[str, Any]]:
        if self._emit_tool_call:
            output = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "SimpleDecision",
                        "args": _DECISION.model_dump(),
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            output = AIMessage(content="no tool here")  # model declined the tool
        for ev in _events(
            output=output, reasoning=["think ", "more"], terminal="on_chat_model_end"
        ):
            yield ev


class _FakeOpenAIAutoToolLLM:
    """OpenAI-like model exposing both ``bind_tools`` (auto-tool streaming path)
    and ``with_structured_output`` (buffered fallback)."""

    def __init__(self, *, emit_tool_call: bool) -> None:
        self.bound = _FakeBoundToolLLM(emit_tool_call=emit_tool_call)
        self.structured = _FakeStructuredLLM()
        self.bind_calls = 0

    def bind_tools(self, _tools: Any, **_kw: Any) -> _FakeBoundToolLLM:
        self.bind_calls += 1
        return self.bound

    def with_structured_output(self, _schema: Any, **_kw: Any) -> _FakeStructuredLLM:
        return self.structured


@pytest.mark.asyncio
class TestOpenAIAutoToolPath:
    async def test_auto_tool_streams_reasoning_and_parses(self) -> None:
        """OpenAI: schema bound as an auto tool → reasoning streamed + parsed result.

        No forced tool_choice (which would suppress the reasoning summary); the
        tool-call args are validated into the schema. No buffered fallback.
        """
        emitted: list[str] = []
        llm = _FakeOpenAIAutoToolLLM(emit_tool_call=True)
        with patch("src.infrastructure.llm.structured_output.settings") as s:
            s.provider_supports_structured_output = {"openai": True}
            result = await get_structured_output(
                llm=llm,  # type: ignore[arg-type]
                messages=[HumanMessage(content="x")],
                schema=SimpleDecision,
                provider="openai",
                reasoning_emit=emitted.append,
            )
        assert result == _DECISION  # parsed from the tool-call args
        assert "".join(emitted) == "think more"  # reasoning streamed live
        assert llm.bind_calls == 1  # auto-tool path used
        assert llm.structured.ainvoke_calls == 0  # no buffered fallback

    async def test_auto_tool_falls_back_to_buffered_when_tool_declined(self) -> None:
        """OpenAI: if the model emits no tool call, fall back to buffered ainvoke."""
        emitted: list[str] = []
        llm = _FakeOpenAIAutoToolLLM(emit_tool_call=False)
        with patch("src.infrastructure.llm.structured_output.settings") as s:
            s.provider_supports_structured_output = {"openai": True}
            result = await get_structured_output(
                llm=llm,  # type: ignore[arg-type]
                messages=[HumanMessage(content="x")],
                schema=SimpleDecision,
                provider="openai",
                reasoning_emit=emitted.append,
            )
        assert result == _DECISION  # parity preserved via buffered fallback
        assert llm.bind_calls == 1  # auto-tool attempted first
        assert llm.structured.ainvoke_calls == 1  # then buffered fallback


class _FakeAnthropicThinkingLLM:
    """Anthropic-like model with extended thinking ON (exposes a ``.thinking`` dict).

    Structured output on a thinking-enabled Claude MUST go through the auto-tool
    path: a forced ``tool_choice`` is rejected by the API (400). There is no
    buffered forced-tool fallback (it would 400), so a missing tool call raises.
    """

    def __init__(self, *, emit_tool_call: bool) -> None:
        self.thinking = {"type": "adaptive"}
        self.bound = _FakeBoundToolLLM(emit_tool_call=emit_tool_call)
        self.structured = _FakeStructuredLLM()
        self.bind_calls = 0

    def bind_tools(self, _tools: Any, **_kw: Any) -> _FakeBoundToolLLM:
        self.bind_calls += 1
        return self.bound

    def with_structured_output(self, _schema: Any, **_kw: Any) -> _FakeStructuredLLM:
        return self.structured


@pytest.mark.asyncio
class TestAnthropicThinkingAutoToolPath:
    async def test_thinking_uses_auto_tool_and_parses(self) -> None:
        """Anthropic thinking ON → auto-tool path, reasoning streamed, parsed result.

        Applies regardless of reasoning_emit, but never falls back to the forced-tool
        buffered path (which would 400 with thinking enabled).
        """
        emitted: list[str] = []
        llm = _FakeAnthropicThinkingLLM(emit_tool_call=True)
        with patch("src.infrastructure.llm.structured_output.settings") as s:
            s.provider_supports_structured_output = {"anthropic": True}
            result = await get_structured_output(
                llm=llm,  # type: ignore[arg-type]
                messages=[HumanMessage(content="x")],
                schema=SimpleDecision,
                provider="anthropic",
                reasoning_emit=emitted.append,
            )
        assert result == _DECISION  # parsed from the tool-call args
        assert "".join(emitted) == "think more"  # reasoning streamed live
        assert llm.bind_calls == 1  # auto-tool path used
        assert llm.structured.ainvoke_calls == 0  # NO forced-tool fallback (would 400)

    async def test_thinking_no_tool_call_raises(self) -> None:
        """Anthropic thinking ON + model declines the tool → raise (no safe fallback)."""
        from src.infrastructure.llm.structured_output import StructuredOutputError

        emitted: list[str] = []
        llm = _FakeAnthropicThinkingLLM(emit_tool_call=False)
        with patch("src.infrastructure.llm.structured_output.settings") as s:
            s.provider_supports_structured_output = {"anthropic": True}
            with pytest.raises(StructuredOutputError):
                await get_structured_output(
                    llm=llm,  # type: ignore[arg-type]
                    messages=[HumanMessage(content="x")],
                    schema=SimpleDecision,
                    provider="anthropic",
                    reasoning_emit=emitted.append,
                )
        assert llm.structured.ainvoke_calls == 0  # never falls back to the forced tool


@pytest.mark.asyncio
class TestReasoningEmitParity:
    async def test_native_path_parity_and_emit(self) -> None:
        """Generic native path (non-OpenAI): reasoning_emit = ainvoke result + deltas.

        Uses ``anthropic`` because OpenAI is diverted to the auto-tool path (see
        ``TestOpenAIAutoToolPath``); deepseek/anthropic keep the generic
        ``with_structured_output`` streaming path validated here.
        """
        emitted: list[str] = []
        llm = _FakeNativeLLM()
        with patch("src.infrastructure.llm.structured_output.settings") as s:
            s.provider_supports_structured_output = {"anthropic": True}
            result = await get_structured_output(
                llm=llm,  # type: ignore[arg-type]
                messages=[HumanMessage(content="x")],
                schema=SimpleDecision,
                provider="anthropic",
                reasoning_emit=emitted.append,
            )
        assert isinstance(result, SimpleDecision)
        assert result == _DECISION  # parity: identical to the ainvoke result
        assert "".join(emitted) == "think more"  # reasoning forwarded
        assert llm.structured.ainvoke_calls == 0  # streaming path used, no fallback

    async def test_json_mode_path_parity_and_emit(self) -> None:
        """JSON-mode path (deepseek thinking): parsed result identical + reasoning emitted."""
        emitted: list[str] = []
        llm = _FakeJsonModeLLM()
        with (
            patch("src.infrastructure.llm.structured_output.settings") as s,
            patch(
                "src.infrastructure.llm.structured_output._is_v4_thinking_enabled",
                return_value=True,
            ),
        ):
            s.provider_supports_structured_output = {"deepseek": True}
            result = await get_structured_output(
                llm=llm,  # type: ignore[arg-type]
                messages=[HumanMessage(content="x")],
                schema=SimpleDecision,
                provider="deepseek",
                reasoning_emit=emitted.append,
            )
        assert isinstance(result, SimpleDecision)
        assert result == _DECISION  # parity: parsed JSON identical
        assert "".join(emitted) == "step1 step2"
        assert llm.ainvoke_calls == 0  # streaming used, no fallback

    async def test_no_emit_is_unchanged_behavior(self) -> None:
        """Without reasoning_emit, the native path must use plain ainvoke (no streaming)."""
        llm = _FakeNativeLLM()
        with patch("src.infrastructure.llm.structured_output.settings") as s:
            s.provider_supports_structured_output = {"openai": True}
            result = await get_structured_output(
                llm=llm,  # type: ignore[arg-type]
                messages=[HumanMessage(content="x")],
                schema=SimpleDecision,
                provider="openai",
            )
        assert result == _DECISION
        assert llm.structured.ainvoke_calls == 1  # plain ainvoke path, unchanged
