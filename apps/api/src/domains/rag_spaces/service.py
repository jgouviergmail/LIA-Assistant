"""
RAG Spaces service.

Business logic for space CRUD, document upload/delete, and lifecycle management.
Delegates to repositories for data access and processing.py for background tasks.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import NoReturn

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.models import RAGDocument, RAGDocumentStatus, RAGSpace
from src.domains.rag_spaces.repository import (
    RAGChunkRepository,
    RAGDocumentRepository,
    RAGSpaceRepository,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_documents_total_count,
    rag_spaces_active_count,
    rag_spaces_total_count,
)

logger = get_logger(__name__)

# Extension-to-MIME mapping for defense-in-depth validation
_EXT_TO_MIME: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ============================================================================
# Exception Helpers
# ============================================================================


def raise_space_not_found(space_id: uuid.UUID) -> NoReturn:
    """Raise 404 when space is not found or not owned by user."""
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="RAG space not found",
        log_event="rag_space_not_found",
        space_id=str(space_id),
    )


def raise_document_not_found(document_id: uuid.UUID) -> NoReturn:
    """Raise 404 when document is not found."""
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Document not found",
        log_event="rag_document_not_found",
        document_id=str(document_id),
    )


def raise_space_limit_exceeded(max_spaces: int) -> NoReturn:
    """Raise 400 when user exceeds max spaces limit."""
    raise BaseAPIException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Maximum number of spaces reached ({max_spaces})",
        log_event="rag_space_limit_exceeded",
        max_spaces=max_spaces,
    )


def raise_document_limit_exceeded(max_docs: int) -> NoReturn:
    """Raise 400 when space exceeds max documents limit."""
    raise BaseAPIException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Maximum number of documents per space reached ({max_docs})",
        log_event="rag_document_limit_exceeded",
        max_docs=max_docs,
    )


def raise_file_too_large(file_size: int, max_size_mb: int) -> NoReturn:
    """Raise 413 when file exceeds size limit."""
    raise BaseAPIException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail=f"File too large (max {max_size_mb}MB)",
        log_event="rag_file_too_large",
        file_size=file_size,
        max_size_mb=max_size_mb,
    )


def raise_file_type_not_allowed(content_type: str) -> NoReturn:
    """Raise 415 when file MIME type is not allowed."""
    raise BaseAPIException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"File type not allowed: {content_type}",
        log_event="rag_file_type_not_allowed",
        content_type=content_type,
    )


# ============================================================================
# Service
# ============================================================================


class RAGSpaceService:
    """Service for RAG space and document management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.space_repo = RAGSpaceRepository(db)
        self.doc_repo = RAGDocumentRepository(db)
        self.chunk_repo = RAGChunkRepository(db)

    # ========================================================================
    # Space CRUD
    # ========================================================================

    async def list_spaces(self, user_id: uuid.UUID) -> list[dict]:
        """List all spaces for a user with computed stats."""
        spaces = await self.space_repo.get_all_for_user(user_id)
        result = []
        for space in spaces:
            stats = await self.doc_repo.get_space_stats(space.id)
            result.append(
                {
                    **space.dict(),
                    **stats,
                }
            )
        return result

    async def create_space(
        self,
        user_id: uuid.UUID,
        name: str,
        description: str | None = None,
    ) -> RAGSpace:
        """Create a new RAG space with limit enforcement."""
        # Check space limit
        count = await self.space_repo.count_for_user(user_id)
        if count >= settings.rag_spaces_max_spaces_per_user:
            raise_space_limit_exceeded(settings.rag_spaces_max_spaces_per_user)

        try:
            space = await self.space_repo.create(
                {
                    "user_id": user_id,
                    "name": name.strip(),
                    "description": description.strip() if description else None,
                }
            )
            await self.db.commit()

            rag_spaces_total_count.inc()
            rag_spaces_active_count.inc()  # New spaces are active by default

            logger.info(
                "rag_space_created",
                space_id=str(space.id),
                user_id=str(user_id),
                name=name,
            )
            return space

        except IntegrityError:
            await self.db.rollback()
            raise BaseAPIException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A space named '{name}' already exists",
                log_event="rag_space_duplicate_name",
                name=name,
            ) from None

    async def get_space(self, space_id: uuid.UUID, user_id: uuid.UUID) -> RAGSpace:
        """Get a space with ownership verification."""
        space = await self.space_repo.get_by_id(space_id)
        if not space or space.user_id != user_id:
            raise_space_not_found(space_id)
        return space

    async def get_space_detail(self, space_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        """Get space with documents and computed stats."""
        space = await self.get_space(space_id, user_id)
        stats = await self.doc_repo.get_space_stats(space_id)
        documents = await self.doc_repo.get_all_for_space(space_id)
        return {
            **space.dict(),
            **stats,
            "documents": [doc.dict() for doc in documents],
        }

    async def update_space(
        self,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> RAGSpace:
        """Update a space (partial update)."""
        space = await self.get_space(space_id, user_id)

        update_data: dict[str, str | None] = {}
        if name is not None:
            update_data["name"] = name.strip()
        if description is not None:
            update_data["description"] = description.strip() if description else None

        if update_data:
            try:
                space = await self.space_repo.update(space, update_data)
                await self.db.commit()
            except IntegrityError:
                await self.db.rollback()
                raise BaseAPIException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A space named '{name}' already exists",
                    log_event="rag_space_duplicate_name",
                    name=name,
                ) from None

        if update_data:
            logger.info(
                "rag_space_updated",
                space_id=str(space_id),
                fields=list(update_data.keys()),
            )
        return space

    async def update_space_with_stats(
        self,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Update a space and return it with computed stats."""
        space = await self.update_space(space_id, user_id, name, description)
        stats = await self.doc_repo.get_space_stats(space_id)
        return {**space.dict(), **stats}

    async def delete_space(self, space_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete a space with all its documents, chunks, and files."""
        space = await self.get_space(space_id, user_id)

        # Snapshot document statuses BEFORE cascade delete (for gauge updates)
        documents = await self.doc_repo.get_all_for_space(space_id)

        # DB operations in a single transaction: bulk-delete chunks, then cascade space → docs
        await self.chunk_repo.delete_by_space(space_id)
        await self.space_repo.delete(space)
        await self.db.commit()

        # Physical files cleaned up AFTER successful DB commit (best-effort)
        storage_dir = Path(settings.rag_spaces_storage_path) / str(user_id) / str(space_id)
        if storage_dir.exists():
            shutil.rmtree(storage_dir, ignore_errors=True)

        rag_spaces_total_count.dec()
        if space.is_active:
            rag_spaces_active_count.dec()
        for doc in documents:
            rag_documents_total_count.labels(status=doc.status).dec()

        logger.info(
            "rag_space_deleted",
            space_id=str(space_id),
            user_id=str(user_id),
            name=space.name,
        )

    async def toggle_space(self, space_id: uuid.UUID, user_id: uuid.UUID) -> RAGSpace:
        """Toggle space activation."""
        space = await self.get_space(space_id, user_id)
        space = await self.space_repo.update(space, {"is_active": not space.is_active})
        await self.db.commit()

        if space.is_active:
            rag_spaces_active_count.inc()
        else:
            rag_spaces_active_count.dec()

        logger.info(
            "rag_space_toggled",
            space_id=str(space_id),
            is_active=space.is_active,
        )
        return space

    # ========================================================================
    # Document Management
    # ========================================================================

    async def upload_document(
        self,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
        file: UploadFile,
    ) -> RAGDocument:
        """
        Upload a document to a space.

        Validates format/size, writes to disk, creates DB record with
        status=processing, and returns the document. The caller is
        responsible for launching the background processing task.
        """
        await self.get_space(space_id, user_id)  # Verify ownership

        # Check document limit
        doc_count = await self.doc_repo.count_for_space(space_id)
        if doc_count >= settings.rag_spaces_max_docs_per_space:
            raise_document_limit_exceeded(settings.rag_spaces_max_docs_per_space)

        # Validate MIME type from client header
        content_type = file.content_type or "application/octet-stream"
        allowed_types = [t.strip() for t in settings.rag_spaces_allowed_types.split(",")]
        if content_type not in allowed_types:
            raise_file_type_not_allowed(content_type)

        # Validate file extension matches claimed MIME type (defense-in-depth)
        original_filename = file.filename or "unnamed"
        ext = Path(original_filename).suffix.lower()
        expected_mime = _EXT_TO_MIME.get(ext)
        if expected_mime and expected_mime != content_type:
            raise_file_type_not_allowed(content_type)

        # Read file content with size limit (streaming to avoid unbounded RAM usage)
        max_size_bytes = settings.rag_spaces_max_file_size_mb * 1024 * 1024
        chunks: list[bytes] = []
        total_read = 0
        while True:
            chunk = await file.read(64 * 1024)  # 64KB chunks
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > max_size_bytes:
                raise_file_too_large(total_read, settings.rag_spaces_max_file_size_mb)
            chunks.append(chunk)
        content = b"".join(chunks)
        file_size = total_read

        # Generate UUID-based filename (anti-traversal)
        stored_filename = f"{uuid.uuid4().hex}{ext}"

        # Write to disk
        storage_dir = Path(settings.rag_spaces_storage_path) / str(user_id) / str(space_id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / stored_filename
        file_path.write_bytes(content)

        # Create DB record — clean up file on failure to avoid orphans
        try:
            document = await self.doc_repo.create(
                {
                    "space_id": space_id,
                    "user_id": user_id,
                    "filename": stored_filename,
                    "original_filename": original_filename,
                    "file_size": file_size,
                    "content_type": content_type,
                    "status": RAGDocumentStatus.PROCESSING,
                }
            )
            await self.db.commit()
        except Exception:
            # Rollback DB and remove orphan file on failure
            await self.db.rollback()
            if file_path.exists():
                os.remove(file_path)
            raise

        rag_documents_total_count.labels(status="processing").inc()

        logger.info(
            "rag_document_uploaded",
            document_id=str(document.id),
            space_id=str(space_id),
            original_filename=original_filename,
            content_type=content_type,
            file_size=file_size,
        )
        return document

    async def delete_document(
        self,
        space_id: uuid.UUID,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a document with its chunks and physical file."""
        # Verify space ownership
        await self.get_space(space_id, user_id)

        document = await self.doc_repo.get_by_id(document_id)
        if not document or document.space_id != space_id or document.user_id != user_id:
            raise_document_not_found(document_id)

        # DB operations in a single transaction: chunks + document record
        await self.chunk_repo.delete_by_document(document_id)
        await self.doc_repo.delete(document)
        await self.db.commit()

        # Physical file cleaned up AFTER successful DB commit (best-effort)
        file_path = (
            Path(settings.rag_spaces_storage_path)
            / str(user_id)
            / str(space_id)
            / document.filename
        )
        if file_path.exists():
            os.remove(file_path)

        rag_documents_total_count.labels(status=document.status).dec()

        logger.info(
            "rag_document_deleted",
            document_id=str(document_id),
            space_id=str(space_id),
            original_filename=document.original_filename,
        )

    async def get_document_status(
        self,
        space_id: uuid.UUID,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> RAGDocument:
        """Get document processing status with ownership verification."""
        await self.get_space(space_id, user_id)

        document = await self.doc_repo.get_by_id(document_id)
        if not document or document.space_id != space_id or document.user_id != user_id:
            raise_document_not_found(document_id)

        return document
