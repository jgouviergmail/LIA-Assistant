"""Tests for SystemSpaceIndexer — markdown parsing, hash computation, staleness."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.rag_spaces.system_indexer import SystemSpaceIndexer

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    return AsyncMock()


@pytest.fixture
def indexer(mock_db):
    """Create indexer with mocked dependencies."""
    with patch("src.domains.rag_spaces.system_indexer.RAGSpaceService"):
        with patch("src.domains.rag_spaces.system_indexer.RAGDocumentRepository"):
            with patch("src.domains.rag_spaces.system_indexer.RAGChunkRepository"):
                idx = SystemSpaceIndexer(mock_db)
                idx.service = AsyncMock()
                idx.doc_repo = AsyncMock()
                idx.chunk_repo = AsyncMock()
                return idx


@pytest.fixture
def sample_md_file(tmp_path):
    """Create a sample FAQ markdown file."""
    content = """# Getting Started

## What is LIA?
LIA is a personal AI assistant.

## How do I start?
Click on Chat in the left menu.
Type your message.
"""
    md_file = tmp_path / "01_getting_started.md"
    md_file.write_text(content, encoding="utf-8")
    return md_file


@pytest.fixture
def knowledge_dir(tmp_path):
    """Create a knowledge directory with multiple files."""
    (tmp_path / "01_intro.md").write_text(
        "# Intro\n\n## What is LIA?\nA personal assistant.\n\n## How to start?\nJust talk.\n",
        encoding="utf-8",
    )
    (tmp_path / "02_features.md").write_text(
        "# Features\n\n## Email support?\nYes, Gmail and Outlook.\n",
        encoding="utf-8",
    )
    return tmp_path


# ============================================================================
# TestParseFaqMarkdown
# ============================================================================


@pytest.mark.unit
class TestParseFaqMarkdown:
    """Tests for parse_faq_markdown method."""

    def test_parses_questions_and_answers(self, indexer, sample_md_file) -> None:
        """Should extract Q/A pairs from ## headings."""
        chunks = indexer.parse_faq_markdown(sample_md_file)

        assert len(chunks) == 2
        assert chunks[0]["question"] == "What is LIA?"
        assert "personal AI assistant" in chunks[0]["answer"]
        assert chunks[1]["question"] == "How do I start?"
        assert "Click on Chat" in chunks[1]["answer"]

    def test_extracts_section_title(self, indexer, sample_md_file) -> None:
        """Should use # heading as section title."""
        chunks = indexer.parse_faq_markdown(sample_md_file)

        assert chunks[0]["section"] == "Getting Started"
        assert chunks[1]["section"] == "Getting Started"

    def test_metadata_contains_required_fields(self, indexer, sample_md_file) -> None:
        """Should include section, source, question, file in metadata."""
        chunks = indexer.parse_faq_markdown(sample_md_file)

        meta = chunks[0]["metadata"]
        assert meta["section"] == "Getting Started"
        assert meta["source"] == "faq"
        assert meta["question"] == "What is LIA?"
        assert meta["file"] == "01_getting_started.md"

    def test_empty_file_returns_empty(self, indexer, tmp_path) -> None:
        """Should return empty list for file without ## headings."""
        empty = tmp_path / "empty.md"
        empty.write_text("# Just a title\nNo questions here.\n", encoding="utf-8")

        chunks = indexer.parse_faq_markdown(empty)
        assert chunks == []

    def test_skips_empty_answers(self, indexer, tmp_path) -> None:
        """Should skip Q/A where answer is empty."""
        md = tmp_path / "sparse.md"
        md.write_text(
            "# Test\n\n## Empty question?\n\n## Real question?\nReal answer.\n", encoding="utf-8"
        )

        chunks = indexer.parse_faq_markdown(md)
        assert len(chunks) == 1
        assert chunks[0]["question"] == "Real question?"

    def test_multiline_answer(self, indexer, tmp_path) -> None:
        """Should preserve multiline answers."""
        md = tmp_path / "multi.md"
        md.write_text(
            "# Test\n\n## How?\nStep 1: Do this.\nStep 2: Do that.\nStep 3: Done.\n",
            encoding="utf-8",
        )

        chunks = indexer.parse_faq_markdown(md)
        assert len(chunks) == 1
        assert "Step 1" in chunks[0]["answer"]
        assert "Step 3" in chunks[0]["answer"]


