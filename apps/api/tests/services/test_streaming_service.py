"""
Unit tests for StreamingService.

Tests SSE formatting logic without requiring full graph execution.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

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

    # First chunk captures the routing_history baseline (turn-start checkpoint
    # replay — empty here for a fresh conversation). _track_routing_history_change
    # requires the signature to differ from this baseline before emission.
    streaming_service._process_values_chunk(
        {"routing_history": [], "messages": []}, last_sent_routing=None
    )

    # Second chunk: router_node has appended the new RouterOutput
    chunk = {
        "routing_history": [mock_routing],
        "messages": [],
    }
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

    # Baseline chunk (empty routing_history captures the signature)
    streaming_service._process_values_chunk(
        {"routing_history": [], "messages": []}, last_sent_routing=None
    )

    # Subsequent chunk with same routing AND last_sent_routing already set:
    # signature change passes _track_routing_history_change but the
    # last_sent_routing match suppresses the duplicate.
    chunk = {
        "routing_history": [mock_routing],
        "messages": [],
    }
    sse_chunks = streaming_service._process_values_chunk(chunk, last_sent_routing=mock_routing)

    # Assert no router decision emitted (duplicate)
    assert len(sse_chunks) == 0


@pytest.mark.asyncio
async def test_process_values_chunk_suppresses_stale_routing_from_checkpoint(
    streaming_service,
):
    """Regression test: router_decision must NOT be emitted from the
    routing_history entry inherited from the previous turn's checkpoint.

    Scenario reproduced from prod log analysis (2026-05-28):
    - Previous turn ended with intention="conversation" (chit-chat).
    - At the start of the new turn, LangGraph "values" mode emits the checkpoint
      state with routing_history=[prev_turn_routing].
    - Without this guard, a router_decision SSE with intention="conversation"
      was emitted at +308ms, triggering chat_voice_streamer (direct TTS reading
      the displayed text) before the new router_node had classified the query
      as intention="action" (which would otherwise route voice through the
      Voice Comment LLM).
    """
    prev_turn_routing = MagicMock()
    prev_turn_routing.intention = "conversation"
    prev_turn_routing.confidence = 0.99
    prev_turn_routing.context_label = "chitchat"
    prev_turn_routing.next_node = "response"
    prev_turn_routing.reasoning = "Previous turn"

    # First chunk replays the checkpoint with the previous turn's routing
    sse_chunks_initial = streaming_service._process_values_chunk(
        {"routing_history": [prev_turn_routing], "messages": []},
        last_sent_routing=None,
    )
    # No router_decision emitted — stale entry from checkpoint baseline
    assert sse_chunks_initial == []

    # Second chunk: current turn's router_node appended a fresh RouterOutput
    current_turn_routing = MagicMock()
    current_turn_routing.intention = "action"
    current_turn_routing.confidence = 1.0
    current_turn_routing.context_label = "email"
    current_turn_routing.next_node = "planner"
    current_turn_routing.reasoning = "Current turn"

    sse_chunks_fresh = streaming_service._process_values_chunk(
        {
            "routing_history": [prev_turn_routing, current_turn_routing],
            "messages": [],
        },
        last_sent_routing=None,
    )
    assert len(sse_chunks_fresh) == 1
    assert sse_chunks_fresh[0][0].type == "router_decision"
    assert sse_chunks_fresh[0][0].metadata["intention"] == "action"


@pytest.mark.asyncio
async def test_process_messages_chunk_does_not_emit_execution_step(streaming_service):
    """``_process_messages_chunk`` no longer emits ``execution_step`` — node
    transition detection moved to ``_process_updates_chunk`` once LangGraph
    1.x exposed ``stream_mode="updates"`` reliably. This test guards against
    a regression that would re-introduce duplicate step events.
    """
    mock_message = AIMessage(content="Hello")
    metadata = {"langgraph_node": "response"}
    message_tuple = (mock_message, metadata)

    sse_chunks = streaming_service._process_messages_chunk(
        message_tuple,
        _state={},
        _first_token_time=None,
    )

    # No execution_step in the output — only token chunks may appear.
    step_chunks = [c for c, _ in sse_chunks if c.type == "execution_step"]
    assert step_chunks == []


@pytest.mark.asyncio
async def test_process_messages_chunk_streams_response_tokens(streaming_service):
    """Tokens from the ``response`` node are forwarded as SSE token chunks
    (the only node whose tokens reach the client)."""
    mock_message = AIMessage(content="Hello world")
    metadata = {"langgraph_node": "response"}
    message_tuple = (mock_message, metadata)

    sse_chunks = streaming_service._process_messages_chunk(
        message_tuple,
        _state={},
        _first_token_time=None,
    )

    assert len(sse_chunks) == 1
    assert sse_chunks[0][0].type == "token"
    assert sse_chunks[0][0].content == "Hello world"
    assert sse_chunks[0][1] == "Hello world"  # Content returned for accumulation


@pytest.mark.asyncio
async def test_process_messages_chunk_filters_router_tokens(streaming_service):
    """Tokens from non-response nodes (router, planner, ...) MUST NOT be
    streamed — they would surface internal JSON / reasoning to the user."""
    mock_message = AIMessage(content='{"intention": "contacts_search"}')
    metadata = {"langgraph_node": "router"}
    message_tuple = (mock_message, metadata)

    sse_chunks = streaming_service._process_messages_chunk(
        message_tuple,
        _state={},
        _first_token_time=None,
    )

    assert sse_chunks == []


@pytest.mark.asyncio
async def test_process_messages_chunk_skips_complete_message_after_deltas(
    streaming_service,
):
    """Duplicate-display fix: LangGraph "messages" mode emits the LLM's streaming
    deltas (``AIMessageChunk``) AND the complete ``AIMessage`` the response node
    returns to the ``messages`` channel. Once deltas have streamed, the complete
    message is a duplicate and MUST be skipped (otherwise the client shows the
    whole reply twice before the post-loop ``content_replacement`` collapses it).
    """
    node = {"langgraph_node": "response"}

    # 1) A streaming delta is forwarded and marks that deltas were seen.
    delta_chunks = streaming_service._process_messages_chunk(
        (AIMessageChunk(content="Hello world"), node),
        _state={},
        _first_token_time=None,
    )
    assert len(delta_chunks) == 1
    assert delta_chunks[0][0].type == "token"
    assert streaming_service._response_deltas_streamed is True

    # 2) The complete returned message (post-processed AIMessage) is the duplicate.
    dup_chunks = streaming_service._process_messages_chunk(
        (AIMessage(content="Hello world (with photos injected)"), node),
        _state={"content_final_replacement": "Hello world (with photos injected)"},
        _first_token_time=None,
    )
    assert dup_chunks == []


@pytest.mark.asyncio
async def test_process_messages_chunk_emits_complete_message_when_no_deltas(
    streaming_service,
):
    """Non-streaming path: if the response LLM never emitted token deltas, the
    single complete ``AIMessage`` is the only content we have — it MUST be emitted
    once (skipping it would lose the entire reply)."""
    sse_chunks = streaming_service._process_messages_chunk(
        (AIMessage(content="Full reply"), {"langgraph_node": "response"}),
        _state={},
        _first_token_time=None,
    )

    assert len(sse_chunks) == 1
    assert sse_chunks[0][0].type == "token"
    assert sse_chunks[0][1] == "Full reply"


@pytest.mark.asyncio
async def test_process_messages_chunk_streams_consecutive_deltas(streaming_service):
    """Consecutive streaming deltas are all forwarded (no false-positive skip)."""
    node = {"langgraph_node": "response"}

    first = streaming_service._process_messages_chunk(
        (AIMessageChunk(content="Hello "), node), _state={}, _first_token_time=None
    )
    second = streaming_service._process_messages_chunk(
        (AIMessageChunk(content="world"), node), _state={}, _first_token_time=None
    )

    assert [c.content for c, _ in first] == ["Hello "]
    assert [c.content for c, _ in second] == ["world"]


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
async def test_format_error_chunk_returns_localized_user_message(streaming_service):
    """``format_error_chunk`` MUST return a user-friendly localized string and
    MUST NOT leak the raw exception type or message to the client.

    Regression guard: an earlier version exposed
    ``{"error": exc_message, "error_type": exc_class}`` which leaked
    implementation details (and sometimes PII) into SSE payloads.
    """
    error = ValueError("Internal validation message that must not leak")
    chunk = streaming_service.format_error_chunk(error, context={"run_id": "123"})

    assert chunk.type == "error"
    # ``content`` is now a single localized string, not a dict.
    assert isinstance(chunk.content, str)
    assert chunk.content  # non-empty
    # Critical: raw exception type / message must not surface to the client.
    assert "ValueError" not in chunk.content
    assert "Internal validation message" not in chunk.content


@pytest.mark.asyncio
async def test_format_error_chunk_respects_language(streaming_service):
    """Localised error message must vary with the ``language`` argument."""
    error = RuntimeError("boom")
    chunk_fr = streaming_service.format_error_chunk(error, language="fr")
    chunk_en = streaming_service.format_error_chunk(error, language="en")

    assert chunk_fr.type == "error"
    assert chunk_en.type == "error"
    assert isinstance(chunk_fr.content, str)
    assert isinstance(chunk_en.content, str)
    # Different locales must produce different user-facing copy.
    assert chunk_fr.content != chunk_en.content


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

        # Baseline (empty routing_history) — captures signature
        sent_registry_ids: set[str] = set()
        streaming_service._process_values_chunk(
            {"routing_history": [], "messages": []},
            last_sent_routing=None,
            sent_registry_ids=sent_registry_ids,
        )

        chunk = {
            "registry": {"contact_abc123": mock_item},
            "routing_history": [mock_routing],
            "messages": [],
        }
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


# =============================================================================
# _process_updates_chunk — None state_delta (LangGraph no-op normalisation)
# =============================================================================


@pytest.mark.asyncio
async def test_process_updates_chunk_handles_none_state_delta_silently(
    streaming_service,
):
    """LangGraph 1.x normalises an empty-dict return from a node into ``None``
    in ``stream_mode="updates"`` (cf. ``langgraph.pregel._io.map_output_updates``):
    nodes that ran without producing channel writes yield ``{node_name: None}``.

    The streaming service must treat that as the expected no-op signal — log
    at debug level, NOT warning. Regression: previously the path emitted
    ``logger.warning("updates_mode_non_dict_state_delta", ...)`` for every
    no-op node (compaction is the most frequent), polluting prod logs.
    """
    # Patch the module-level logger to assert log levels.
    with patch("src.domains.agents.services.streaming.service.logger") as mock_logger:
        # Use a node that has display metadata so the execution_step path is
        # also traversed end-to-end.
        sse_chunks = streaming_service._process_updates_chunk(
            chunk={"router": None},
            accumulated_state={},
        )

    # No-op debug log was emitted, NOT a warning.
    debug_event_names = [c.args[0] for c in mock_logger.debug.call_args_list if c.args]
    warning_event_names = [c.args[0] for c in mock_logger.warning.call_args_list if c.args]
    assert "updates_mode_node_no_op" in debug_event_names
    assert "updates_mode_non_dict_state_delta" not in warning_event_names

    # The node-level execution_step is still emitted for visible nodes.
    assert len(sse_chunks) == 1
    sse_chunk, content = sse_chunks[0]
    assert sse_chunk.type == "execution_step"
    assert content == ""


@pytest.mark.asyncio
async def test_process_updates_chunk_handles_none_state_delta_for_invisible_node(
    streaming_service,
):
    """For a no-op on an internal/invisible node (e.g. ``compaction``), the
    debug log still fires but no execution_step is emitted (the UI does not
    track that node) — and crucially, no warning is logged either.
    """
    with patch("src.domains.agents.services.streaming.service.logger") as mock_logger:
        sse_chunks = streaming_service._process_updates_chunk(
            chunk={"compaction": None},
            accumulated_state={},
        )

    debug_event_names = [c.args[0] for c in mock_logger.debug.call_args_list if c.args]
    warning_event_names = [c.args[0] for c in mock_logger.warning.call_args_list if c.args]
    assert "updates_mode_node_no_op" in debug_event_names
    assert "updates_mode_non_dict_state_delta" not in warning_event_names
    # Invisible node → no SSE step emitted (existing behaviour preserved).
    assert sse_chunks == []


@pytest.mark.asyncio
async def test_process_updates_chunk_warns_on_truly_unexpected_state_delta(
    streaming_service,
):
    """Defence-in-depth: when state_delta is something other than dict/None
    (list, str, int, ...) — which would indicate a real LangGraph anomaly —
    the warning path is preserved.
    """
    with patch("src.domains.agents.services.streaming.service.logger") as mock_logger:
        sse_chunks = streaming_service._process_updates_chunk(
            chunk={"router": ["unexpected", "list"]},
            accumulated_state={},
        )

    warning_event_names = [c.args[0] for c in mock_logger.warning.call_args_list if c.args]
    assert "updates_mode_non_dict_state_delta" in warning_event_names
    # Visible node → step still emitted (resilience over silence).
    assert len(sse_chunks) == 1
    assert sse_chunks[0][0].type == "execution_step"


# ============================================================================
# "custom" stream_mode handler (Day 2 — Task 2.1)
# ============================================================================


class TestProcessCustomChunk:
    """Tests for _process_custom_chunk which forwards node-emitted custom events."""

    def test_forwards_well_formed_chunk_into_metadata(self, streaming_service):
        """step_type and step_label are folded into metadata; chunk type preserved."""
        chunk = {
            "type": "execution_step",
            "step_type": "compaction",
            "step_label": "compaction_start",
            "metadata": {"phase": "start", "estimated_duration_seconds": 30},
        }
        result = streaming_service._process_custom_chunk(chunk)

        assert len(result) == 1
        sse, content = result[0]
        assert content == ""
        assert sse.type == "execution_step"
        assert sse.metadata is not None
        assert sse.metadata["step_type"] == "compaction"
        assert sse.metadata["step_label"] == "compaction_start"
        assert sse.metadata["phase"] == "start"
        assert sse.metadata["estimated_duration_seconds"] == 30

    def test_drops_non_dict_chunk_with_warning(self, streaming_service):
        """A non-dict payload yields no SSE chunks (defensive)."""
        result = streaming_service._process_custom_chunk("not a dict")
        assert result == []
        result_list = streaming_service._process_custom_chunk(["also bad"])
        assert result_list == []

    def test_handles_missing_metadata(self, streaming_service):
        """Missing or None metadata becomes an empty dict; step_type/_label still folded."""
        chunk = {
            "type": "execution_step",
            "step_type": "compaction",
            "step_label": "compaction_done",
        }
        sse, _ = streaming_service._process_custom_chunk(chunk)[0]
        assert sse.metadata == {
            "step_type": "compaction",
            "step_label": "compaction_done",
        }

    def test_root_metadata_takes_precedence_over_folded_fields(self, streaming_service):
        """If metadata already has step_type, the root-level step_type does not overwrite it."""
        chunk = {
            "type": "execution_step",
            "step_type": "compaction",
            "metadata": {"step_type": "from_metadata"},
        }
        sse, _ = streaming_service._process_custom_chunk(chunk)[0]
        assert sse.metadata is not None
        assert sse.metadata["step_type"] == "from_metadata"


@pytest.mark.asyncio
async def test_format_token_chunk_coerces_gemini3_list_content(streaming_service):
    """Regression: Gemini 3.x list[dict] content is coerced to text.

    Before the fix, ``ChatStreamChunk(content=<list>)`` raised a Pydantic
    ValidationError that aborted the SSE stream ("Un problème est survenu...").
    """
    content = [{"type": "text", "text": "Bonjour", "index": 0}]
    chunk = streaming_service.format_token_chunk(content)
    assert chunk.type == "token"
    assert chunk.content == "Bonjour"


@pytest.mark.asyncio
async def test_process_messages_chunk_handles_gemini3_list_content(streaming_service):
    """Regression: the response-node token path must not crash on list content.

    Reproduces the production failure where Gemini 3.5 Flash streamed an
    AIMessageChunk whose ``content`` was ``[{'type': 'text', ...}]``.
    """
    mock_message = AIMessageChunk(content=[{"type": "text", "text": "Voici tes rdv", "index": 0}])
    message_tuple = (mock_message, {"langgraph_node": "response"})

    sse_chunks = streaming_service._process_messages_chunk(
        message_tuple,
        _state={},
        _first_token_time=None,
    )

    assert len(sse_chunks) == 1
    assert sse_chunks[0][0].type == "token"
    assert sse_chunks[0][0].content == "Voici tes rdv"


# =============================================================================
# Activated skill capture (user-facing badge — must NOT be debug-gated)
# =============================================================================


def _make_planning_result(skill_name: str) -> MagicMock:
    """Build a planning_result mock whose plan carries a skill_name."""
    planning_result = MagicMock()
    planning_result.plan.metadata = {"skill_name": skill_name}
    return planning_result


def test_capture_activated_skill_without_debug_panel(streaming_service):
    """Skill name is captured even when the debug panel is disabled.

    Regression test: the capture used to live inside _cache_debug_data,
    which early-returns when debug_panel_enabled=False — the skill badge
    never appeared for non-admin users.
    """
    assert streaming_service._debug_panel_enabled is False

    chunk = {
        "routing_history": [],
        "messages": [],
        "planning_result": _make_planning_result("meteo"),
        "query_intelligence": {"route_to": "planner"},
    }
    streaming_service._process_values_chunk(chunk, last_sent_routing=None)

    assert streaming_service.activated_skill_name == "meteo"


def test_capture_activated_skill_ignores_stale_planning_result(streaming_service):
    """A stale planning_result (current turn did not route through the
    planner) must not surface a stale skill badge."""
    chunk = {
        "routing_history": [],
        "messages": [],
        "planning_result": _make_planning_result("meteo"),
        "query_intelligence": {"route_to": "response"},
    }
    streaming_service._process_values_chunk(chunk, last_sent_routing=None)

    assert streaming_service.activated_skill_name is None


def test_resolve_activated_skill_name_route3_fallback(streaming_service):
    """Route 3 fallback: activate_skill_tool called directly by the response
    LLM (no planner) is detected from the current turn's messages."""
    messages = [
        HumanMessage(content="active la skill recette"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "activate_skill_tool", "args": {"name": "recette"}, "id": "call_1"}
            ],
        ),
    ]

    resolved = streaming_service.resolve_activated_skill_name({"messages": messages})

    assert resolved == "recette"
    assert streaming_service.activated_skill_name == "recette"


