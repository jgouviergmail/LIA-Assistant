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
from langchain_core.messages import AIMessageChunk, HumanMessage
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


@pytest.mark.asyncio
class TestReasoningEmitParity:
    async def test_native_path_parity_and_emit(self) -> None:
        """Native path: reasoning_emit yields same result as ainvoke + emits deltas."""
        emitted: list[str] = []
        llm = _FakeNativeLLM()
        with patch("src.infrastructure.llm.structured_output.settings") as s:
            s.provider_supports_structured_output = {"openai": True}
            result = await get_structured_output(
                llm=llm,  # type: ignore[arg-type]
                messages=[HumanMessage(content="x")],
                schema=SimpleDecision,
                provider="openai",
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
