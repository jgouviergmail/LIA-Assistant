"""Parity test for the planner reasoning-stream wiring (Voie A, plain ainvoke).

Guarantees ``SmartPlannerService._invoke_planner_streaming_reasoning`` returns a
message whose ``.text`` (consumed by the planner's JSON parser) is identical to
the plain ``ainvoke`` path, and forwards reasoning. No network/LLM.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from src.domains.agents.services.smart_planner_service import SmartPlannerService

_PLAN_JSON = '{"steps": [{"id": "step_1", "tool_name": "get_events_tool"}]}'


class _FakePlannerLLM:
    def __init__(self) -> None:
        self.ainvoke_calls = 0

    async def astream_events(self, _messages: Any, **_kw: Any) -> AsyncIterator[dict[str, Any]]:
        yield {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": AIMessageChunk(
                    content="", additional_kwargs={"reasoning_content": "plan it"}
                )
            },
            "parent_ids": ["root"],
        }
        yield {
            "event": "on_chat_model_end",
            "data": {"output": AIMessageChunk(content=_PLAN_JSON)},
            "parent_ids": [],
        }

    async def ainvoke(self, _messages: Any, **_kw: Any) -> AIMessageChunk:
        self.ainvoke_calls += 1
        return AIMessageChunk(content=_PLAN_JSON)


@pytest.mark.asyncio
class TestPlannerReasoningStream:
    async def test_text_parity_and_emit(self) -> None:
        emitted: list[str] = []
        llm = _FakePlannerLLM()
        with _patch_emit(emitted):
            response = await SmartPlannerService._invoke_planner_streaming_reasoning(
                llm,
                [HumanMessage(content="my agenda")],
                config={"callbacks": []},
            )
        # The planner consumes response.text — must equal the plain JSON, intact.
        assert response.text.strip() == _PLAN_JSON
        assert "".join(emitted) == "plan it"
        assert llm.ainvoke_calls == 0  # streaming used, no fallback

    async def test_falls_back_to_ainvoke_on_empty_stream(self) -> None:
        """If streaming yields no terminal output, fall back to ainvoke (never break planning)."""

        class _EmptyStreamLLM(_FakePlannerLLM):
            async def astream_events(
                self, _messages: Any, **_kw: Any
            ) -> AsyncIterator[dict[str, Any]]:
                if False:  # pragma: no cover - empty async generator
                    yield {}

        llm = _EmptyStreamLLM()
        with _patch_emit([]):
            response = await SmartPlannerService._invoke_planner_streaming_reasoning(
                llm,
                [HumanMessage(content="my agenda")],
                config={"callbacks": []},
            )
        assert response.text.strip() == _PLAN_JSON
        assert llm.ainvoke_calls == 1  # fallback engaged


def _patch_emit(sink: list[str]) -> Any:
    """Patch make_reasoning_emit (resolves get_stream_writer) to append to a sink."""
    from unittest.mock import patch

    return patch(
        "src.infrastructure.llm.reasoning_stream.make_reasoning_emit",
        return_value=sink.append,
    )
