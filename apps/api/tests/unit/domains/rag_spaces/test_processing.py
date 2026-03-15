"""
Unit tests for RAG Spaces document processing pipeline.

Tests text extraction functions (plain, PDF, DOCX), the extract_text
dispatcher, and the async process_document background task with mocked
DB sessions, embeddings, and metrics.

Phase: evolution — RAG Spaces (User Knowledge Documents)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.rag_spaces.models import RAGDocumentStatus
from src.domains.rag_spaces.processing import (
    EMBEDDING_BATCH_SIZE,
    extract_text,
    extract_text_plain,
    process_document,
)

# ============================================================================
# Text Extraction — Plain / Markdown
# ============================================================================


class TestExtractTextPlain:
    """Tests for extract_text_plain (UTF-8 text/markdown files)."""

    @pytest.mark.unit
    def test_reads_utf8_text(self, tmp_path: Path) -> None:
        """Plain text file is read with UTF-8 encoding."""
        file = tmp_path / "note.txt"
        file.write_text("Hello, world!", encoding="utf-8")

        result = extract_text_plain(file)

        assert result == "Hello, world!"

    @pytest.mark.unit
    def test_handles_unicode_characters(self, tmp_path: Path) -> None:
        """Unicode characters (accents, CJK) are preserved."""
        content = "Resume: cafe\u0301 \u2014 \u4f60\u597d \u2014 \u00fc\u00f6\u00e4"
        file = tmp_path / "unicode.md"
        file.write_text(content, encoding="utf-8")

        result = extract_text_plain(file)

        assert result == content

    @pytest.mark.unit
    def test_empty_file_returns_empty_string(self, tmp_path: Path) -> None:
        """An empty file returns an empty string."""
        file = tmp_path / "empty.txt"
        file.write_text("", encoding="utf-8")

        result = extract_text_plain(file)

        assert result == ""


# ============================================================================
# Text Extraction — PDF
# ============================================================================


class TestExtractTextPdf:
    """Tests for extract_text_pdf (PyMuPDF / fitz)."""

    @pytest.mark.unit
    def test_extracts_text_from_pdf(self, tmp_path: Path) -> None:
        """PDF text extraction returns joined page text."""
        mock_page_1 = MagicMock()
        mock_page_1.get_text.return_value = "Page one content."
        mock_page_2 = MagicMock()
        mock_page_2.get_text.return_value = "Page two content."

        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page_1, mock_page_2]))

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            from src.domains.rag_spaces.processing import extract_text_pdf

            result = extract_text_pdf(tmp_path / "dummy.pdf")

        assert result == "Page one content.\nPage two content."

    @pytest.mark.unit
    def test_empty_pdf_returns_empty_string(self, tmp_path: Path) -> None:
        """A PDF with no pages returns an empty string."""
        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_doc.__iter__ = MagicMock(return_value=iter([]))

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            from src.domains.rag_spaces.processing import extract_text_pdf

            result = extract_text_pdf(tmp_path / "empty.pdf")

        assert result == ""


# ============================================================================
# Text Extraction — DOCX
# ============================================================================


class TestExtractTextDocx:
    """Tests for extract_text_docx (python-docx)."""

    @pytest.mark.unit
    def test_extracts_paragraphs_from_docx(self, tmp_path: Path) -> None:
        """DOCX extraction joins non-empty paragraphs with newlines."""
        mock_para_1 = MagicMock()
        mock_para_1.text = "First paragraph."
        mock_para_2 = MagicMock()
        mock_para_2.text = ""
        mock_para_3 = MagicMock()
        mock_para_3.text = "Third paragraph."

        mock_document = MagicMock()
        mock_document.paragraphs = [mock_para_1, mock_para_2, mock_para_3]

        mock_docx_module = MagicMock()
        mock_docx_module.Document.return_value = mock_document

        with patch.dict(sys.modules, {"docx": mock_docx_module}):
            from src.domains.rag_spaces.processing import extract_text_docx

            result = extract_text_docx(tmp_path / "test.docx")

        assert result == "First paragraph.\nThird paragraph."

    @pytest.mark.unit
    def test_whitespace_only_paragraphs_are_skipped(self, tmp_path: Path) -> None:
        """Paragraphs with only whitespace are excluded."""
        mock_para = MagicMock()
        mock_para.text = "   "

        mock_document = MagicMock()
        mock_document.paragraphs = [mock_para]

        mock_docx_module = MagicMock()
        mock_docx_module.Document.return_value = mock_document

        with patch.dict(sys.modules, {"docx": mock_docx_module}):
            from src.domains.rag_spaces.processing import extract_text_docx

            result = extract_text_docx(tmp_path / "ws.docx")

        assert result == ""


# ============================================================================
# extract_text dispatcher
# ============================================================================


class TestExtractText:
    """Tests for the extract_text dispatcher function."""

    @pytest.mark.unit
    def test_dispatches_plain_text(self, tmp_path: Path) -> None:
        """text/plain MIME type dispatches to extract_text_plain."""
        file = tmp_path / "note.txt"
        file.write_text("plain content", encoding="utf-8")

        result = extract_text(file, "text/plain")

        assert result == "plain content"

    @pytest.mark.unit
    def test_dispatches_markdown(self, tmp_path: Path) -> None:
        """text/markdown MIME type dispatches to extract_text_plain."""
        file = tmp_path / "readme.md"
        file.write_text("# Title\n\nBody", encoding="utf-8")

        result = extract_text(file, "text/markdown")

        assert result == "# Title\n\nBody"

    @pytest.mark.unit
    def test_raises_for_unsupported_content_type(self, tmp_path: Path) -> None:
        """Unsupported MIME type raises ValueError."""
        file = tmp_path / "image.png"
        file.write_bytes(b"\x89PNG")

        with pytest.raises(ValueError, match="Unsupported content type"):
            extract_text(file, "image/png")

    @pytest.mark.unit
    def test_dispatches_pdf(self, tmp_path: Path) -> None:
        """application/pdf dispatches to extract_text_pdf."""
        with patch(
            "src.domains.rag_spaces.processing.extract_text_pdf",
            return_value="pdf content",
        ) as mock_pdf:
            result = extract_text(tmp_path / "doc.pdf", "application/pdf")

        assert result == "pdf content"
        mock_pdf.assert_called_once()

    @pytest.mark.unit
    def test_dispatches_docx(self, tmp_path: Path) -> None:
        """DOCX MIME type dispatches to extract_text_docx."""
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        with patch(
            "src.domains.rag_spaces.processing.extract_text_docx",
            return_value="docx content",
        ) as mock_docx:
            result = extract_text(tmp_path / "doc.docx", docx_mime)

        assert result == "docx content"
        mock_docx.assert_called_once()


# ============================================================================
# process_document — async background task
# ============================================================================


class TestProcessDocument:
    """Tests for the async process_document background pipeline."""

    @pytest.fixture
    def ids(self):
        """Generate fresh UUIDs for each test."""
        return {
            "document_id": uuid4(),
            "space_id": uuid4(),
            "user_id": uuid4(),
        }

    @pytest.fixture
    def mock_document(self, ids):
        """Create a mock RAGDocument."""
        doc = MagicMock()
        doc.id = ids["document_id"]
        doc.file_size = 1024
        return doc

    @pytest.fixture
    def mock_db_context(self):
        """Create a mock async context manager for get_db_context."""
        mock_db = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx, mock_db

    def _patch_processing(self):
        """Return a dict of common patches for process_document tests."""
        return {
            "db_ctx": patch(
                "src.domains.rag_spaces.processing.get_db_context",
            ),
            "embeddings": patch(
                "src.domains.rag_spaces.processing.get_rag_embeddings",
            ),
            "set_ctx": patch(
                "src.domains.rag_spaces.processing.set_embedding_context",
            ),
            "clear_ctx": patch(
                "src.domains.rag_spaces.processing.clear_embedding_context",
            ),
            "settings": patch(
                "src.domains.rag_spaces.processing.settings",
            ),
            "metrics_processed": patch(
                "src.domains.rag_spaces.processing.rag_documents_processed_total",
            ),
            "metrics_duration": patch(
                "src.domains.rag_spaces.processing.rag_document_processing_duration_seconds",
            ),
            "metrics_chunks": patch(
                "src.domains.rag_spaces.processing.rag_document_chunks_total",
            ),
            "metrics_size": patch(
                "src.domains.rag_spaces.processing.rag_document_upload_size_bytes",
            ),
            "metrics_tokens": patch(
                "src.domains.rag_spaces.processing.rag_embedding_tokens_total",
            ),
            "estimate_cost": patch(
                "src.infrastructure.llm.tracked_embeddings.estimate_embedding_cost_sync",
                return_value=0.001,
            ),
            "cached_rate": patch(
                "src.infrastructure.cache.pricing_cache.get_cached_usd_eur_rate",
                return_value=0.92,
            ),
        }

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_file_not_found_marks_error(self, ids, mock_document) -> None:
        """When the uploaded file does not exist on disk, document is marked as error."""
        patches = self._patch_processing()

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = mock_document

        with (
            patches["db_ctx"] as mock_get_db,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"] as mock_settings,
            patches["metrics_processed"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            mock_settings.rag_spaces_storage_path = "/nonexistent/storage"

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                ),
                patch(
                    "src.domains.rag_spaces.processing._mark_document_error",
                    new_callable=AsyncMock,
                ) as mock_mark_error,
            ):
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc123.txt",
                    original_filename="my_doc.txt",
                    content_type="text/plain",
                )

                mock_mark_error.assert_awaited_once()
                call_args = mock_mark_error.call_args
                assert "File not found" in call_args[0][3]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_empty_text_marks_error(self, ids, mock_document, tmp_path) -> None:
        """When extracted text is empty/whitespace, document is marked as error."""
        patches = self._patch_processing()

        # Create an actual empty file
        storage_dir = tmp_path / str(ids["user_id"]) / str(ids["space_id"])
        storage_dir.mkdir(parents=True)
        empty_file = storage_dir / "abc123.txt"
        empty_file.write_text("   ", encoding="utf-8")

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = mock_document

        with (
            patches["db_ctx"] as mock_get_db,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"] as mock_settings,
            patches["metrics_processed"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            mock_settings.rag_spaces_storage_path = str(tmp_path)

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                ),
                patch(
                    "src.domains.rag_spaces.processing._mark_document_error",
                    new_callable=AsyncMock,
                ) as mock_mark_error,
            ):
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc123.txt",
                    original_filename="empty.txt",
                    content_type="text/plain",
                )

                mock_mark_error.assert_awaited_once()
                call_args = mock_mark_error.call_args
                assert "No text content" in call_args[0][3]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_too_many_chunks_marks_error(self, ids, mock_document, tmp_path) -> None:
        """When chunk count exceeds max_chunks_per_document, document is marked as error."""
        patches = self._patch_processing()

        # Create a file with enough content to produce many chunks
        storage_dir = tmp_path / str(ids["user_id"]) / str(ids["space_id"])
        storage_dir.mkdir(parents=True)
        big_file = storage_dir / "abc123.txt"
        big_file.write_text("word " * 50000, encoding="utf-8")

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = mock_document

        with (
            patches["db_ctx"] as mock_get_db,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"] as mock_settings,
            patches["metrics_processed"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            mock_settings.rag_spaces_storage_path = str(tmp_path)
            mock_settings.rag_spaces_chunk_size = 100
            mock_settings.rag_spaces_chunk_overlap = 10
            # Set max chunks very low to trigger the guard
            mock_settings.rag_spaces_max_chunks_per_document = 2

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                ),
                patch(
                    "src.domains.rag_spaces.processing._mark_document_error",
                    new_callable=AsyncMock,
                ) as mock_mark_error,
            ):
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc123.txt",
                    original_filename="big.txt",
                    content_type="text/plain",
                )

                mock_mark_error.assert_awaited_once()
                call_args = mock_mark_error.call_args
                assert "exceeding limit" in call_args[0][3]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_processing(self, ids, mock_document, tmp_path) -> None:
        """Happy path: text extracted, chunks created, embeddings generated, status set to READY."""
        patches = self._patch_processing()

        # Create a small file
        storage_dir = tmp_path / str(ids["user_id"]) / str(ids["space_id"])
        storage_dir.mkdir(parents=True)
        doc_file = storage_dir / "abc123.txt"
        doc_file.write_text(
            "This is paragraph one about artificial intelligence.\n\n"
            "This is paragraph two about machine learning.",
            encoding="utf-8",
        )

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = mock_document
        mock_chunk_repo = AsyncMock()
        mock_chunk_repo.bulk_create_chunks.return_value = 2

        mock_embeddings = AsyncMock()
        # Return one vector per chunk (dynamic based on input)
        mock_embeddings.aembed_documents.side_effect = lambda texts: [
            [0.1 * (i + 1)] * 10 for i in range(len(texts))
        ]

        with (
            patches["db_ctx"] as mock_get_db,
            patches["embeddings"] as mock_get_emb,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"] as mock_settings,
            patches["metrics_processed"],
            patches["metrics_duration"],
            patches["metrics_chunks"],
            patches["metrics_size"],
            patches["metrics_tokens"],
            patches["estimate_cost"],
            patches["cached_rate"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            mock_settings.rag_spaces_storage_path = str(tmp_path)
            mock_settings.rag_spaces_chunk_size = 500
            mock_settings.rag_spaces_chunk_overlap = 50
            mock_settings.rag_spaces_max_chunks_per_document = 1000
            mock_settings.rag_spaces_embedding_model = "text-embedding-3-small"

            mock_get_emb.return_value = mock_embeddings

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                    return_value=mock_chunk_repo,
                ),
            ):
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc123.txt",
                    original_filename="notes.txt",
                    content_type="text/plain",
                )

            # Verify embeddings were requested
            mock_embeddings.aembed_documents.assert_awaited()

            # Verify chunks were bulk-inserted
            mock_chunk_repo.bulk_create_chunks.assert_awaited_once()
            created_chunks = mock_chunk_repo.bulk_create_chunks.call_args[0][0]
            assert len(created_chunks) > 0

            # Verify document status updated to READY
            mock_doc_repo.update.assert_awaited_once()
            update_data = mock_doc_repo.update.call_args[0][1]
            assert update_data["status"] == RAGDocumentStatus.READY
            assert update_data["error_message"] is None
            assert update_data["chunk_count"] > 0

            # Verify DB commit
            mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_document_not_found_returns_early(self, ids) -> None:
        """When document ID does not exist in DB, function returns without error."""
        patches = self._patch_processing()

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_by_id.return_value = None

        with (
            patches["db_ctx"] as mock_get_db,
            patches["set_ctx"],
            patches["clear_ctx"],
            patches["settings"],
        ):
            ctx_manager = AsyncMock()
            ctx_manager.__aenter__ = AsyncMock(return_value=mock_db)
            ctx_manager.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = ctx_manager

            with (
                patch(
                    "src.domains.rag_spaces.processing.RAGDocumentRepository",
                    return_value=mock_doc_repo,
                ),
                patch(
                    "src.domains.rag_spaces.processing.RAGChunkRepository",
                ),
            ):
                # Should not raise
                await process_document(
                    document_id=ids["document_id"],
                    space_id=ids["space_id"],
                    user_id=ids["user_id"],
                    filename="abc.txt",
                    original_filename="missing.txt",
                    content_type="text/plain",
                )

            # update should NOT have been called
            mock_doc_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_embedding_context_always_cleared(self, ids, mock_document) -> None:
        """Embedding context is cleared even when processing raises an exception."""
        with (
            patch(
                "src.domains.rag_spaces.processing.get_db_context",
                side_effect=RuntimeError("DB connection failed"),
            ),
            patch(
                "src.domains.rag_spaces.processing.set_embedding_context",
            ),
            patch(
                "src.domains.rag_spaces.processing.clear_embedding_context",
            ) as mock_clear,
            patch("src.domains.rag_spaces.processing.rag_documents_processed_total"),
        ):
            await process_document(
                document_id=ids["document_id"],
                space_id=ids["space_id"],
                user_id=ids["user_id"],
                filename="abc.txt",
                original_filename="crash.txt",
                content_type="text/plain",
            )

            mock_clear.assert_called_once()

    @pytest.mark.unit
    def test_embedding_batch_size_constant(self) -> None:
        """EMBEDDING_BATCH_SIZE is set to the expected value."""
        assert EMBEDDING_BATCH_SIZE == 100
