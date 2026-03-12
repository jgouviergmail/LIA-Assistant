"""
Unit tests for StreamingService.

Tests SSE formatting logic without requiring full graph execution.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.domains.agents.services.streaming.service import StreamingService


@pytest.fixture
def streaming_service():
    """Create StreamingService instance for testing."""
    return StreamingService()


@pytest.fixture
def conversation_id():
    """Generate test conversation ID."""
    return uuid.uuid4()


@pytest.fixture
def run_id():
    """Generate test run ID."""
    return "test_run_123"


@pytest.mark.asyncio
async def test_process_values_chunk_extracts_router_decision(streaming_service):
    """Test that router decisions are extracted from routing_history."""
    # Mock RouterOutput
    mock_routing = MagicMock()
    mock_routing.intention = "contacts_search"
    mock_routing.confidence = 0.95
    mock_routing.context_label = "contacts"
    mock_routing.next_node = "planner"
    mock_routing.reasoning = "User wants to search contacts"

    # Create values chunk with routing_history
    chunk = {
        "routing_history": [mock_routing],
        "messages": [],
    }

    # Process chunk
    sse_chunks = streaming_service._process_values_chunk(chunk, last_sent_routing=None)

    # Assert router decision emitted (result is list of (ChatStreamChunk, content) tuples)
    assert len(sse_chunks) == 1
    assert sse_chunks[0][0].type == "router_decision"
    assert sse_chunks[0][0].content == "Routing decision made"
    assert sse_chunks[0][0].metadata["intention"] == "contacts_search"
    assert sse_chunks[0][0].metadata["confidence"] == 0.95
    assert sse_chunks[0][1] == ""  # No content for router decisions


@pytest.mark.asyncio
async def test_process_values_chunk_avoids_duplicate_router_decisions(streaming_service):
    """Test that duplicate router decisions are not emitted."""
    # Mock RouterOutput
    mock_routing = MagicMock()
    mock_routing.intention = "contacts_search"
    mock_routing.confidence = 0.95
    mock_routing.context_label = "contacts"
    mock_routing.next_node = "planner"
    mock_routing.reasoning = "User wants to search contacts"

    # Create values chunk with routing_history
    chunk = {
        "routing_history": [mock_routing],
        "messages": [],
    }

    # Process chunk with same last_sent_routing
    sse_chunks = streaming_service._process_values_chunk(chunk, last_sent_routing=mock_routing)

    # Assert no router decision emitted (duplicate)
    assert len(sse_chunks) == 0


@pytest.mark.asyncio
async def test_process_messages_chunk_emits_execution_step(streaming_service):
    """Test that execution_step events are emitted for node transitions."""
    # Mock AIMessage
    mock_message = AIMessage(content="Hello")
    metadata = {"langgraph_node": "response"}
    message_tuple = (mock_message, metadata)

    # Process chunk (note: parameter names use underscore prefix: _state, _first_token_time)
    sse_chunks = streaming_service._process_messages_chunk(
        message_tuple,
        _state={},
        last_emitted_node=None,
        _first_token_time=None,
    )

    # Assert execution_step emitted (first chunk)
    assert len(sse_chunks) >= 1
    assert sse_chunks[0][0].type == "execution_step"
    assert sse_chunks[0][0].metadata["step_name"] == "response"
    assert sse_chunks[0][1] == ""  # No content for execution_step


@pytest.mark.asyncio
async def test_process_messages_chunk_filters_response_tokens(streaming_service):
    """Test that tokens are only streamed from response node."""
    # Mock AIMessage from response node
    mock_message = AIMessage(content="Hello world")
    metadata = {"langgraph_node": "response"}
    message_tuple = (mock_message, metadata)

    # Process chunk (note: parameter names use underscore prefix: _state, _first_token_time)
    sse_chunks = streaming_service._process_messages_chunk(
        message_tuple,
        _state={},
        last_emitted_node="response",  # Already emitted execution_step
        _first_token_time=None,
    )

    # Assert token emitted
    assert len(sse_chunks) == 1
    assert sse_chunks[0][0].type == "token"
    assert sse_chunks[0][0].content == "Hello world"
    assert sse_chunks[0][1] == "Hello world"  # Content returned for accumulation


@pytest.mark.asyncio
async def test_process_messages_chunk_filters_router_tokens(streaming_service):
    """Test that tokens from router node are NOT streamed."""
    # Mock AIMessage from router node (JSON output)
    mock_message = AIMessage(content='{"intention": "contacts_search"}')
    metadata = {"langgraph_node": "router"}
    message_tuple = (mock_message, metadata)

    # Process chunk (note: parameter names use underscore prefix: _state, _first_token_time)
    sse_chunks = streaming_service._process_messages_chunk(
        message_tuple,
        _state={},
        last_emitted_node="router",  # Already emitted execution_step
        _first_token_time=None,
    )

    # Assert NO tokens emitted (router is filtered)
    assert len(sse_chunks) == 0


@pytest.mark.asyncio
async def test_should_stream_token_only_allows_response_node(streaming_service):
    """Test that only response node is allowed to stream tokens."""
    assert streaming_service._should_stream_token("response") is True
    assert streaming_service._should_stream_token("router") is False
    assert streaming_service._should_stream_token("planner") is False
    assert streaming_service._should_stream_token("task_orchestrator") is False


@pytest.mark.asyncio
async def test_stream_sse_chunks_accumulates_response_content(
    streaming_service, conversation_id, run_id
):
    """Test that response content is accumulated correctly."""

    # Mock graph stream
    async def mock_graph_stream():
        # Emit router decision
        yield (
            "values",
            {
                "routing_history": [
                    MagicMock(
                        intention="contacts_search",
                        confidence=0.95,
                        context_label="contacts",
                        next_node="planner",
                        reasoning="Test",
                    )
                ]
            },
        )

        # Emit response tokens
        yield ("messages", (AIMessage(content="Hello "), {"langgraph_node": "response"}))
        yield ("messages", (AIMessage(content="world"), {"langgraph_node": "response"}))

    # Stream SSE chunks
    accumulated_content = ""
    async for _sse_chunk, content_fragment in streaming_service.stream_sse_chunks(
        mock_graph_stream(), conversation_id, run_id
    ):
        accumulated_content += content_fragment

    # Assert content accumulated correctly
    assert accumulated_content == "Hello world"


@pytest.mark.asyncio
async def test_format_token_chunk(streaming_service):
    """Test token chunk formatting."""
    chunk = streaming_service.format_token_chunk("Hello")
    assert chunk.type == "token"
    assert chunk.content == "Hello"


@pytest.mark.asyncio
async def test_format_done_chunk(streaming_service):
    """Test done chunk formatting."""
    chunk = streaming_service.format_done_chunk("Final message", metadata={"total_tokens": 100})
    assert chunk.type == "done"
    assert chunk.content["message"] == "Final message"
    assert chunk.content["metadata"]["total_tokens"] == 100


@pytest.mark.asyncio
async def test_format_error_chunk(streaming_service):
    """Test error chunk formatting."""
    error = ValueError("Test error")
    chunk = streaming_service.format_error_chunk(error, context={"run_id": "123"})
    assert chunk.type == "error"
    assert chunk.content["error"] == "Test error"
    assert chunk.content["error_type"] == "ValueError"
    assert chunk.content["context"]["run_id"] == "123"


# =============================================================================
# LARS Registry Update Tests
# =============================================================================


class TestLARSRegistryUpdate:
    """Tests for LARS registry_update SSE event emission."""

    @pytest.mark.asyncio
    async def test_format_registry_update_chunk(self, streaming_service):
        """Test registry_update chunk formatting."""
        items = {
            "contact_abc123": {
                "id": "contact_abc123",
                "type": "CONTACT",
                "payload": {"name": "John Doe", "email": "john@example.com"},
                "meta": {"source": "google_contacts", "timestamp": "2024-01-01T00:00:00Z"},
            }
        }

        chunk = streaming_service.format_registry_update_chunk(items)

        assert chunk.type == "registry_update"
        assert chunk.content == ""  # Empty content - data in metadata
        assert chunk.metadata["count"] == 1
        assert "contact_abc123" in chunk.metadata["items"]
        assert chunk.metadata["items"]["contact_abc123"]["type"] == "CONTACT"

    @pytest.mark.asyncio
    async def test_process_values_chunk_skips_registry_in_values(self, streaming_service):
        """Test that registry in values chunk is SKIPPED (BugFix 2025-11-26).

        Registry updates are now emitted AFTER the streaming loop completes
        (in stream_sse_chunks) to avoid duplicating stale registry data from
        values chunks. Only the fresh registry from state is emitted.
        """
        # Mock RegistryItem (using dict to simulate model_dump output)
        mock_item = MagicMock()
        mock_item.model_dump.return_value = {
            "id": "contact_abc123",
            "type": "CONTACT",
            "payload": {"name": "John Doe"},
            "meta": {"source": "test", "timestamp": "2024-01-01T00:00:00Z"},
        }

        # Create values chunk with registry
        chunk = {
            "registry": {"contact_abc123": mock_item},
            "routing_history": [],
            "messages": [],
        }

        # Process chunk with empty sent_registry_ids
        sent_registry_ids: set[str] = set()
        sse_chunks = streaming_service._process_values_chunk(
            chunk, last_sent_routing=None, sent_registry_ids=sent_registry_ids
        )

        # Assert NO registry_update emitted from values chunk (BugFix 2025-11-26)
        # Registry is emitted post-streaming from stream_sse_chunks
        assert len(sse_chunks) == 0
        # sent_registry_ids should NOT be updated here
        assert "contact_abc123" not in sent_registry_ids

    @pytest.mark.asyncio
    async def test_process_values_chunk_avoids_duplicate_registry_updates(self, streaming_service):
        """Test that already-sent registry items are not re-emitted."""
        mock_item = MagicMock()
        mock_item.model_dump.return_value = {
            "id": "contact_abc123",
            "type": "CONTACT",
            "payload": {"name": "John Doe"},
            "meta": {"source": "test", "timestamp": "2024-01-01T00:00:00Z"},
        }

        chunk = {
            "registry": {"contact_abc123": mock_item},
            "routing_history": [],
            "messages": [],
        }

        # Process with item already in sent_registry_ids
        sent_registry_ids = {"contact_abc123"}
        sse_chunks = streaming_service._process_values_chunk(
            chunk, last_sent_routing=None, sent_registry_ids=sent_registry_ids
        )

        # Assert NO registry_update emitted (already sent)
        assert len(sse_chunks) == 0

    @pytest.mark.asyncio
    async def test_process_values_chunk_router_only_no_registry(self, streaming_service):
        """Test that only router_decision is emitted (registry skipped, BugFix 2025-11-26)."""
        mock_item = MagicMock()
        mock_item.model_dump.return_value = {
            "id": "contact_abc123",
            "type": "CONTACT",
            "payload": {"name": "John Doe"},
            "meta": {"source": "test", "timestamp": "2024-01-01T00:00:00Z"},
        }

        mock_routing = MagicMock()
        mock_routing.intention = "contacts_search"
        mock_routing.confidence = 0.95
        mock_routing.context_label = "contacts"
        mock_routing.next_node = "planner"
        mock_routing.reasoning = "Test"

        chunk = {
            "registry": {"contact_abc123": mock_item},
            "routing_history": [mock_routing],
            "messages": [],
        }

        sent_registry_ids: set[str] = set()
        sse_chunks = streaming_service._process_values_chunk(
            chunk, last_sent_routing=None, sent_registry_ids=sent_registry_ids
        )

        # BugFix 2025-11-26: Registry is skipped in values chunks
        # Only router_decision is emitted
        assert len(sse_chunks) == 1
        assert sse_chunks[0][0].type == "router_decision"

    @pytest.mark.asyncio
    async def test_process_values_chunk_handles_raw_dict_registry_skipped(self, streaming_service):
        """Test that raw dict registry items are SKIPPED (BugFix 2025-11-26)."""
        # Raw dict (already serialized)
        raw_item = {
            "id": "contact_abc123",
            "type": "CONTACT",
            "payload": {"name": "John Doe"},
            "meta": {"source": "test", "timestamp": "2024-01-01T00:00:00Z"},
        }

        chunk = {
            "registry": {"contact_abc123": raw_item},
            "routing_history": [],
            "messages": [],
        }

        sent_registry_ids: set[str] = set()
        sse_chunks = streaming_service._process_values_chunk(
            chunk, last_sent_routing=None, sent_registry_ids=sent_registry_ids
        )

        # BugFix 2025-11-26: Registry is skipped in values chunks
        # No registry_update emitted
        assert len(sse_chunks) == 0

    @pytest.mark.asyncio
    async def test_process_values_chunk_registry_always_skipped(self, streaming_service):
        """Test that registry is always skipped in values chunks (BugFix 2025-11-26).

        Incremental registry updates are now handled post-streaming in
        stream_sse_chunks, not in _process_values_chunk.
        """
        mock_item1 = MagicMock()
        mock_item1.model_dump.return_value = {
            "id": "contact_abc",
            "type": "CONTACT",
            "payload": {"name": "John"},
            "meta": {"source": "test", "timestamp": "2024-01-01T00:00:00Z"},
        }
        mock_item2 = MagicMock()
        mock_item2.model_dump.return_value = {
            "id": "contact_def",
            "type": "CONTACT",
            "payload": {"name": "Jane"},
            "meta": {"source": "test", "timestamp": "2024-01-01T00:00:00Z"},
        }

        # First chunk with item1
        chunk1 = {
            "registry": {"contact_abc": mock_item1},
            "routing_history": [],
        }

        sent_registry_ids: set[str] = set()
        sse_chunks1 = streaming_service._process_values_chunk(
            chunk1, last_sent_routing=None, sent_registry_ids=sent_registry_ids
        )

        # BugFix 2025-11-26: No registry emitted from values chunks
        assert len(sse_chunks1) == 0
        assert "contact_abc" not in sent_registry_ids

        # Second chunk with item1 AND item2 - also skipped
        chunk2 = {
            "registry": {"contact_abc": mock_item1, "contact_def": mock_item2},
            "routing_history": [],
        }

        sse_chunks2 = streaming_service._process_values_chunk(
            chunk2, last_sent_routing=None, sent_registry_ids=sent_registry_ids
        )

        # Also no registry emitted
        assert len(sse_chunks2) == 0
        assert "contact_def" not in sent_registry_ids

    @pytest.mark.asyncio
    async def test_stream_sse_chunks_emits_registry_updates(
        self, streaming_service, conversation_id, run_id
    ):
        """Test that registry_update events are emitted in the full stream."""
        mock_item = MagicMock()
        mock_item.model_dump.return_value = {
            "id": "contact_abc123",
            "type": "CONTACT",
            "payload": {"name": "John Doe"},
            "meta": {"source": "test", "timestamp": "2024-01-01T00:00:00Z"},
        }

        async def mock_graph_stream():
            # Emit state with registry
            yield (
                "values",
                {
                    "registry": {"contact_abc123": mock_item},
                    "routing_history": [],
                },
            )

            # Emit response token
            yield ("messages", (AIMessage(content="Hello"), {"langgraph_node": "response"}))

        # Stream SSE chunks
        registry_updates_received = []
        async for sse_chunk, _content in streaming_service.stream_sse_chunks(
            mock_graph_stream(), conversation_id, run_id
        ):
            if sse_chunk.type == "registry_update":
                registry_updates_received.append(sse_chunk)

        # Assert registry_update emitted
        assert len(registry_updates_received) == 1
        assert registry_updates_received[0].metadata["count"] == 1