def test_resolve_activated_skill_name_scoped_to_current_turn(streaming_service):
    """Tool calls from PREVIOUS turns (before the last HumanMessage) must not
    surface a stale skill badge on the current turn."""
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "activate_skill_tool", "args": {"name": "old_skill"}, "id": "call_0"}
            ],
        ),
        HumanMessage(content="nouvelle question sans skill"),
        AIMessage(content="réponse simple sans tool call"),
    ]

    resolved = streaming_service.resolve_activated_skill_name({"messages": messages})

    assert resolved is None
    assert streaming_service.activated_skill_name is None


def test_capture_activated_skill_cleared_by_fresh_plan_without_skill(streaming_service):
    """A skill captured early in the turn from the STALE checkpoint plan must
    be cleared once the planner produces the fresh plan without skill_name.

    Sequence: turn N-1 activated skill X; turn N routes through the planner
    but activates no skill. Early values chunks still carry the previous
    turn's planning_result (checkpoint) with route_to already "planner".
    """
    # Early chunk: stale plan from previous turn (skill X), route already planner
    stale_chunk = {
        "routing_history": [],
        "messages": [],
        "planning_result": _make_planning_result("old_skill"),
        "query_intelligence": {"route_to": "planner"},
    }
    streaming_service._process_values_chunk(stale_chunk, last_sent_routing=None)
    assert streaming_service.activated_skill_name == "old_skill"

    # Planner completed: fresh plan WITHOUT skill_name replaces the stale one
    fresh_planning_result = MagicMock()
    fresh_planning_result.plan.metadata = {}
    fresh_chunk = {
        "routing_history": [],
        "messages": [],
        "planning_result": fresh_planning_result,
        "query_intelligence": {"route_to": "planner"},
    }
    streaming_service._process_values_chunk(fresh_chunk, last_sent_routing=None)

    assert streaming_service.activated_skill_name is None


def test_capture_activated_skill_ignored_in_react_mode(streaming_service):
    """ReAct mode never runs the planner: a leftover planning_result from a
    previous pipeline turn must not surface a skill badge (route_to cannot
    discriminate — it only knows planner/response). The legitimate ReAct
    badge comes from the Route 3 activate_skill_tool fallback."""
    chunk = {
        "routing_history": [],
        "messages": [],
        "execution_mode": "react",
        "planning_result": _make_planning_result("old_pipeline_skill"),
        "query_intelligence": {"route_to": "planner"},
    }
    streaming_service._process_values_chunk(chunk, last_sent_routing=None)

    assert streaming_service.activated_skill_name is None
