"""Characterization tests for ``StreamingService.stream_sse_chunks`` post-loop blocks.

The main SSE loop dispatches per stream-mode (already covered by
test_streaming_service.py); these tests pin the CURRENT behavior of the
post-loop emission blocks that were previously uncovered — the
content-final-replacement chunk and the debug-panel ``debug_metrics`` chunk —
so they can be extracted into helpers without changing what the stream emits.

Every assertion below was verified GREEN against the pre-refactoring code.
"""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage

from src.domains.agents.services.streaming.service import StreamingService


@pytest.fixture
def conversation_id() -> uuid.UUID:
    return uuid.uuid4()


async def _collect(stream) -> list:
    return [chunk async for chunk in stream]


@pytest.mark.asyncio
async def test_char_content_final_replacement_chunk_emitted():
    """A ``content_final_replacement`` in the final state emits a content_replacement chunk."""
    service = StreamingService()

    async def graph_stream():
        yield (
            "values",
            {"routing_history": [], "content_final_replacement": "FINAL POST-PROCESSED"},
        )
        yield ("messages", (AIMessage(content="stream"), {"langgraph_node": "response"}))

    chunks = await _collect(service.stream_sse_chunks(graph_stream(), uuid.uuid4(), "run-x"))

    replacements = [c for c, _ in chunks if c.type == "content_replacement"]
    assert len(replacements) == 1
    assert replacements[0].content == "FINAL POST-PROCESSED"


@pytest.mark.asyncio
async def test_char_debug_metrics_chunk_emitted_when_panel_enabled():
    """With the debug panel enabled + cached query intelligence, a debug_metrics chunk is emitted."""
    service = StreamingService(debug_panel_enabled=True)
    service._cached_query_intelligence = Mock(
        to_debug_metrics=Mock(return_value={"routing_decision": {"intention": "conversation"}})
    )

    async def graph_stream():
        yield ("values", {"routing_history": [], "messages": []})
        yield ("messages", (AIMessage(content="hi"), {"langgraph_node": "response"}))

    with patch(
        "src.infrastructure.async_utils.await_run_id_tasks",
        AsyncMock(return_value=[]),
    ):
        chunks = await _collect(service.stream_sse_chunks(graph_stream(), uuid.uuid4(), "run-y"))

    debug_chunks = [c for c, _ in chunks if c.type == "debug_metrics"]
    assert len(debug_chunks) == 1
    # Base section from to_debug_metrics + sections added by the builder are merged.
    assert debug_chunks[0].metadata["routing_decision"] == {"intention": "conversation"}
    assert "token_budget" in debug_chunks[0].metadata
    assert "knowledge_enrichment" in debug_chunks[0].metadata


@pytest.mark.asyncio
async def test_char_debug_metrics_not_emitted_when_panel_disabled():
    """No debug_metrics chunk when the panel is disabled (default)."""
    service = StreamingService(debug_panel_enabled=False)
    service._cached_query_intelligence = Mock(to_debug_metrics=Mock(return_value={}))

    async def graph_stream():
        yield ("values", {"routing_history": []})
        yield ("messages", (AIMessage(content="hi"), {"langgraph_node": "response"}))

    chunks = await _collect(service.stream_sse_chunks(graph_stream(), uuid.uuid4(), "run-z"))

    assert not [c for c, _ in chunks if c.type == "debug_metrics"]
