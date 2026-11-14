"""A kept answer or a generated file becomes a message attachment — a COPY (2026-10-24).

The owner asked to bring back into the current discussion what LIA already
gave them: a bookmark, a generated image or document. Each is attached the
way a knowledge-space document is (``knowledge_copy``, ADR-295): a COPY in
the attachments store, an UPLOAD (ADR-279) the next reset removes and the TTL
expires, the original untouched.

- A kept answer is rendered as the very Markdown its knowledge document reads
  (``bookmarks.indexing.render_bookmark``, ADR-291) — whatever state its
  projection is in — and attached as a document carrying that text, cut at the
  attachments' text cap.
- A generated file is copied file and all. Only the caller's own, generated
  (never an upload), live (kept, or before its deadline) and still on disk
  exists here; an image must also pass the bounds an upload passes, a document
  gets its text through the knowledge spaces' pipeline.

The edge ``attachments → bookmarks`` lives here; ``bookmarks`` imports nothing
of ``attachments``.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.conversation_target import ConversationRef
from src.core.i18n import normalize_language
from src.core.time_utils import resolve_user_timezone
from src.domains.attachments.copy_store import (
    copy_and_extract,
    publish_copy,
    write_text_copy,
)
from src.domains.attachments.file_contracts import FileWriteResult, UploadMetadata
from src.domains.attachments.file_paths import owned_relative_path
from src.domains.attachments.knowledge_copy import text_is_capped
from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentStatus,
)
from src.domains.attachments.origin import is_generated
from src.domains.attachments.repository import AttachmentRepository
from src.domains.attachments.service import (
    raise_attachment_not_found,
    raise_attachment_too_large,
    raise_attachment_type_not_allowed,
)
from src.domains.bookmarks.errors import raise_bookmark_not_found
from src.domains.bookmarks.indexing import document_name, render_bookmark
from src.domains.bookmarks.repository import BookmarkRepository
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

#: A kept answer travels as the Markdown its knowledge document reads.
BOOKMARK_MIME: Final = "text/markdown"


async def copy_bookmark(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    bookmark_id: uuid.UUID,
    target: ConversationRef | None = None,
) -> Attachment:
    """Attach one of the caller's kept answers, as the document its space reads.

    Args:
        db: The request session (committed here).
        user_id: The caller — the bookmark must be theirs.
        bookmark_id: The kept answer.

    Returns:
        The attachment row, ``ready``, its text the rendered answer.

    Raises:
        ResourceNotFoundError: 404 when the bookmark is not the caller's.
    """
    bookmark = await BookmarkRepository(db).get_for_user(user_id, bookmark_id)
    if bookmark is None:
        raise_bookmark_not_found(bookmark_id)
    user = await db.get(User, user_id)
    language = normalize_language(getattr(user, "language", None))
    zone = resolve_user_timezone(user).key
    text = render_bookmark(bookmark, language=language, timezone=zone)
    capped = text[: settings.attachments_max_pdf_text_chars]
    attachment = await publish_copy(
        db,
        user_id=user_id,
        target=target,
        metadata=UploadMetadata(
            document_name(bookmark, language=language, timezone=zone),
            BOOKMARK_MIME,
            AttachmentContentType.DOCUMENT,
            ".md",
        ),
        write=lambda path: FileWriteResult(write_text_copy(path, text), capped),
    )
    logger.info(
        "attachment_copied_from_bookmark",
        attachment_id=str(attachment.id),
        user_id=str(user_id),
        bookmark_id=str(bookmark_id),
        text_chars=len(capped),
        text_capped=text_is_capped(capped, settings.attachments_max_pdf_text_chars),
    )
    return attachment


def _check_image_bounds(source: Attachment) -> None:
    """An image copy passes the bounds an upload passes — the same refusals."""
    allowed = {mime.strip() for mime in settings.attachments_allowed_image_types.split(",")}
    if source.mime_type not in allowed:
        raise_attachment_type_not_allowed(source.mime_type)
    max_bytes = settings.attachments_max_image_size_mb * 1024 * 1024
    if source.file_size > max_bytes:
        raise_attachment_too_large(source.file_size, max_bytes)


async def _live_generated(
    db: AsyncSession, user_id: uuid.UUID, attachment_id: uuid.UUID
) -> tuple[Attachment, Path]:
    """The caller's live generated file and where it lies, or a 404."""
    source = await AttachmentRepository(db).get_by_id(attachment_id)
    if (
        source is None
        or source.user_id != user_id
        or not is_generated(source.origin)
        or source.status != AttachmentStatus.READY
        # A kept file has no deadline (ADR-319); any other past its own is gone.
        or (source.expires_at is not None and source.expires_at <= datetime.now(UTC))
    ):
        raise_attachment_not_found(attachment_id)
    relative_path = source.file_path
    await db.commit()
    try:
        path = await asyncio.to_thread(owned_relative_path, user_id, relative_path)
    except ValueError:
        raise_attachment_not_found(attachment_id)
    if not await asyncio.to_thread(path.is_file):
        raise_attachment_not_found(attachment_id)
    return source, path


async def copy_generated(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    attachment_id: uuid.UUID,
    target: ConversationRef | None = None,
) -> Attachment:
    """Attach a copy of one of the caller's generated files.

    Args:
        db: The request session (committed here).
        user_id: The caller — the file must be theirs.
        attachment_id: The generated file.

    Returns:
        The copy, ``ready``: an image as an image, a document with its text.

    Raises:
        BaseAPIException: 404 when the file is not the caller's live generated
            file; 413/415 when an image passes the bounds an upload must pass.
    """
    source, path = await _live_generated(db, user_id, attachment_id)
    image = source.content_type == AttachmentContentType.IMAGE
    if image:
        _check_image_bounds(source)
    extraction_type = None if image else source.mime_type

    def write(destination: Path) -> FileWriteResult:
        text, size = copy_and_extract(
            path, destination, extraction_type, settings.attachments_max_pdf_text_chars
        )
        return FileWriteResult(size, text)

    attachment = await publish_copy(
        db,
        user_id=user_id,
        target=target,
        metadata=UploadMetadata(
            source.original_filename,
            source.mime_type,
            source.content_type,
            Path(source.stored_filename).suffix,
        ),
        write=write,
    )
    logger.info(
        "attachment_copied_from_generated_file",
        attachment_id=str(attachment.id),
        user_id=str(user_id),
        source_id=str(attachment_id),
        content_type=source.content_type,
        text_chars=len(attachment.extracted_text or ""),
    )
    return attachment


__all__ = ["BOOKMARK_MIME", "copy_bookmark", "copy_generated"]