# ============================================================================
# TestComputeContentHash
# ============================================================================


@pytest.mark.unit
class TestComputeContentHash:
    """Tests for compute_content_hash method."""

    def test_deterministic_hash(self, indexer, knowledge_dir) -> None:
        """Same content should produce same hash."""
        hash1 = indexer.compute_content_hash(knowledge_dir)
        hash2 = indexer.compute_content_hash(knowledge_dir)
        assert hash1 == hash2

    def test_hash_changes_on_content_change(self, indexer, knowledge_dir) -> None:
        """Modified content should produce different hash."""
        hash1 = indexer.compute_content_hash(knowledge_dir)

        (knowledge_dir / "01_intro.md").write_text("# Changed\n\n## New?\nNew content.\n")

        hash2 = indexer.compute_content_hash(knowledge_dir)
        assert hash1 != hash2

    def test_hash_is_sha256(self, indexer, knowledge_dir) -> None:
        """Hash should be 64 characters (SHA-256 hex digest)."""
        h = indexer.compute_content_hash(knowledge_dir)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_directory(self, indexer, tmp_path) -> None:
        """Empty directory should still produce a valid hash."""
        h = indexer.compute_content_hash(tmp_path)
        assert len(h) == 64


# ============================================================================
# TestCheckStaleness
# ============================================================================


@pytest.mark.unit
class TestCheckStaleness:
    """Tests for check_staleness method."""

    @pytest.mark.asyncio
    async def test_stale_when_hash_differs(self, indexer, knowledge_dir) -> None:
        """Should report stale when stored hash differs from current."""
        space = MagicMock()
        space.content_hash = "old_hash_value"
        indexer.service.space_repo.get_system_space_by_name = AsyncMock(return_value=space)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=knowledge_dir):
            result = await indexer.check_staleness("lia-faq")

        assert result["is_stale"] is True
        assert result["stored_hash"] == "old_hash_value"
        assert len(result["current_hash"]) == 64

    @pytest.mark.asyncio
    async def test_not_stale_when_hash_matches(self, indexer, knowledge_dir) -> None:
        """Should report not stale when hashes match."""
        current_hash = indexer.compute_content_hash(knowledge_dir)
        space = MagicMock()
        space.content_hash = current_hash
        indexer.service.space_repo.get_system_space_by_name = AsyncMock(return_value=space)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=knowledge_dir):
            result = await indexer.check_staleness("lia-faq")

        assert result["is_stale"] is False

    @pytest.mark.asyncio
    async def test_stale_when_space_not_found(self, indexer, knowledge_dir) -> None:
        """Should report stale when space doesn't exist yet."""
        indexer.service.space_repo.get_system_space_by_name = AsyncMock(return_value=None)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=knowledge_dir):
            result = await indexer.check_staleness("lia-faq")

        assert result["is_stale"] is True
        assert result["stored_hash"] is None


# ============================================================================
# TestIndexFaqSpace
# ============================================================================


@pytest.mark.unit
class TestIndexFaqSpace:
    """Tests for index_faq_space method."""

    @pytest.mark.asyncio
    async def test_skips_when_hash_matches(self, indexer, knowledge_dir) -> None:
        """Should skip indexation when content hash matches."""
        current_hash = indexer.compute_content_hash(knowledge_dir)
        space = MagicMock()
        space.id = "space-uuid"
        space.content_hash = current_hash
        indexer.service.space_repo.get_system_space_by_name = AsyncMock(return_value=space)

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=knowledge_dir):
            result = await indexer.index_faq_space()

        assert result["status"] == "skipped"
        assert result["chunks_created"] == 0

    @pytest.mark.asyncio
    async def test_error_when_dir_missing(self, indexer, tmp_path) -> None:
        """Should return error when knowledge directory doesn't exist."""
        missing = tmp_path / "nonexistent"

        with patch.object(indexer, "_resolve_knowledge_dir", return_value=missing):
            result = await indexer.index_faq_space()

        assert result["status"] == "error"
        assert (
            "not found" in result["error"].lower() or "not found" in result.get("error", "").lower()
        )
