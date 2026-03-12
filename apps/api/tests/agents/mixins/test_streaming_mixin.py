"""
Tests for StreamingMixin.

Tests the streaming methods extracted during Phase 2 refactoring.
Covers token buffering and enrichment after HITL resumption.

REFACTORED (Phase 8.4.1): Tests now match the new stream-first architecture.
The code uses _get_token_summary_best_effort() with fallback chain:
  1. In-memory tracker
  2. Redis cache
  3. Database query
  4. Zero fallback
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.api.mixins.streaming import StreamingMixin
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.chat.schemas import TokenSummaryDTO


class MockAgentService(StreamingMixin):
    """Mock service for testing mixin methods in isolation."""

    def __init__(self):
        """Initialize mock."""
        pass


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_service():
    """Create mock agent service with StreamingMixin."""
    return MockAgentService()


@pytest.fixture
def sample_chunks():
    """Sample stream chunks."""
    return [
        ChatStreamChunk(type="token", content="Hello"),
        ChatStreamChunk(type="token", content=" world"),
        ChatStreamChunk(type="token", content="Final message"),
    ]


@pytest.fixture
def sample_done_chunk():
    """Sample done chunk with original metadata."""
    return ChatStreamChunk(
        type="done",
        content="",
        metadata={
            "duration_ms": 1234,
            "node_count": 3,
        },
    )


@pytest.fixture
def mock_token_summary_dto():
    """
    Mock TokenSummaryDTO returned by _get_token_summary_best_effort.
    """
    return TokenSummaryDTO(
        tokens_in=1500,
        tokens_out=300,
        tokens_cache=500,
        cost_eur=0.025,
        message_count=2,
    )


# ============================================================================
# buffer_and_enrich_resumption_chunks Tests
# ============================================================================


@pytest.mark.asyncio
async def test_buffer_and_enrich_yields_all_chunks(
    mock_service, sample_chunks, sample_done_chunk, mock_token_summary_dto
):
    """Test that all chunks are streamed immediately and done chunk is enriched."""
    # Setup
    run_id = "test-run-123"
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    # Create async generator for graph stream
    async def mock_graph_stream():
        for chunk in sample_chunks:
            yield chunk
        yield sample_done_chunk

    # Mock _get_token_summary_best_effort
    with patch.object(
        mock_service,
        "_get_token_summary_best_effort",
        return_value=mock_token_summary_dto,
    ) as mock_get_summary:
        # Execute
        yielded_chunks = []
        async for chunk in mock_service.buffer_and_enrich_resumption_chunks(
            graph_stream=mock_graph_stream(),
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
        ):
            yielded_chunks.append(chunk)

        # Verify
        # Should yield: sample_chunks + enriched_done_chunk
        assert len(yielded_chunks) == len(sample_chunks) + 1

        # Verify chunks are in order
        for i, original_chunk in enumerate(sample_chunks):
            assert yielded_chunks[i].type == original_chunk.type
            assert yielded_chunks[i].content == original_chunk.content

        # Verify done chunk is enriched with DTO values
        done_chunk = yielded_chunks[-1]
        assert done_chunk.type == "done"
        assert done_chunk.metadata["tokens_in"] == 1500
        assert done_chunk.metadata["tokens_out"] == 300
        assert done_chunk.metadata["tokens_cache"] == 500
        assert done_chunk.metadata["cost_eur"] == 0.025
        assert done_chunk.metadata["message_count"] == 2

        # Verify _get_token_summary_best_effort was called correctly
        mock_get_summary.assert_called_once_with(
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            tracker=None,
        )


@pytest.mark.asyncio
async def test_buffer_preserves_original_done_metadata(
    mock_service, sample_chunks, sample_done_chunk, mock_token_summary_dto
):
    """Test that original done chunk metadata is preserved during enrichment."""
    # Setup
    run_id = "test-run"
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    async def mock_graph_stream():
        for chunk in sample_chunks:
            yield chunk
        yield sample_done_chunk

    with patch.object(
        mock_service,
        "_get_token_summary_best_effort",
        return_value=mock_token_summary_dto,
    ):
        # Execute
        yielded_chunks = []
        async for chunk in mock_service.buffer_and_enrich_resumption_chunks(
            graph_stream=mock_graph_stream(),
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
        ):
            yielded_chunks.append(chunk)

        # Verify
        done_chunk = yielded_chunks[-1]
        # Original metadata should be preserved
        assert done_chunk.metadata["duration_ms"] == 1234
        assert done_chunk.metadata["node_count"] == 3
        # DTO values should be added
        assert "tokens_in" in done_chunk.metadata
        assert "tokens_out" in done_chunk.metadata


@pytest.mark.asyncio
async def test_buffer_handles_missing_done_chunk(
    mock_service, sample_chunks, mock_token_summary_dto
):
    """Test handling when no done chunk is present in stream."""
    # Setup
    run_id = "test-run"
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    # Stream without done chunk
    async def mock_graph_stream():
        for chunk in sample_chunks:
            yield chunk

    with patch.object(
        mock_service,
        "_get_token_summary_best_effort",
        return_value=mock_token_summary_dto,
    ):
        # Execute
        yielded_chunks = []
        async for chunk in mock_service.buffer_and_enrich_resumption_chunks(
            graph_stream=mock_graph_stream(),
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
        ):
            yielded_chunks.append(chunk)

        # Verify: Should still get sample chunks + enriched done (even without original)
        assert len(yielded_chunks) == len(sample_chunks) + 1
        # Done chunk should be created with DTO metadata only
        done_chunk = yielded_chunks[-1]
        assert done_chunk.type == "done"
        assert done_chunk.metadata["tokens_in"] == 1500


@pytest.mark.asyncio
async def test_buffer_handles_db_query_failure(mock_service, sample_chunks, sample_done_chunk):
    """Test graceful handling when token summary fails (returns zeros)."""
    # Setup
    run_id = "test-run"
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    async def mock_graph_stream():
        for chunk in sample_chunks:
            yield chunk
        yield sample_done_chunk

    # Return zero DTO (simulating all fallbacks failed)
    with patch.object(
        mock_service,
        "_get_token_summary_best_effort",
        return_value=TokenSummaryDTO.zero(),
    ):
        # Execute - should not raise
        yielded_chunks = []
        async for chunk in mock_service.buffer_and_enrich_resumption_chunks(
            graph_stream=mock_graph_stream(),
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
        ):
            yielded_chunks.append(chunk)

        # Verify done chunk has zero values (graceful degradation)
        done_chunk = yielded_chunks[-1]
        assert done_chunk.type == "done"
        assert done_chunk.metadata["tokens_in"] == 0
        assert done_chunk.metadata["tokens_out"] == 0


@pytest.mark.asyncio
async def test_buffer_with_empty_stream(mock_service, mock_token_summary_dto):
    """Test handling of completely empty stream."""
    # Setup
    run_id = "test-run"
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    async def mock_graph_stream():
        # Empty stream
        if False:
            yield

    with patch.object(
        mock_service,
        "_get_token_summary_best_effort",
        return_value=mock_token_summary_dto,
    ):
        # Execute
        yielded_chunks = []
        async for chunk in mock_service.buffer_and_enrich_resumption_chunks(
            graph_stream=mock_graph_stream(),
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
        ):
            yielded_chunks.append(chunk)

        # Verify: Should still yield enriched done chunk
        assert len(yielded_chunks) == 1
        assert yielded_chunks[0].type == "done"


@pytest.mark.asyncio
async def test_buffer_passes_tracker_to_best_effort(
    mock_service, sample_chunks, sample_done_chunk, mock_token_summary_dto
):
    """Test that tracker parameter is passed to _get_token_summary_best_effort."""
    # Setup
    run_id = "test-run"
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    mock_tracker = MagicMock()

    async def mock_graph_stream():
        for chunk in sample_chunks:
            yield chunk
        yield sample_done_chunk

    with patch.object(
        mock_service,
        "_get_token_summary_best_effort",
        return_value=mock_token_summary_dto,
    ) as mock_get_summary:
        # Execute with tracker
        yielded_chunks = []
        async for chunk in mock_service.buffer_and_enrich_resumption_chunks(
            graph_stream=mock_graph_stream(),
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            tracker=mock_tracker,
        ):
            yielded_chunks.append(chunk)

        # Verify tracker was passed
        mock_get_summary.assert_called_once_with(
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            tracker=mock_tracker,
        )


@pytest.mark.asyncio
async def test_buffer_enrichment_overwrites_with_dto_values(
    mock_service, sample_chunks, mock_token_summary_dto
):
    """Test that DTO values overwrite original done chunk metadata."""
    # Setup
    run_id = "test-run"
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    # Done chunk with conflicting tokens_in value
    conflicting_done_chunk = ChatStreamChunk(
        type="done",
        content="",
        metadata={
            "tokens_in": 999,  # Should be overwritten
            "original_field": "preserved",
        },
    )

    async def mock_graph_stream():
        for chunk in sample_chunks:
            yield chunk
        yield conflicting_done_chunk

    with patch.object(
        mock_service,
        "_get_token_summary_best_effort",
        return_value=mock_token_summary_dto,
    ):
        # Execute
        yielded_chunks = []
        async for chunk in mock_service.buffer_and_enrich_resumption_chunks(
            graph_stream=mock_graph_stream(),
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
        ):
            yielded_chunks.append(chunk)

        # Verify DTO values overwrite, but other fields preserved
        done_chunk = yielded_chunks[-1]
        assert done_chunk.metadata["tokens_in"] == 1500  # DTO value, not 999
        assert done_chunk.metadata["original_field"] == "preserved"
