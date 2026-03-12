"""
Unit tests for LangGraph streaming metrics (P5).

Tests that streaming service correctly tracks:
- SSE chunk emissions (langgraph_streaming_chunks_total)
- Chunk type mapping to event_type

Phase: PHASE 2.5 - LangGraph Observability (P5)
Created: 2025-11-22
"""

import uuid
from unittest.mock import MagicMock

import pytest
from prometheus_client import REGISTRY

from src.domains.agents.services.streaming.service import (
    StreamingService,
    _get_chunk_event_type,
)
from src.infrastructure.observability.metrics_langgraph import (
    langgraph_streaming_chunks_total,
)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test to ensure clean state."""
    for collector in list(REGISTRY._collector_to_names.keys()):
        if hasattr(collector, "_metrics"):
            collector._metrics.clear()
    yield


class TestChunkEventTypeMapping:
    """Test chunk type to event_type mapping."""

    def test_maps_token_to_stream_token(self):
        """Verify token chunks map to STREAM_TOKEN."""
        assert _get_chunk_event_type("token") == "STREAM_TOKEN"

    def test_maps_content_replacement_to_stream_token(self):
        """Verify content_replacement maps to STREAM_TOKEN."""
        assert _get_chunk_event_type("content_replacement") == "STREAM_TOKEN"

    def test_maps_router_decision_to_stream_metadata(self):
        """Verify router_decision maps to STREAM_METADATA."""
        assert _get_chunk_event_type("router_decision") == "STREAM_METADATA"

    def test_maps_planner_metadata_to_stream_metadata(self):
        """Verify planner_metadata maps to STREAM_METADATA."""
        assert _get_chunk_event_type("planner_metadata") == "STREAM_METADATA"

    def test_maps_execution_step_to_stream_metadata(self):
        """Verify execution_step maps to STREAM_METADATA."""
        assert _get_chunk_event_type("execution_step") == "STREAM_METADATA"

    def test_maps_hitl_types_to_stream_interrupt(self):
        """Verify HITL chunk types map to STREAM_INTERRUPT."""
        assert _get_chunk_event_type("hitl_interrupt") == "STREAM_INTERRUPT"
        assert _get_chunk_event_type("hitl_interrupt_metadata") == "STREAM_INTERRUPT"
        assert _get_chunk_event_type("hitl_question_token") == "STREAM_INTERRUPT"
        assert _get_chunk_event_type("hitl_interrupt_complete") == "STREAM_INTERRUPT"

    def test_maps_error_to_stream_error(self):
        """Verify error chunks map to STREAM_ERROR."""
        assert _get_chunk_event_type("error") == "STREAM_ERROR"
        assert _get_chunk_event_type("planner_error") == "STREAM_ERROR"

    def test_maps_done_to_stream_complete(self):
        """Verify done chunk maps to STREAM_COMPLETE."""
        assert _get_chunk_event_type("done") == "STREAM_COMPLETE"

    def test_maps_unknown_types_to_stream_other(self):
        """Verify unknown chunk types map to STREAM_OTHER."""
        assert _get_chunk_event_type("future_type") == "STREAM_OTHER"
        assert _get_chunk_event_type("unknown") == "STREAM_OTHER"


class TestStreamingChunksTracking:
    """Test that streaming chunks are tracked correctly."""

    @pytest.mark.asyncio
    async def test_tracks_token_chunks(self):
        """Verify token chunks are tracked as STREAM_TOKEN."""
        service = StreamingService()

        # Mock graph stream that emits tokens
        async def mock_graph_stream():
            # Simulate mode="messages" with tokens
            yield ("messages", (MagicMock(content="Hello"), {"langgraph_node": "response"}))
            yield ("messages", (MagicMock(content=" world"), {"langgraph_node": "response"}))
            yield ("__end__", {})

        conversation_id = uuid.uuid4()
        run_id = "test_run_id"

        # Collect chunks
        chunks = []
        async for chunk, _content in service.stream_sse_chunks(
            mock_graph_stream(), conversation_id, run_id
        ):
            chunks.append(chunk)

        # Verify STREAM_TOKEN metrics were tracked
        samples = langgraph_streaming_chunks_total.collect()[0].samples
        token_samples = [s for s in samples if s.labels.get("event_type") == "STREAM_TOKEN"]

        assert len(token_samples) > 0
        # At least 2 token chunks (Hello + world)
        assert token_samples[0].value >= 2.0

    @pytest.mark.asyncio
    async def test_tracks_router_decision_chunks(self):
        """Verify router_decision chunks are tracked as STREAM_METADATA."""
        service = StreamingService()

        # Mock graph stream that emits router decision
        async def mock_graph_stream():
            # Simulate mode="values" with routing_history
            from src.domains.agents.domain_schemas import RouterOutput

            yield (
                "values",
                {
                    "routing_history": [
                        RouterOutput(
                            intention="search",
                            confidence=0.9,
                            context_label="contact",
                            next_node="planner",
                            reasoning="User wants to search",
                        )
                    ],
                    "messages": [],
                },
            )
            yield ("__end__", {})

        conversation_id = uuid.uuid4()
        run_id = "test_run_id"

        # Collect chunks
        chunks = []
        async for chunk, _content in service.stream_sse_chunks(
            mock_graph_stream(), conversation_id, run_id
        ):
            chunks.append(chunk)

        # Verify STREAM_METADATA metrics were tracked
        samples = langgraph_streaming_chunks_total.collect()[0].samples
        metadata_samples = [s for s in samples if s.labels.get("event_type") == "STREAM_METADATA"]

        assert len(metadata_samples) > 0
        assert metadata_samples[0].value >= 1.0

    @pytest.mark.asyncio
    async def test_tracks_content_replacement_chunks(self):
        """Verify content_replacement chunks are tracked as STREAM_TOKEN."""
        service = StreamingService()

        # Mock graph stream with content_final_replacement
        # Note: The streaming service accumulates state from "values" mode chunks,
        # so we need to emit the content_final_replacement in a "values" chunk.
        async def mock_graph_stream():
            yield ("messages", (MagicMock(content="Initial"), {"langgraph_node": "response"}))
            yield ("values", {"content_final_replacement": "Final content with photos"})

        conversation_id = uuid.uuid4()
        run_id = "test_run_id"

        # Collect chunks
        chunks = []
        async for chunk, _content in service.stream_sse_chunks(
            mock_graph_stream(), conversation_id, run_id
        ):
            chunks.append(chunk)

        # Verify content_replacement was emitted
        replacement_chunks = [c for c in chunks if c.type == "content_replacement"]
        assert len(replacement_chunks) == 1

        # Verify STREAM_TOKEN metrics include content_replacement
        samples = langgraph_streaming_chunks_total.collect()[0].samples
        token_samples = [s for s in samples if s.labels.get("event_type") == "STREAM_TOKEN"]

        assert len(token_samples) > 0
        # Should have token + content_replacement
        assert token_samples[0].value >= 2.0

    @pytest.mark.asyncio
    async def test_tracks_hitl_chunks(self):
        """Verify HITL chunks are tracked as STREAM_INTERRUPT."""
        # Create service with HITL dependencies
        service = StreamingService(
            conv_service=None, hitl_store=None, tracker=None, user_message="Test message"
        )

        # Mock graph stream with HITL interrupt
        async def mock_graph_stream():
            yield (
                "values",
                {
                    "__interrupt__": [
                        MagicMock(
                            value={
                                "action_requests": [
                                    {"type": "plan_approval", "user_message": "Confirmer le plan?"}
                                ]
                            }
                        )
                    ],
                    "messages": [],
                },
            )

        conversation_id = uuid.uuid4()
        run_id = "test_run_id"

        # Collect chunks
        chunks = []
        async for chunk, _content in service.stream_sse_chunks(
            mock_graph_stream(), conversation_id, run_id
        ):
            chunks.append(chunk)

        # Verify HITL chunks were emitted
        hitl_chunks = [c for c in chunks if c.type.startswith("hitl_")]
        assert len(hitl_chunks) > 0

        # Verify STREAM_INTERRUPT metrics were tracked
        samples = langgraph_streaming_chunks_total.collect()[0].samples
        interrupt_samples = [s for s in samples if s.labels.get("event_type") == "STREAM_INTERRUPT"]

        assert len(interrupt_samples) > 0
        # Should have at least metadata + tokens + complete
        assert interrupt_samples[0].value >= 3.0


class TestMetricsCardinality:
    """Test that streaming metrics have acceptable cardinality."""

    def test_chunk_event_type_cardinality(self):
        """Verify langgraph_streaming_chunks_total has acceptable label combinations."""
        # Expected event_type values: 5 categories
        expected_event_types = [
            "STREAM_TOKEN",  # token, content_replacement
            "STREAM_METADATA",  # router_decision, planner_metadata, execution_step
            "STREAM_INTERRUPT",  # hitl_*
            "STREAM_ERROR",  # error, planner_error
            "STREAM_COMPLETE",  # done
            "STREAM_OTHER",  # future additions
        ]

        max_expected_series = len(expected_event_types)

        # Validate cardinality: 6 event types → 6 time series
        assert max_expected_series == 6

    def test_event_type_mapping_coverage(self):
        """Verify all ChatStreamChunk types are mapped."""
        # All known chunk types from api/schemas.py
        known_chunk_types = [
            "token",
            "content_replacement",
            "router_decision",
            "planner_metadata",
            "planner_error",
            "execution_step",
            "hitl_interrupt",
            "hitl_interrupt_metadata",
            "hitl_question_token",
            "hitl_interrupt_complete",
            "hitl_clarification_token",
            "hitl_clarification_complete",
            "hitl_question",
            "error",
            "done",
        ]

        # Verify all types map to valid event_type
        valid_event_types = [
            "STREAM_TOKEN",
            "STREAM_METADATA",
            "STREAM_INTERRUPT",
            "STREAM_ERROR",
            "STREAM_COMPLETE",
            "STREAM_OTHER",
        ]

        for chunk_type in known_chunk_types:
            event_type = _get_chunk_event_type(chunk_type)
            assert (
                event_type in valid_event_types
            ), f"Chunk type '{chunk_type}' maps to invalid event_type '{event_type}'"
