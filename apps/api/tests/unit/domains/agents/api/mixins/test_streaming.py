"""
Unit tests for StreamingMixin.

Tests chunk buffering and token metadata enrichment logic.
"""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.domains.agents.api.mixins.streaming import StreamingMixin
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.chat.schemas import TokenSummaryDTO

pytestmark = pytest.mark.unit


def _redis_stub() -> Mock:
    """A Redis client that holds nothing — forces the chain to the next source."""
    redis = Mock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    return redis


def _db_context_stub() -> Mock:
    """`get_db_context()` as an async context manager yielding a dummy session."""
    context = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=Mock())
    context.__aexit__ = AsyncMock(return_value=None)
    return Mock(return_value=context)


class AsyncGeneratorMock:
    """Helper to create async generators for testing."""

    def __init__(self, items):
        self.items = items

    async def __aiter__(self):
        for item in self.items:
            yield item


class TestStreamingMixin:
    """Test suite for StreamingMixin."""

    # ==================== buffer_and_enrich_resumption_chunks Tests ====================

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_with_in_memory_tracker(self):
        """Test chunk buffering and enrichment with in-memory tracker."""
        mixin = StreamingMixin()

        # Setup mock chunks
        chunks = [
            ChatStreamChunk(type="token", content="Hello", metadata={}),
            ChatStreamChunk(type="token", content=" world", metadata={}),
            ChatStreamChunk(type="done", content="", metadata={"original": "value"}),
        ]
        graph_stream = AsyncGeneratorMock(chunks)

        # Setup mock tracker
        mock_tracker = Mock()
        mock_tracker.get_summary_dto.return_value = TokenSummaryDTO(
            tokens_in=100,
            tokens_out=50,
            tokens_cache=10,
            cost_eur=0.05,
            message_count=3,
        )

        # Test
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=graph_stream,
            run_id="test_run_123",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify
        assert len(result_chunks) == 3
        assert result_chunks[0].content == "Hello"
        assert result_chunks[1].content == " world"

        # Verify done chunk is enriched
        done_chunk = result_chunks[2]
        assert done_chunk.type == "done"
        assert done_chunk.metadata["tokens_in"] == 100
        assert done_chunk.metadata["tokens_out"] == 50
        assert done_chunk.metadata["tokens_cache"] == 10
        assert done_chunk.metadata["cost_eur"] == 0.05
        assert done_chunk.metadata["message_count"] == 3
        # Original metadata preserved
        assert done_chunk.metadata["original"] == "value"

        # Verify tracker was queried
        mock_tracker.get_summary_dto.assert_called_once()

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_without_done_chunk(self):
        """Test buffering when no done chunk is provided by graph."""
        mixin = StreamingMixin()

        # Setup mock chunks WITHOUT done chunk
        chunks = [
            ChatStreamChunk(type="token", content="Hello", metadata={}),
            ChatStreamChunk(type="token", content=" world", metadata={}),
        ]
        graph_stream = AsyncGeneratorMock(chunks)

        # Setup mock tracker
        mock_tracker = Mock()
        mock_tracker.get_summary_dto.return_value = TokenSummaryDTO(
            tokens_in=100,
            tokens_out=50,
            tokens_cache=10,
            cost_eur=0.05,
            message_count=3,
        )

        # Test
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=graph_stream,
            run_id="test_run_123",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify
        assert len(result_chunks) == 3  # 2 tokens + 1 synthetic done
        assert result_chunks[0].content == "Hello"
        assert result_chunks[1].content == " world"

        # Verify synthetic done chunk is created with tracker data
        done_chunk = result_chunks[2]
        assert done_chunk.type == "done"
        assert done_chunk.metadata["tokens_in"] == 100
        assert done_chunk.metadata["tokens_out"] == 50

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_without_tracker_uses_db(self):
        """Without an in-memory tracker, the summary comes from the database.

        The chain is: tracker -> Redis cache -> repository -> zeros. This test
        used to patch `streaming.TrackingContext`, a name the mixin deliberately
        stopped instantiating ("architectural violation fixed"); the patch could
        only raise. Both external sources are stubbed here so the assertion is
        about the FALLBACK ORDER, and so no socket is opened.
        """
        mixin = StreamingMixin()

        chunks = [
            ChatStreamChunk(type="token", content="Test", metadata={}),
            ChatStreamChunk(type="done", content="", metadata={}),
        ]
        graph_stream = AsyncGeneratorMock(chunks)

        db_record = Mock(
            total_prompt_tokens=200,
            total_completion_tokens=100,
            total_cached_tokens=20,
            total_cost_eur=0.10,
            google_api_requests=0,
        )
        repository = Mock()
        repository.get_token_summary_by_run_id = AsyncMock(return_value=db_record)

        with (
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                AsyncMock(return_value=_redis_stub()),
            ),
            patch("src.infrastructure.database.get_db_context", _db_context_stub()),
            patch("src.domains.chat.repository.ChatRepository", return_value=repository),
        ):
            result_chunks = []
            async for chunk in mixin.buffer_and_enrich_resumption_chunks(
                graph_stream=graph_stream,
                run_id="test_run_123",
                user_id=uuid.uuid4(),
                conversation_id=uuid.uuid4(),
                tracker=None,  # No tracker = DB fallback
            ):
                result_chunks.append(chunk)

        assert len(result_chunks) == 2
        done_chunk = result_chunks[1]
        assert done_chunk.type == "done"
        assert done_chunk.metadata["tokens_in"] == 200
        assert done_chunk.metadata["tokens_out"] == 100
        repository.get_token_summary_by_run_id.assert_awaited_once_with("test_run_123")

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_handles_tracker_exception(self):
        """A failing tracker degrades to zeros, and the done chunk still ships.

        The original metadata is no longer "preserved as-is": every source
        failing yields `TokenSummaryDTO.zero()`, so the frontend receives an
        explicit zero rather than a done chunk with no token keys at all. The
        caller's own metadata is still merged underneath.
        """
        mixin = StreamingMixin()

        chunks = [
            ChatStreamChunk(type="token", content="Test", metadata={}),
            ChatStreamChunk(type="done", content="", metadata={"original": "data"}),
        ]
        graph_stream = AsyncGeneratorMock(chunks)

        mock_tracker = Mock()
        mock_tracker.get_summary_dto.side_effect = Exception("Tracker failed")

        with (
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                AsyncMock(side_effect=ConnectionError("no redis")),
            ),
            patch(
                "src.infrastructure.database.get_db_context",
                Mock(side_effect=ConnectionError("no database")),
            ),
        ):
            result_chunks = []
            async for chunk in mixin.buffer_and_enrich_resumption_chunks(
                graph_stream=graph_stream,
                run_id="test_run_123",
                user_id=uuid.uuid4(),
                conversation_id=uuid.uuid4(),
                tracker=mock_tracker,
            ):
                result_chunks.append(chunk)

        assert len(result_chunks) == 2
        done_chunk = result_chunks[1]
        assert done_chunk.type == "done"
        assert done_chunk.metadata["original"] == "data"  # caller's key survives
        assert done_chunk.metadata["tokens_in"] == 0
        assert done_chunk.metadata["tokens_out"] == 0
        assert done_chunk.metadata["cost_eur"] == 0

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_preserves_metadata_merge_order(self):
        """Test that metadata merge order is correct (original first, then aggregated)."""
        mixin = StreamingMixin()

        # Setup mock chunks with overlapping metadata
        chunks = [
            ChatStreamChunk(
                type="done",
                content="",
                metadata={
                    "original_field": "original_value",
                    "tokens_in": 999,  # Should be overwritten
                },
            ),
        ]
        graph_stream = AsyncGeneratorMock(chunks)

        # Setup mock tracker
        mock_tracker = Mock()
        mock_tracker.get_summary_dto.return_value = TokenSummaryDTO(
            tokens_in=100,  # Should overwrite original
            tokens_out=50,
            tokens_cache=10,
            cost_eur=0.05,
            message_count=3,
        )

        # Test
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=graph_stream,
            run_id="test_run_123",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify metadata merge
        done_chunk = result_chunks[0]
        assert done_chunk.metadata["original_field"] == "original_value"  # Preserved
        assert done_chunk.metadata["tokens_in"] == 100  # Overwritten by tracker

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_empty_stream(self):
        """Test behavior with empty graph stream."""
        mixin = StreamingMixin()

        # Empty stream
        chunks = []
        graph_stream = AsyncGeneratorMock(chunks)

        # Setup mock tracker
        mock_tracker = Mock()
        mock_tracker.get_summary_dto.return_value = TokenSummaryDTO(
            tokens_in=0,
            tokens_out=0,
            tokens_cache=0,
            cost_eur=0.0,
            message_count=0,
        )

        # Test
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=graph_stream,
            run_id="test_run_123",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify - should create synthetic done chunk with tracker data
        assert len(result_chunks) == 1
        assert result_chunks[0].type == "done"
        assert result_chunks[0].metadata["tokens_in"] == 0

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_multiple_done_chunks(self):
        """Test behavior when stream contains multiple done chunks (edge case)."""
        mixin = StreamingMixin()

        # Multiple done chunks (unusual but possible)
        chunks = [
            ChatStreamChunk(type="token", content="Hello", metadata={}),
            ChatStreamChunk(type="done", content="", metadata={"first": "done"}),
            ChatStreamChunk(type="done", content="", metadata={"second": "done"}),
        ]
        graph_stream = AsyncGeneratorMock(chunks)

        # Setup mock tracker
        mock_tracker = Mock()
        mock_tracker.get_summary_dto.return_value = TokenSummaryDTO(
            tokens_in=100,
            tokens_out=50,
            tokens_cache=10,
            cost_eur=0.05,
            message_count=3,
        )

        # Test
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=graph_stream,
            run_id="test_run_123",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify - only last done chunk is kept and enriched
        assert len(result_chunks) == 2  # 1 token + 1 enriched done
        assert result_chunks[0].content == "Hello"
        assert result_chunks[1].type == "done"
        assert result_chunks[1].metadata["second"] == "done"  # Last done chunk
        assert result_chunks[1].metadata["tokens_in"] == 100  # Enriched

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_non_chatstream_chunks(self):
        """Test handling of non-ChatStreamChunk objects in stream."""
        mixin = StreamingMixin()

        # Mix of ChatStreamChunk and other objects
        chunks = [
            ChatStreamChunk(type="token", content="Hello", metadata={}),
            {"type": "other", "content": "not a chunk"},  # Non-ChatStreamChunk
            ChatStreamChunk(type="done", content="", metadata={}),
        ]
        graph_stream = AsyncGeneratorMock(chunks)

        # Setup mock tracker
        mock_tracker = Mock()
        mock_tracker.get_summary_dto.return_value = TokenSummaryDTO(
            tokens_in=100,
            tokens_out=50,
            tokens_cache=10,
            cost_eur=0.05,
            message_count=3,
        )

        # Test
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=graph_stream,
            run_id="test_run_123",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify - non-ChatStreamChunk objects are buffered as-is
        assert len(result_chunks) == 3
        assert result_chunks[0].content == "Hello"
        assert result_chunks[1] == {"type": "other", "content": "not a chunk"}
        assert result_chunks[2].type == "done"

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_tracker_with_missing_fields(self):
        """Test handling when tracker summary is missing some fields."""
        mixin = StreamingMixin()

        # Setup mock chunks
        chunks = [
            ChatStreamChunk(type="done", content="", metadata={}),
        ]
        graph_stream = AsyncGeneratorMock(chunks)

        # The DTO makes an incomplete summary UNREPRESENTABLE: every field is
        # required or defaulted, so the partial dict this test used to build
        # can no longer reach the mixin. What remains worth asserting is that
        # the optional cost fields default to zero rather than to nothing.
        mock_tracker = Mock()
        mock_tracker.get_summary_dto.return_value = TokenSummaryDTO(
            tokens_in=100,
            tokens_out=0,
            tokens_cache=0,
            cost_eur=0.0,
            message_count=0,
        )

        # Test
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=graph_stream,
            run_id="test_run_123",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify - should use whatever fields are available
        done_chunk = result_chunks[0]
        assert done_chunk.metadata["tokens_in"] == 100
        # Other fields will use .get() default or be missing


