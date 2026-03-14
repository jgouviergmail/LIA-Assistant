"""
Attachment service for file upload, validation, and lifecycle management.

Responsibilities:
- Upload with in-memory processing (MIME detection, HEIC conversion, PDF extraction)
- MIME validation by magic bytes (not extension)
- HEIC→JPEG conversion (iPhone photos)
- PDF text extraction (PyMuPDF)
- Ownership verification on all access
- Cleanup (conversation reset + TTL expiration)

Note: Files are read fully into memory for processing (magic byte detection,
HEIC conversion, PDF extraction all require full content). This is acceptable
because client-side compression reduces images to ~300KB and max PDF is 20MB.
Single-user assistant on Raspberry Pi — no concurrent upload pressure.

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

import structlog
from fastapi import UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import BaseAPIException

from .models import Attachment, AttachmentContentType, AttachmentStatus
from .repository import AttachmentRepository

logger = structlog.get_logger(__name__)


# ============================================================================
# Exception Helpers (pattern: core/exceptions.py raise_* functions)
# ============================================================================


def raise_attachment_not_found(attachment_id: uuid.UUID) -> NoReturn:
    """Raise 404 when attachment is not found or not owned by user."""
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Attachment not found",
        log_event="attachment_not_found",
        attachment_id=str(attachment_id),
    )


def raise_attachment_too_large(file_size: int, max_size: int) -> NoReturn:
    """Raise 413 when file exceeds size limit."""
    raise BaseAPIException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail=f"File too large ({file_size} bytes, max {max_size} bytes)",
        log_event="attachment_too_large",
        file_size=file_size,
        max_size=max_size,
    )


def raise_attachment_type_not_allowed(mime_type: str) -> NoReturn:
    """Raise 415 when MIME type is not in the allow list."""
    raise BaseAPIException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"File type not allowed: {mime_type}",
        log_event="attachment_type_not_allowed",
        mime_type=mime_type,
    )


def raise_attachment_limit_exceeded(max_per_message: int) -> NoReturn:
    """Raise 400 when too many attachments in a single message."""
    raise BaseAPIException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Maximum {max_per_message} attachments per message",
        log_event="attachment_limit_exceeded",
        max_per_message=max_per_message,
    )


def raise_attachment_upload_failed(reason: str) -> NoReturn:
    """Raise 500 when upload processing fails unexpectedly."""
    raise BaseAPIException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Attachment upload failed",
        log_level="error",
        log_event="attachment_upload_failed",
        reason=reason,
    )


# ============================================================================
# Service
# ============================================================================


class AttachmentService:
    """
    Service for file attachment lifecycle management.

    Pattern: class-based service (VoiceCommentService pattern).
    Receives AsyncSession via __init__, not as method parameter.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AttachmentRepository(db)
        self._settings = get_settings()

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #

    async def upload(
        self,
        user_id: uuid.UUID,
        file: UploadFile,
    ) -> Attachment:
        """
        Upload and process a file attachment.

        Flow:
        1. Validate MIME type (magic bytes via filetype library)
        2. Validate file size against configured limits
        3. HEIC→JPEG conversion if needed (Pillow)
        4. Stream write to disk (chunked, memory-safe)
        5. Extract text from PDF (PyMuPDF)
        6. Create DB record with status='ready'

        Args:
            user_id: Owner user UUID.
            file: FastAPI UploadFile from multipart form.

        Returns:
            Created Attachment instance.

        Raises:
            BaseAPIException: 413, 415, or 500 on validation/processing failure.
        """
        from src.infrastructure.observability.metrics_attachments import (
            attachments_upload_duration_seconds,
            attachments_upload_size_bytes,
            attachments_uploaded_total,
        )

        start_time = time.perf_counter()
        content_type_category: str = "unknown"

        try:
            # Step 1: Read file content and detect MIME
            file_bytes = await file.read()
            detected_mime = self._detect_mime_type(file_bytes)
            content_type_category = self._classify_content(detected_mime)

            # Step 2: Validate size
            max_size_bytes = self._get_max_size_bytes(content_type_category)
            if len(file_bytes) > max_size_bytes:
                attachments_uploaded_total.labels(
                    content_type=content_type_category, status="error"
                ).inc()
                raise_attachment_too_large(len(file_bytes), max_size_bytes)

            # Step 3: HEIC→JPEG conversion
            if detected_mime in ("image/heic", "image/heif"):
                file_bytes, detected_mime = self._convert_heic_to_jpeg(file_bytes)

            # Step 4: Write to disk
            stored_filename = f"{uuid.uuid4()}.{self._mime_to_extension(detected_mime)}"
            relative_path = f"{user_id}/{stored_filename}"
            absolute_path = Path(self._settings.attachments_storage_path) / relative_path

            absolute_path.parent.mkdir(parents=True, exist_ok=True)
            absolute_path.write_bytes(file_bytes)

            # Step 5: Extract PDF text
            extracted_text: str | None = None
            if (
                content_type_category == AttachmentContentType.DOCUMENT
                and detected_mime == "application/pdf"
            ):
                extracted_text = self._extract_pdf_text(
                    file_bytes,
                    max_chars=self._settings.attachments_max_pdf_text_chars,
                )

            # Step 6: Create DB record
            expires_at = datetime.now(UTC) + timedelta(
                hours=self._settings.attachments_ttl_hours,
            )

            attachment = await self.repo.create(
                {
                    "user_id": user_id,
                    "original_filename": file.filename or "unnamed",
                    "stored_filename": stored_filename,
                    "mime_type": detected_mime,
                    "file_size": len(file_bytes),
                    "file_path": relative_path,
                    "content_type": content_type_category,
                    "extracted_text": extracted_text,
                    "status": AttachmentStatus.READY,
                    "expires_at": expires_at,
                }
            )
            await self.db.commit()

            # Metrics
            attachments_uploaded_total.labels(
                content_type=content_type_category, status="success"
            ).inc()
            attachments_upload_size_bytes.labels(content_type=content_type_category).observe(
                len(file_bytes)
            )

            logger.info(
                "attachment_uploaded",
                attachment_id=str(attachment.id),
                user_id=str(user_id),
                mime_type=detected_mime,
                file_size=len(file_bytes),
                content_type=content_type_category,
            )

            return attachment

        except BaseAPIException:
            raise
        except Exception as exc:
            attachments_uploaded_total.labels(
                content_type=content_type_category, status="error"
            ).inc()
            logger.error(
                "attachment_upload_error",
                user_id=str(user_id),
                error=str(exc),
                exc_info=True,
            )
            raise_attachment_upload_failed(str(exc))
        finally:
            duration = time.perf_counter() - start_time
            attachments_upload_duration_seconds.labels(content_type=content_type_category).observe(
                duration
            )

    # ------------------------------------------------------------------ #
    # Access
    # ------------------------------------------------------------------ #

    async def get_for_user(
        self,
        attachment_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Attachment:
        """
        Get a single attachment with ownership verification.

        Args:
            attachment_id: Attachment UUID.
            user_id: Current user UUID (ownership check).

        Returns:
            Attachment instance.

        Raises:
            BaseAPIException: 404 if not found or not owned by user.
        """
        attachment = await self.repo.get_by_id(attachment_id)
        if not attachment or attachment.user_id != user_id:
            raise_attachment_not_found(attachment_id)
        if attachment.status != AttachmentStatus.READY:
            raise_attachment_not_found(attachment_id)
        return attachment

    async def get_batch(
        self,
        attachment_ids: list[uuid.UUID],
        user_id: uuid.UUID,
    ) -> list[Attachment]:
        """
        Get multiple attachments with ownership verification.

        Validates that ALL requested IDs exist and belong to the user.
        Used by ChatRequest processing.

        Args:
            attachment_ids: List of attachment UUIDs.
            user_id: Current user UUID (ownership check).

        Returns:
            List of Attachment instances (same order not guaranteed).

        Raises:
            BaseAPIException: 404 if any attachment is missing or not owned.
        """
        if not attachment_ids:
            return []

        # Validate limit
        max_per_message = self._settings.attachments_max_per_message
        if len(attachment_ids) > max_per_message:
            raise_attachment_limit_exceeded(max_per_message)

        attachments = await self.repo.get_batch_for_user(attachment_ids, user_id)

        # All requested IDs must be found
        if len(attachments) != len(attachment_ids):
            found_ids = {a.id for a in attachments}
            missing = [aid for aid in attachment_ids if aid not in found_ids]
            if missing:
                raise_attachment_not_found(missing[0])

        return attachments

    # ------------------------------------------------------------------ #
    # Deletion
    # ------------------------------------------------------------------ #

    async def delete_for_user_single(
        self,
        attachment_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """
        Delete a single attachment (DB + disk).

        Args:
            attachment_id: Attachment UUID.
            user_id: Current user UUID (ownership check).
        """
        attachment = await self.get_for_user(attachment_id, user_id)

        # Remove from disk
        self._remove_file_from_disk(attachment.file_path)

        # Remove from DB
        await self.repo.delete(attachment)
        await self.db.commit()

        logger.info(
            "attachment_deleted",
            attachment_id=str(attachment_id),
            user_id=str(user_id),
        )

    async def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        """
        Delete all attachments for a user (conversation reset).

        Args:
            user_id: User UUID.

        Returns:
            Number of deleted attachments.
        """
        from src.infrastructure.observability.metrics_attachments import (
            attachments_cleanup_deleted_total,
        )

        # Get file paths before DB delete
        file_paths = await self.repo.get_file_paths_for_user(user_id)

        # Delete DB records
        count = await self.repo.delete_for_user(user_id)
        await self.db.commit()

        # Remove files from disk
        for path in file_paths:
            self._remove_file_from_disk(path)

        # Remove user directory if empty
        user_dir = Path(self._settings.attachments_storage_path) / str(user_id)
        if user_dir.exists() and not any(user_dir.iterdir()):
            user_dir.rmdir()

        if count > 0:
            attachments_cleanup_deleted_total.labels(reason="conversation_reset").inc(count)

        logger.info(
            "attachments_deleted_all_for_user",
            user_id=str(user_id),
            count=count,
        )

        return count

    async def cleanup_expired(self) -> dict[str, int]:
        """
        Clean up expired attachments (scheduler job).

        Returns:
            Dict with cleanup stats: {"deleted": N, "errors": N}.
        """
        from src.infrastructure.observability.metrics_attachments import (
            attachments_active_count,
            attachments_cleanup_deleted_total,
        )

        now = datetime.now(UTC)
        expired = await self.repo.get_expired(now)

        deleted = 0
        errors = 0

        for attachment in expired:
            try:
                self._remove_file_from_disk(attachment.file_path)
                await self.repo.delete(attachment)
                deleted += 1
            except Exception as exc:
                errors += 1
                logger.error(
                    "attachment_cleanup_delete_error",
                    attachment_id=str(attachment.id),
                    error=str(exc),
                )

        if deleted > 0:
            await self.db.commit()
            attachments_cleanup_deleted_total.labels(reason="expired").inc(deleted)

        # Update active gauge
        active_count = await self.repo.count()
        attachments_active_count.set(active_count)

        logger.info(
            "attachment_cleanup_completed",
            deleted=deleted,
            errors=errors,
        )

        return {"deleted": deleted, "errors": errors}

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _detect_mime_type(self, file_bytes: bytes) -> str:
        """Detect MIME type by magic bytes (not file extension)."""
        import filetype  # type: ignore[import-untyped]

        kind = filetype.guess(file_bytes)
        if kind is None:
            raise_attachment_type_not_allowed("unknown (undetectable)")

        detected: str = kind.mime
        allowed = self._get_all_allowed_types()
        if detected not in allowed:
            raise_attachment_type_not_allowed(detected)

        return detected

    def _get_all_allowed_types(self) -> set[str]:
        """Get combined set of allowed MIME types from settings."""
        image_types = {
            t.strip()
            for t in self._settings.attachments_allowed_image_types.split(",")
            if t.strip()
        }
        doc_types = {
            t.strip() for t in self._settings.attachments_allowed_doc_types.split(",") if t.strip()
        }
        return image_types | doc_types

    def _classify_content(self, mime_type: str) -> str:
        """Classify MIME type as AttachmentContentType.IMAGE or DOCUMENT."""
        if mime_type.startswith("image/"):
            return AttachmentContentType.IMAGE
        return AttachmentContentType.DOCUMENT

    def _get_max_size_bytes(self, content_type: str) -> int:
        """Get maximum file size in bytes for the given content type."""
        if content_type == AttachmentContentType.IMAGE:
            return self._settings.attachments_max_image_size_mb * 1024 * 1024
        return self._settings.attachments_max_doc_size_mb * 1024 * 1024

    @staticmethod
    def _convert_heic_to_jpeg(file_bytes: bytes) -> tuple[bytes, str]:
        """Convert HEIC/HEIF image to JPEG using Pillow."""
        import io

        from PIL import Image

        image: Image.Image = Image.open(io.BytesIO(file_bytes))
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85)
        output.seek(0)

        logger.debug(
            "heic_converted_to_jpeg",
            original_size=len(file_bytes),
            converted_size=output.getbuffer().nbytes,
        )

        return output.read(), "image/jpeg"

    @staticmethod
    def _extract_pdf_text(file_bytes: bytes, max_chars: int) -> str | None:
        """Extract text from PDF using PyMuPDF (fitz)."""
        try:
            import fitz  # type: ignore[import-untyped]  # PyMuPDF

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text_parts: list[str] = []
            total_chars = 0

            for page in doc:
                page_text = page.get_text()
                if total_chars + len(page_text) > max_chars:
                    remaining = max_chars - total_chars
                    text_parts.append(page_text[:remaining])
                    break
                text_parts.append(page_text)
                total_chars += len(page_text)

            doc.close()

            full_text = "\n".join(text_parts).strip()
            if not full_text:
                return None

            logger.debug(
                "pdf_text_extracted",
                text_length=len(full_text),
                pages_processed=len(text_parts),
            )

            return full_text

        except Exception as exc:
            logger.warning(
                "pdf_text_extraction_failed",
                error=str(exc),
            )
            return None

    @staticmethod
    def _mime_to_extension(mime_type: str) -> str:
        """Convert MIME type to file extension."""
        mime_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "webp",
            "image/heic": "heic",
            "image/heif": "heif",
            "application/pdf": "pdf",
        }
        return mime_map.get(mime_type, "bin")

    def _remove_file_from_disk(self, relative_path: str) -> None:
        """Remove a file from disk, logging but not raising on error."""
        absolute_path = Path(self._settings.attachments_storage_path) / relative_path
        try:
            if absolute_path.exists():
                absolute_path.unlink()
        except OSError as exc:
            logger.warning(
                "attachment_file_remove_error",
                file_path=str(absolute_path),
                error=str(exc),
            )
