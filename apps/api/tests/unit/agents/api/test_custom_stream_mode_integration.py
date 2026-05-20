"""LangGraph custom-mode → streaming service integration test (Task 2.4).

Builds a minimal LangGraph that calls `langgraph.config.get_stream_writer()`
to push a payload, runs it with `stream_mode=["custom"]`, then feeds the
yielded `(mode, chunk)` tuples to `StreamingService._process_custom_chunk`.

This is the only place where the end-to-end "node writer → custom mode →
ChatStreamChunk" wire is exercised — the rest of the suite mocks either
side of the boundary. Catches integration regressions if LangGraph changes
the shape of custom payloads or if our handler stops accepting them.

Phase: F4.5 — Compaction v2 / Task 2.4
Created: 2026-05-19
"""

from __future__ import annotations

from typing import Annotated, Any

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from src.domains.agents.services.streaming.service import StreamingService


class _MiniState(TypedDict):
    """Minimal state matching LangGraph's required schema."""

    messages: Annotated[list[Any], add_messages]
    sentinel: int


async def _writer_node(_state: _MiniState) -> dict[str, Any]:
    """Node that mimics how `compaction_node` pushes start/done payloads."""
    writer = get_stream_writer()
    writer(
        {
            "type": "execution_step",
            "step_type": "compaction",
            "step_label": "compaction_start",
            "metadata": {"phase": "start", "estimated_duration_seconds": 12},
        }
    )
    writer(
        {
            "type": "execution_step",
            "step_type": "compaction",
            "step_label": "compaction_done",
            "metadata": {"phase": "done", "tokens_saved": 1234, "strategy": "single_chunk"},
        }
    )
    return {"sentinel": 1}


async def test_langgraph_custom_mode_payloads_reach_streaming_service() -> None:
    """A node's writer payloads survive the LangGraph custom mode round-trip
    and are correctly translated by StreamingService._process_custom_chunk."""
    builder: StateGraph[_MiniState] = StateGraph(_MiniState)
    builder.add_node("writer", _writer_node)
    builder.add_edge(START, "writer")
    builder.add_edge("writer", END)
    graph = builder.compile()

    streaming = StreamingService()
    sse_chunks: list[Any] = []

    async for mode, payload in graph.astream(
        {"messages": [], "sentinel": 0},
        stream_mode=["values", "messages", "updates", "custom"],
    ):
        if mode != "custom":
            continue
        for sse_chunk, _content in streaming._process_custom_chunk(payload):
            sse_chunks.append(sse_chunk)

    assert len(sse_chunks) == 2

    start = sse_chunks[0]
    done = sse_chunks[1]
    assert start.type == "execution_step"
    assert start.metadata is not None
    assert start.metadata["step_type"] == "compaction"
    assert start.metadata["step_label"] == "compaction_start"
    assert start.metadata["phase"] == "start"
    assert start.metadata["estimated_duration_seconds"] == 12

    assert done.metadata is not None
    assert done.metadata["step_label"] == "compaction_done"
    assert done.metadata["tokens_saved"] == 1234
    assert done.metadata["strategy"] == "single_chunk"