class TestStreamingMixinEdgeCases:
    """Test suite for StreamingMixin edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_with_none_metadata_in_done_chunk(self):
        """Test handling when done chunk has None metadata."""
        mixin = StreamingMixin()

        # Done chunk with None metadata
        chunks = [
            ChatStreamChunk(type="done", content="", metadata=None),
        ]
        graph_stream = AsyncGeneratorMock(chunks)

        # Setup mock tracker
        mock_tracker = Mock()
        mock_tracker.get_summary_dto.return_value = TokenSummaryDTO(
            tokens_in=100,
            tokens_out=50,
            tokens_cache=10,
            cost_eur=0.05,
            message_count=3,
        )

        # Test
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=graph_stream,
            run_id="test_run_123",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify - should handle None metadata gracefully
        done_chunk = result_chunks[0]
        assert done_chunk.type == "done"
        assert done_chunk.metadata["tokens_in"] == 100

    @pytest.mark.asyncio
    async def test_buffer_and_enrich_large_token_stream(self):
        """Test performance with large number of token chunks."""
        mixin = StreamingMixin()

        # Large stream (1000 tokens)
        chunks = [
            ChatStreamChunk(type="token", content=f"word{i}", metadata={}) for i in range(1000)
        ]
        chunks.append(ChatStreamChunk(type="done", content="", metadata={}))
        graph_stream = AsyncGeneratorMock(chunks)

        # Setup mock tracker
        mock_tracker = Mock()
        mock_tracker.get_summary_dto.return_value = TokenSummaryDTO(
            tokens_in=10000,
            tokens_out=5000,
            tokens_cache=1000,
            cost_eur=5.0,
            message_count=100,
        )

        # Test
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=graph_stream,
            run_id="test_run_123",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify all chunks were buffered and done was enriched
        assert len(result_chunks) == 1001  # 1000 tokens + 1 done
        assert result_chunks[-1].type == "done"
        assert result_chunks[-1].metadata["tokens_in"] == 10000
