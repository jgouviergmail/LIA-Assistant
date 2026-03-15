"""
Unit tests for RAG Spaces retrieval service.

Tests the retrieve_rag_context function with mocked repositories,
embeddings, BM25 index, and Redis. Also tests RAGContext dataclass
methods (to_prompt_context, truncate_to_token_budget).

Phase: evolution — RAG Spaces (User Knowledge Documents)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.rag_spaces.retrieval import (
    RAGContext,
    RAGRetrievedChunk,
    retrieve_rag_context,
)

# ============================================================================
# RAGRetrievedChunk / RAGContext dataclass tests
# ============================================================================


class TestRAGRetrievedChunk:
    """Tests for the RAGRetrievedChunk dataclass."""

    @pytest.mark.unit
    def test_fields_stored_correctly(self) -> None:
        """All fields are stored and accessible."""
        chunk = RAGRetrievedChunk(
            content="Some text about AI.",
            score=0.85,
            space_name="Research",
            original_filename="paper.pdf",
            chunk_index=3,
        )

        assert chunk.content == "Some text about AI."
        assert chunk.score == 0.85
        assert chunk.space_name == "Research"
        assert chunk.original_filename == "paper.pdf"
        assert chunk.chunk_index == 3


class TestRAGContext:
    """Tests for RAGContext dataclass methods."""

    @pytest.fixture
    def sample_chunks(self) -> list[RAGRetrievedChunk]:
        """Create a list of sample retrieved chunks."""
        return [
            RAGRetrievedChunk(
                content="Machine learning is a subset of AI.",
                score=0.92,
                space_name="Research",
                original_filename="ml_intro.pdf",
                chunk_index=0,
            ),
            RAGRetrievedChunk(
                content="Deep learning uses neural networks.",
                score=0.87,
                space_name="Research",
                original_filename="dl_guide.pdf",
                chunk_index=1,
            ),
            RAGRetrievedChunk(
                content="Natural language processing handles text.",
                score=0.75,
                space_name="NLP Notes",
                original_filename="nlp.txt",
                chunk_index=0,
            ),
        ]

    # --- to_prompt_context ---

    @pytest.mark.unit
    def test_to_prompt_context_empty(self) -> None:
        """Empty context returns empty string."""
        ctx = RAGContext(chunks=[], spaces_searched=0, total_results=0)

        assert ctx.to_prompt_context() == ""

    @pytest.mark.unit
    def test_to_prompt_context_contains_header(self, sample_chunks) -> None:
        """Prompt context starts with the RAG header section."""
        ctx = RAGContext(chunks=sample_chunks, spaces_searched=2, total_results=3)

        result = ctx.to_prompt_context()

        assert "## USER KNOWLEDGE SPACES (RAG Documents)" in result
        assert "personal document spaces" in result
        assert "cite the source document" in result

    @pytest.mark.unit
    def test_to_prompt_context_contains_chunk_metadata(self, sample_chunks) -> None:
        """Each chunk includes space name and source filename."""
        ctx = RAGContext(chunks=sample_chunks, spaces_searched=2, total_results=3)

        result = ctx.to_prompt_context()

        assert "[Space: Research]" in result
        assert "[Space: NLP Notes]" in result
        assert "Source: ml_intro.pdf" in result
        assert "Source: dl_guide.pdf" in result
        assert "Source: nlp.txt" in result

    @pytest.mark.unit
    def test_to_prompt_context_contains_chunk_content(self, sample_chunks) -> None:
        """Chunk text content appears in the prompt output."""
        ctx = RAGContext(chunks=sample_chunks, spaces_searched=2, total_results=3)

        result = ctx.to_prompt_context()

        assert "Machine learning is a subset of AI." in result
        assert "Deep learning uses neural networks." in result
        assert "Natural language processing handles text." in result

    @pytest.mark.unit
    def test_to_prompt_context_chunks_separated(self, sample_chunks) -> None:
        """Chunks are separated by --- dividers."""
        ctx = RAGContext(chunks=sample_chunks, spaces_searched=2, total_results=3)

        result = ctx.to_prompt_context()

        assert result.count("---") == len(sample_chunks)

    # --- truncate_to_token_budget ---

    @pytest.mark.unit
    def test_truncate_empty_context(self) -> None:
        """Truncating empty context returns self."""
        ctx = RAGContext(chunks=[], spaces_searched=0, total_results=0)

        result = ctx.truncate_to_token_budget(100)

        assert result.chunks == []

    @pytest.mark.unit
    def test_truncate_keeps_chunks_within_budget(self, sample_chunks) -> None:
        """Large budget keeps all chunks."""
        ctx = RAGContext(chunks=sample_chunks, spaces_searched=2, total_results=3)

        result = ctx.truncate_to_token_budget(10000)

        assert len(result.chunks) == 3

    @pytest.mark.unit
    def test_truncate_removes_chunks_exceeding_budget(self) -> None:
        """Very small budget truncates to fewer chunks."""
        chunks = [
            RAGRetrievedChunk(
                content="A " * 200,  # ~200 tokens
                score=0.9,
                space_name="S",
                original_filename="a.txt",
                chunk_index=0,
            ),
            RAGRetrievedChunk(
                content="B " * 200,
                score=0.8,
                space_name="S",
                original_filename="b.txt",
                chunk_index=1,
            ),
        ]
        ctx = RAGContext(chunks=chunks, spaces_searched=1, total_results=2)

        # Budget of 100 tokens should not fit both chunks (each ~200 tokens + 50 overhead)
        result = ctx.truncate_to_token_budget(100)

        assert len(result.chunks) < 2

    @pytest.mark.unit
    def test_truncate_preserves_metadata(self, sample_chunks) -> None:
        """Truncated context preserves spaces_searched and total_results."""
        ctx = RAGContext(chunks=sample_chunks, spaces_searched=5, total_results=42)

        result = ctx.truncate_to_token_budget(10000)

        assert result.spaces_searched == 5
        assert result.total_results == 42

    @pytest.mark.unit
    def test_truncate_zero_budget_returns_no_chunks(self, sample_chunks) -> None:
        """A budget of zero tokens returns no chunks."""
        ctx = RAGContext(chunks=sample_chunks, spaces_searched=2, total_results=3)

        result = ctx.truncate_to_token_budget(0)

        assert len(result.chunks) == 0


# ============================================================================
# retrieve_rag_context — async function
# ============================================================================


class TestRetrieveRagContext:
    """Tests for the retrieve_rag_context async function."""

    @pytest.fixture
    def user_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_settings(self):
        """Patch settings with sensible defaults for retrieval."""
        with patch("src.domains.rag_spaces.retrieval.settings") as mock_s:
            mock_s.rag_spaces_retrieval_limit = 5
            mock_s.rag_spaces_retrieval_min_score = 0.3
            mock_s.rag_spaces_max_context_tokens = 2000
            mock_s.rag_spaces_hybrid_alpha = 0.7
            yield mock_s

    def _patch_metrics(self):
        """Context manager bundle for all Prometheus metric patches."""
        return (
            patch("src.domains.rag_spaces.retrieval.rag_retrieval_requests_total"),
            patch("src.domains.rag_spaces.retrieval.rag_retrieval_duration_seconds"),
            patch("src.domains.rag_spaces.retrieval.rag_retrieval_chunks_returned"),
            patch("src.domains.rag_spaces.retrieval.rag_retrieval_skipped_total"),
        )

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_no_active_spaces_returns_none(self, user_id, mock_db, mock_settings) -> None:
        """When user has no active spaces, returns None."""
        mock_space_repo = AsyncMock()
        mock_space_repo.get_active_for_user.return_value = []

        m1, m2, m3, m4 = self._patch_metrics()
        with (
            patch(
                "src.domains.rag_spaces.retrieval.RAGSpaceRepository",
                return_value=mock_space_repo,
            ),
            patch("src.domains.rag_spaces.retrieval.RAGChunkRepository"),
            m1,
            m2,
            m3,
            m4,
        ):
            result = await retrieve_rag_context(
                user_id=user_id,
                query="What is AI?",
                db=mock_db,
            )

        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reindex_in_progress_returns_none(self, user_id, mock_db, mock_settings) -> None:
        """When Redis reindex flag is set, returns None."""
        space = MagicMock()
        space.id = uuid4()
        space.name = "Research"

        mock_space_repo = AsyncMock()
        mock_space_repo.get_active_for_user.return_value = [space]

        mock_redis = AsyncMock()
        mock_redis.get.return_value = "1"  # Reindex flag set

        m1, m2, m3, m4 = self._patch_metrics()
        with (
            patch(
                "src.domains.rag_spaces.retrieval.RAGSpaceRepository",
                return_value=mock_space_repo,
            ),
            patch("src.domains.rag_spaces.retrieval.RAGChunkRepository"),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            m1,
            m2,
            m3,
            m4,
        ):
            result = await retrieve_rag_context(
                user_id=user_id,
                query="What is AI?",
                db=mock_db,
            )

        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_no_semantic_results_returns_empty_context(
        self, user_id, mock_db, mock_settings
    ) -> None:
        """When semantic search returns nothing, returns RAGContext with empty chunks."""
        space = MagicMock()
        space.id = uuid4()
        space.name = "Notes"

        mock_space_repo = AsyncMock()
        mock_space_repo.get_active_for_user.return_value = [space]

        mock_chunk_repo = AsyncMock()
        mock_chunk_repo.search_by_similarity.return_value = []

        mock_embeddings = AsyncMock()
        mock_embeddings.aembed_query.return_value = [0.1] * 10

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # No reindex flag

        m1, m2, m3, m4 = self._patch_metrics()
        with (
            patch(
                "src.domains.rag_spaces.retrieval.RAGSpaceRepository",
                return_value=mock_space_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.RAGChunkRepository",
                return_value=mock_chunk_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.get_rag_embeddings",
                return_value=mock_embeddings,
            ),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch("src.domains.rag_spaces.retrieval.set_embedding_context"),
            patch("src.domains.rag_spaces.retrieval.clear_embedding_context"),
            m1,
            m2,
            m3,
            m4,
        ):
            result = await retrieve_rag_context(
                user_id=user_id,
                query="Quantum physics",
                db=mock_db,
            )

        assert result is not None
        assert result.chunks == []
        assert result.spaces_searched == 1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_hybrid_search(self, user_id, mock_db, mock_settings) -> None:
        """Happy path: semantic + BM25 hybrid search returns scored chunks."""
        space_id = uuid4()
        chunk_id_1 = uuid4()
        chunk_id_2 = uuid4()

        space = MagicMock()
        space.id = space_id
        space.name = "Research"

        mock_space_repo = AsyncMock()
        mock_space_repo.get_active_for_user.return_value = [space]

        # Build mock chunks
        chunk_1 = MagicMock()
        chunk_1.id = chunk_id_1
        chunk_1.content = "AI is transforming industries."
        chunk_1.space_id = space_id
        chunk_1.chunk_index = 0
        chunk_1.metadata_ = {
            "original_filename": "ai_report.pdf",
            "content_type": "application/pdf",
        }

        chunk_2 = MagicMock()
        chunk_2.id = chunk_id_2
        chunk_2.content = "Machine learning enables predictions."
        chunk_2.space_id = space_id
        chunk_2.chunk_index = 1
        chunk_2.metadata_ = {
            "original_filename": "ml_book.pdf",
            "content_type": "application/pdf",
        }

        mock_chunk_repo = AsyncMock()
        # search_by_similarity returns (chunk, similarity_score) tuples
        mock_chunk_repo.search_by_similarity.return_value = [
            (chunk_1, 0.92),
            (chunk_2, 0.85),
        ]
        # BM25 corpus data
        mock_chunk_repo.get_corpus_for_spaces.return_value = [
            (chunk_id_1, "AI is transforming industries."),
            (chunk_id_2, "Machine learning enables predictions."),
        ]

        mock_embeddings = AsyncMock()
        mock_embeddings.aembed_query.return_value = [0.1] * 10

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        # BM25 mocks
        mock_bm25 = MagicMock()
        mock_bm25.get_scores.return_value = [0.8, 0.6]

        mock_bm25_manager = MagicMock()
        mock_bm25_manager.get_or_build_index.return_value = (
            mock_bm25,
            [str(chunk_id_1), str(chunk_id_2)],
        )

        m1, m2, m3, m4 = self._patch_metrics()
        with (
            patch(
                "src.domains.rag_spaces.retrieval.RAGSpaceRepository",
                return_value=mock_space_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.RAGChunkRepository",
                return_value=mock_chunk_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.get_rag_embeddings",
                return_value=mock_embeddings,
            ),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.get_bm25_manager",
                return_value=mock_bm25_manager,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.tokenize_text",
                return_value=["ai", "search"],
            ),
            patch("src.domains.rag_spaces.retrieval.set_embedding_context"),
            patch("src.domains.rag_spaces.retrieval.clear_embedding_context"),
            m1,
            m2,
            m3,
            m4,
        ):
            result = await retrieve_rag_context(
                user_id=user_id,
                query="Tell me about AI",
                db=mock_db,
            )

        assert result is not None
        assert len(result.chunks) > 0
        assert result.spaces_searched == 1

        # Verify chunks have correct structure
        first_chunk = result.chunks[0]
        assert first_chunk.space_name == "Research"
        assert first_chunk.score > 0
        assert isinstance(first_chunk.content, str)
        assert isinstance(first_chunk.original_filename, str)

        # Verify ordering by score (descending)
        for i in range(len(result.chunks) - 1):
            assert result.chunks[i].score >= result.chunks[i + 1].score

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_embedding_context_always_cleared(self, user_id, mock_db, mock_settings) -> None:
        """Embedding context is cleared even if an error occurs during retrieval."""
        space = MagicMock()
        space.id = uuid4()
        space.name = "Test"

        mock_space_repo = AsyncMock()
        mock_space_repo.get_active_for_user.return_value = [space]

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_embeddings = AsyncMock()
        mock_embeddings.aembed_query.side_effect = RuntimeError("API down")

        m1, m2, m3, m4 = self._patch_metrics()
        with (
            patch(
                "src.domains.rag_spaces.retrieval.RAGSpaceRepository",
                return_value=mock_space_repo,
            ),
            patch("src.domains.rag_spaces.retrieval.RAGChunkRepository"),
            patch(
                "src.domains.rag_spaces.retrieval.get_rag_embeddings",
                return_value=mock_embeddings,
            ),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch("src.domains.rag_spaces.retrieval.set_embedding_context"),
            patch(
                "src.domains.rag_spaces.retrieval.clear_embedding_context",
            ) as mock_clear,
            m1,
            m2,
            m3,
            m4,
        ):
            with pytest.raises(RuntimeError, match="API down"):
                await retrieve_rag_context(
                    user_id=user_id,
                    query="test",
                    db=mock_db,
                )

            mock_clear.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_bm25_failure_falls_back_to_semantic_only(
        self, user_id, mock_db, mock_settings
    ) -> None:
        """If BM25 scoring fails, retrieval still works with semantic-only scores."""
        space_id = uuid4()
        chunk_id = uuid4()

        space = MagicMock()
        space.id = space_id
        space.name = "Docs"

        mock_space_repo = AsyncMock()
        mock_space_repo.get_active_for_user.return_value = [space]

        chunk = MagicMock()
        chunk.id = chunk_id
        chunk.content = "Relevant content."
        chunk.space_id = space_id
        chunk.chunk_index = 0
        chunk.metadata_ = {"original_filename": "doc.txt"}

        mock_chunk_repo = AsyncMock()
        mock_chunk_repo.search_by_similarity.return_value = [(chunk, 0.9)]
        # BM25 corpus raises an exception
        mock_chunk_repo.get_corpus_for_spaces.side_effect = RuntimeError("BM25 error")

        mock_embeddings = AsyncMock()
        mock_embeddings.aembed_query.return_value = [0.1] * 10

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        m1, m2, m3, m4 = self._patch_metrics()
        with (
            patch(
                "src.domains.rag_spaces.retrieval.RAGSpaceRepository",
                return_value=mock_space_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.RAGChunkRepository",
                return_value=mock_chunk_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.get_rag_embeddings",
                return_value=mock_embeddings,
            ),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch("src.domains.rag_spaces.retrieval.set_embedding_context"),
            patch("src.domains.rag_spaces.retrieval.clear_embedding_context"),
            m1,
            m2,
            m3,
            m4,
        ):
            result = await retrieve_rag_context(
                user_id=user_id,
                query="test",
                db=mock_db,
            )

        assert result is not None
        # With alpha=0.7, semantic_score=0.9, bm25=0.0 → hybrid=0.63 > min_score 0.3
        assert len(result.chunks) == 1
        assert result.chunks[0].content == "Relevant content."

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_chunks_below_min_score_filtered_out(
        self, user_id, mock_db, mock_settings
    ) -> None:
        """Chunks with hybrid scores below min_score are excluded."""
        space_id = uuid4()

        space = MagicMock()
        space.id = space_id
        space.name = "S"

        mock_space_repo = AsyncMock()
        mock_space_repo.get_active_for_user.return_value = [space]

        # Create a chunk with very low semantic score
        chunk = MagicMock()
        chunk.id = uuid4()
        chunk.content = "Irrelevant."
        chunk.space_id = space_id
        chunk.chunk_index = 0
        chunk.metadata_ = {"original_filename": "junk.txt"}

        mock_chunk_repo = AsyncMock()
        # Very low similarity score
        mock_chunk_repo.search_by_similarity.return_value = [(chunk, 0.1)]
        mock_chunk_repo.get_corpus_for_spaces.return_value = []

        mock_embeddings = AsyncMock()
        mock_embeddings.aembed_query.return_value = [0.1] * 10

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        # Set a high min_score via settings
        mock_settings.rag_spaces_retrieval_min_score = 0.5

        m1, m2, m3, m4 = self._patch_metrics()
        with (
            patch(
                "src.domains.rag_spaces.retrieval.RAGSpaceRepository",
                return_value=mock_space_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.RAGChunkRepository",
                return_value=mock_chunk_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.get_rag_embeddings",
                return_value=mock_embeddings,
            ),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch("src.domains.rag_spaces.retrieval.set_embedding_context"),
            patch("src.domains.rag_spaces.retrieval.clear_embedding_context"),
            m1,
            m2,
            m3,
            m4,
        ):
            result = await retrieve_rag_context(
                user_id=user_id,
                query="test",
                db=mock_db,
            )

        assert result is not None
        # hybrid = 0.7 * 0.1 + 0.3 * 0.0 = 0.07 < min_score 0.5
        assert len(result.chunks) == 0

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_redis_unavailable_does_not_block_retrieval(
        self, user_id, mock_db, mock_settings
    ) -> None:
        """If Redis is unreachable, retrieval continues (reindex check skipped)."""
        space_id = uuid4()

        space = MagicMock()
        space.id = space_id
        space.name = "Fallback"

        mock_space_repo = AsyncMock()
        mock_space_repo.get_active_for_user.return_value = [space]

        chunk = MagicMock()
        chunk.id = uuid4()
        chunk.content = "Data despite Redis failure."
        chunk.space_id = space_id
        chunk.chunk_index = 0
        chunk.metadata_ = {"original_filename": "data.txt"}

        mock_chunk_repo = AsyncMock()
        mock_chunk_repo.search_by_similarity.return_value = [(chunk, 0.95)]
        mock_chunk_repo.get_corpus_for_spaces.return_value = []

        mock_embeddings = AsyncMock()
        mock_embeddings.aembed_query.return_value = [0.1] * 10

        m1, m2, m3, m4 = self._patch_metrics()
        with (
            patch(
                "src.domains.rag_spaces.retrieval.RAGSpaceRepository",
                return_value=mock_space_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.RAGChunkRepository",
                return_value=mock_chunk_repo,
            ),
            patch(
                "src.domains.rag_spaces.retrieval.get_rag_embeddings",
                return_value=mock_embeddings,
            ),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Redis down"),
            ),
            patch("src.domains.rag_spaces.retrieval.set_embedding_context"),
            patch("src.domains.rag_spaces.retrieval.clear_embedding_context"),
            m1,
            m2,
            m3,
            m4,
        ):
            result = await retrieve_rag_context(
                user_id=user_id,
                query="test",
                db=mock_db,
            )

        assert result is not None
        assert len(result.chunks) == 1
        assert result.chunks[0].content == "Data despite Redis failure."
