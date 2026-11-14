"""
Attachment service for file upload, validation, and lifecycle management.

Responsibilities:
- Upload with in-memory processing (type detection, HEIC conversion, text extraction)
- Type decided by what the file IS: an image by its magic bytes, a document
  on its whole content (``document_formats``) — never by the declared type
- HEIC→JPEG conversion (iPhone photos)
- Text extraction: PDF (PyMuPDF), every other document format through the
  knowledge spaces' readers
- Ownership verification on all access
- Cleanup (conversation reset + TTL expiration)

Reads are bounded by the server's per-type limit before allocating the full
processing buffer. File ownership is committed before disk effects; publication
rechecks the immutable source and failed writes retain a cleanup record.

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import structlog
from fastapi import UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.constants import ATTACHMENTS_READ_CHUNK_BYTES
from src.core.conversation_execution import ExecutionRevoked
from src.core.conversation_target import ConversationRef
from src.core.exceptions import BaseAPIException
from src.domains.attachments.conversation_usage import ConversationAttachmentUsageRepository
from src.domains.attachments.document_formats import (
    detect_document_type,
    extension_of,
    extract_capped_text,
)
from src.domains.attachments.file_cleanup import cleanup_files
from src.domains.attachments.file_contracts import FileWriteResult, UploadMetadata
from src.domains.attachments.file_publication import publish_file
from src.domains.attachments.file_repository import AttachmentFileRepository
from src.domains.attachments.origin import GENERATED_ORIGINS
from src.domains.attachments.publication_errors import raise_retired_file_source
from src.domains.attachments.selection import validate_upload_filename
from src.infrastructure.async_utils import finish_owned_task
from src.infrastructure.observability.metrics_attachments import DELETION_REASON_USER

from .models import Attachment, AttachmentContentType, AttachmentStatus
from .repository import AttachmentRepository

if TYPE_CHECKING:
    from src.domains.attachments.gallery_queries import GalleryFilters

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
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
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
        *,
        target: ConversationRef | None = None,
    ) -> Attachment:
        """
        Upload and process a file attachment.

        Read only bounded chunks, decide the type by what the file IS (an image
        by its first bytes; a document on its whole content, since an archive
        names itself at its end — ``document_formats``), convert HEIC off-loop,
        then use the shared durable publication protocol. The conversion, the
        detection and the disk worker are joined through cancellation, not
        merely abandoned.

        Args:
            user_id: Owner user UUID.
            file: FastAPI UploadFile from multipart form.
            target: Source frozen at request admission; None is a legacy unbound file.

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

        filename = validate_upload_filename(file.filename or "unnamed")
        start_time = time.perf_counter()
        content_type_category: str = "unknown"

        try:
            # End auth/source reads before waiting on the spooled upload or CPU.
            await self.db.commit()
            prefix = await file.read(ATTACHMENTS_READ_CHUNK_BYTES)
            image_mime = self._detect_mime_type(prefix)
            content_type_category = self._classify_content(image_mime)
            max_size_bytes = self._get_max_size_bytes(content_type_category)
            file_bytes = await self._read_bounded(file, prefix, max_size_bytes)
            detected_mime: str = (
                image_mime
                if image_mime is not None
                # Off the loop: an archive's directory is parsed, and the whole
                # content is scanned for the byte no text file holds.
                else await finish_owned_task(
                    asyncio.create_task(
                        asyncio.to_thread(self._detect_document_type, filename, file_bytes)
                    )
                )
            )

            # Step 3: HEIC→JPEG conversion — Pillow decodes and re-encodes the whole
            # picture: on the loop, a 12-megapixel photo stalled it about a second
            # (measured). Off the event loop, like the write below.
            if detected_mime in ("image/heic", "image/heif"):
                file_bytes, detected_mime = await finish_owned_task(
                    asyncio.create_task(asyncio.to_thread(self._convert_heic_to_jpeg, file_bytes))
                )
                if len(file_bytes) > max_size_bytes:
                    raise_attachment_too_large(len(file_bytes), max_size_bytes)

            def write(path: Path) -> FileWriteResult:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(file_bytes)
                extracted = self._extract_text(
                    path, file_bytes, detected_mime, content_type_category
                )
                return FileWriteResult(len(file_bytes), extracted)

            attachment = await publish_file(
                self.db,
                owner_id=user_id,
                metadata=UploadMetadata(
                    filename,
                    detected_mime,
                    content_type_category,
                    f".{self._mime_to_extension(detected_mime)}",
                ),
                target=target,
                write=write,
            )

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
            attachments_uploaded_total.labels(
                content_type=content_type_category, status="error"
            ).inc()
            raise
        except ExecutionRevoked as exc:
            attachments_uploaded_total.labels(
                content_type=content_type_category, status="error"
            ).inc()
            raise_retired_file_source(exc)
        except Exception as exc:
            attachments_uploaded_total.labels(
                content_type=content_type_category, status="error"
            ).inc()
            logger.error(
                "attachment_upload_error",
                user_id=str(user_id),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            raise_attachment_upload_failed(type(exc).__name__)
        finally:
            duration = time.perf_counter() - start_time
            attachments_upload_duration_seconds.labels(content_type=content_type_category).observe(
                duration
            )

    async def _read_bounded(self, file: UploadFile, prefix: bytes, limit: int) -> bytes:
        """Stop at the first excess byte, retaining no unbounded body allocation."""
        content = bytearray(prefix)
        while True:
            if len(content) > limit:
                raise_attachment_too_large(len(content), limit)
            chunk = await file.read(min(ATTACHMENTS_READ_CHUNK_BYTES, limit + 1 - len(content)))
            if not chunk:
                return bytes(content)
            content.extend(chunk)

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

    async def accept_for_conversation(
        self, attachment_ids: list[uuid.UUID], user_id: uuid.UUID, target: ConversationRef
    ) -> list[Attachment]:
        """Accept all files under the current source and persist their shared usages.

        The caller owns the short transaction and commits it before best-effort
        message archiving. Missing, expired and foreign files all refuse the batch.
        """
        if len(attachment_ids) > self._settings.attachments_max_per_message:
            raise_attachment_limit_exceeded(self._settings.attachments_max_per_message)
        return await ConversationAttachmentUsageRepository(self.db).accept_batch(
            user_id, attachment_ids, target
        )

    # ------------------------------------------------------------------ #
    # Deletion
    # ------------------------------------------------------------------ #

    async def delete_for_user_single(
        self,
        attachment_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """
        Retire a single attachment, retaining retryable evidence until its file is gone.

        Args:
            attachment_id: Attachment UUID.
            user_id: Current user UUID (ownership check).
        """
        await self.get_for_user(attachment_id, user_id)
        await AttachmentFileRepository(self.db).retire_owned(
            user_id, ids=[attachment_id], reason=DELETION_REASON_USER
        )
        await self.db.commit()
        await cleanup_files(self.db, ids=[attachment_id])

        logger.info(
            "attachment_deleted",
            attachment_id=str(attachment_id),
            user_id=str(user_id),
        )

    async def cleanup_expired(self) -> dict[str, int]:
        """
        Clean up expired attachments (scheduler job).

        Retire expired READY files atomically, then retry bounded durable disk
        effects. A keep that commits first wins; a retired file cannot be kept.
        An unknown uploader is never declared stopped merely because it aged.

        Returns:
            Exact physical results {"deleted": N, "errors": N}. Failed paths
            remain recorded for a later sweep, with their original reason.
        """
        from src.infrastructure.observability.metrics_attachments import (
            attachments_active_count,
            attachments_kept_bytes,
            attachments_kept_count,
        )

        await AttachmentFileRepository(self.db).retire_expired(datetime.now(UTC))
        await self.db.commit()
        stats = await cleanup_files(self.db)

        # Gauges: what the table holds, and what people chose to keep — the
        # disk a kept file holds is never reclaimed by this sweep.
        attachments_active_count.set(await self.repo.count())
        kept_files, kept_bytes = await self.repo.kept_totals()
        attachments_kept_count.set(kept_files)
        attachments_kept_bytes.set(kept_bytes)

        logger.info(
            "attachment_cleanup_completed",
            deleted=stats["deleted"],
            errors=stats["errors"],
            kept_files=kept_files,
        )

        return stats

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _detect_mime_type(self, file_bytes: bytes) -> str | None:
        """The type the first bytes alone prove — an image — or None for a document.

        Args:
            file_bytes: The first chunk of the upload.

        Returns:
            The image's MIME type, by its magic bytes; None when the content is
            not an image and must be decided whole (``_detect_document_type``).

        Raises:
            BaseAPIException: 415 for an image format the instance does not allow.
        """
        import filetype  # type: ignore[import-untyped]

        kind = filetype.guess(file_bytes)
        if kind is None or not kind.mime.startswith("image/"):
            return None
        detected: str = kind.mime
        if detected not in self._get_all_allowed_types():
            raise_attachment_type_not_allowed(detected)
        return detected

    def _detect_document_type(self, filename: str, file_bytes: bytes) -> str:
        """The document format of a whole upload, by what it is.

        Args:
            filename: The name it was sent under (read for a text format only).
            file_bytes: Its whole, bounded content.

        Returns:
            The MIME type of an allowed document format.

        Raises:
            BaseAPIException: 415 when the content is no known document, or a
                format the instance does not allow.
        """
        detected = detect_document_type(filename, file_bytes)
        if detected is None:
            raise_attachment_type_not_allowed("unknown (undetectable)")
        if detected not in self._get_all_allowed_types():
            raise_attachment_type_not_allowed(detected)
        return detected

    def _extract_text(
        self, path: Path, file_bytes: bytes, mime_type: str, content_type: str
    ) -> str | None:
        """What the model will read of a stored upload: a document's text, capped.

        Args:
            path: Where the file was just written.
            file_bytes: Its content.
            mime_type: What it is.
            content_type: Its category; an image carries no text.

        Returns:
            The capped text, or None for an image or an unreadable document.
        """
        cap = self._settings.attachments_max_pdf_text_chars
        if mime_type == "application/pdf":
            return self._extract_pdf_text(file_bytes, cap)
        if content_type == AttachmentContentType.DOCUMENT:
            return extract_capped_text(path, mime_type, cap)
        return None

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

    def _classify_content(self, mime_type: str | None) -> str:
        """Classify as IMAGE or DOCUMENT; what is not a proven image is a document."""
        if mime_type is not None and mime_type.startswith("image/"):
            return AttachmentContentType.IMAGE
        return AttachmentContentType.DOCUMENT

    def _get_max_size_bytes(self, content_type: str) -> int:
        """Get maximum file size in bytes for the given content type."""
        if content_type == AttachmentContentType.IMAGE:
            return self._settings.attachments_max_image_size_mb * 1024 * 1024
        return self._settings.attachments_max_doc_size_mb * 1024 * 1024

    @staticmethod
    def _convert_heic_to_jpeg(file_bytes: bytes) -> tuple[bytes, str]:
        """Convert HEIC/HEIF image to JPEG using Pillow (the HEIF plugin registered first)."""
        import io

        from PIL import Image

        from src.infrastructure.media.heif import ensure_heif_support

        ensure_heif_support()
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
        """Extract text from PDF using PyMuPDF."""
        try:
            import pymupdf

            text_parts: list[str] = []
            total_chars = 0

            with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    page_text = page.get_text()
                    if total_chars + len(page_text) > max_chars:
                        remaining = max_chars - total_chars
                        text_parts.append(page_text[:remaining])
                        break
                    text_parts.append(page_text)
                    total_chars += len(page_text)

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
                error_type=type(exc).__name__,
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
        known = mime_map.get(mime_type)
        if known is not None:
            return known
        extension = extension_of(mime_type)
        return extension.removeprefix(".") if extension else "bin"

    async def list_generated(
        self, user_id: uuid.UUID, filters: GalleryFilters
    ) -> tuple[list[Attachment], int, int]:
        """One page of a gallery, its exact total and the bytes behind it.

        Args:
            user_id: Whose gallery.
            filters: What it is narrowed to.

        Returns:
            ``(rows, total, total_bytes)``.
        """
        return await self.repo.list_generated(user_id, filters)

    async def delete_generated_batch(
        self, user_id: uuid.UUID, ids: list[uuid.UUID], *, commit: bool = True
    ) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
        """Retire a selection of the person's generated files, once per requested id.

        Says EXACTLY what went: an id the caller does not own, or one the
        cleanup removed between the listing and the click, is skipped rather
        than counted as deleted (ADR-185 — a count shown to a person is exact
        or it does not exist).

        Args:
            user_id: Owner.
            ids: Candidate ids.
            commit: False defers commit and physical cleanup to the caller.

        Returns:
            ``(retired, skipped)`` in request order. Retired files leave all
            readable surfaces immediately; failed physical cleanup is retried.
        """
        # The same id twice is ONE file. Walking `ids` as given deleted the row
        # twice, unlinked it twice, counted two removals and returned it twice
        # — « 2 supprimés » for one file is the claim ADR-185 forbids. The
        # first occurrence keeps its place: re-sorting would make a client
        # match rows by luck (cold review, 2026-09-10).
        wanted = list(dict.fromkeys(ids))
        retired = set(
            await AttachmentFileRepository(self.db).retire_owned(
                user_id,
                ids=wanted,
                origins=[origin.value for origin in GENERATED_ORIGINS],
                reason=DELETION_REASON_USER,
            )
        )
        deleted = [candidate for candidate in wanted if candidate in retired]
        if deleted:
            if commit:
                await self.db.commit()
                await cleanup_files(self.db, ids=deleted)
            else:
                await self.db.flush()

        removed = set(deleted)
        skipped = [candidate for candidate in wanted if candidate not in removed]
        logger.info(
            "generated_assets_deleted",
            user_id=str(user_id),
            deleted=len(deleted),
            skipped=len(skipped),
        )
        return deleted, skipped
