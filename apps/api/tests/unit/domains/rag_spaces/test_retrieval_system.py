"""Tests for system RAG retrieval (system_only mode)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.rag_spaces.retrieval import RAGContext, retrieve_rag_context

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_space():
    """Create a mock active system space."""
    space = MagicMock()
    space.id = uuid.uuid4()
    space.name = "lia-faq"
    space.is_system = True
    space.is_active = True
    return space


# ============================================================================
# TestRetrieveSystemContext
# ============================================================================


@pytest.mark.unit
class TestRetrieveSystemContext:
    """Tests for retrieve_rag_context with system_only=True."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_system_spaces(self, mock_db) -> None:
        """Should return None when no active system spaces exist."""
        with (
            patch("src.domains.rag_spaces.retrieval.RAGSpaceRepository") as mock_space_repo_cls,
            patch("src.domains.rag_spaces.retrieval.RAGChunkRepository"),
        ):
            mock_space_repo = AsyncMock()
            mock_space_repo.get_active_system_spaces = AsyncMock(return_value=[])
            mock_space_repo_cls.return_value = mock_space_repo

            result = await retrieve_rag_context(
                user_id=None,
                query="What can you do?",
                db=mock_db,
                system_only=True,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_raises_when_user_id_none_without_system_only(self, mock_db) -> None:
        """Should raise ValueError when user_id=None and system_only=False."""
        with (
            patch("src.domains.rag_spaces.retrieval.RAGSpaceRepository") as mock_cls,
            patch("src.domains.rag_spaces.retrieval.RAGChunkRepository"),
        ):
            mock_repo = AsyncMock()
            mock_cls.return_value = mock_repo

            with pytest.raises(ValueError, match="user_id is required"):
                await retrieve_rag_context(
                    user_id=None,
                    query="test",
                    db=mock_db,
                    system_only=False,
                )


# ============================================================================
# TestRAGContextType
# ============================================================================


@pytest.mark.unit
class TestRAGContextType:
    """Tests for RAGContext.context_type and to_prompt_context."""

    def test_system_context_header(self) -> None:
        """System context should have APP KNOWLEDGE header."""
        from src.domains.rag_spaces.retrieval import RAGRetrievedChunk

        ctx = RAGContext(
            chunks=[
                RAGRetrievedChunk(
                    content="Q: What is LIA?\nA: A personal assistant.",
                    score=0.95,
                    space_name="lia-faq",
                    original_filename="01_getting_started.md",
                    chunk_index=0,
                )
            ],
            spaces_searched=1,
            total_results=1,
            context_type="system",
        )

        prompt = ctx.to_prompt_context()
        assert "APP KNOWLEDGE" in prompt
        assert "FAQ" in prompt
        assert "LIA" in prompt

    def test_user_context_header(self) -> None:
        """User context should have USER KNOWLEDGE SPACES header."""
        from src.domains.rag_spaces.retrieval import RAGRetrievedChunk

        ctx = RAGContext(
            chunks=[
                RAGRetrievedChunk(
                    content="Some user document content.",
                    score=0.9,
                    space_name="My Notes",
                    original_filename="notes.pdf",
                    chunk_index=0,
                )
            ],
            spaces_searched=1,
            total_results=1,
            context_type="user",
        )

        prompt = ctx.to_prompt_context()
        assert "USER KNOWLEDGE SPACES" in prompt
        assert "personal document" in prompt

    def test_truncate_preserves_context_type(self) -> None:
        """Truncation should preserve context_type."""
        ctx = RAGContext(
            chunks=[],
            spaces_searched=1,
            total_results=0,
            context_type="system",
        )

        truncated = ctx.truncate_to_token_budget(1000)
        assert truncated.context_type == "system"
