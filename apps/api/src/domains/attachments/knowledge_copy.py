"""A knowledge-space document becomes a message attachment — a COPY the person chose.

The composer's « + » offers the documents already indexed in the person's
spaces, ACTIVE OR NOT: the search of a knowledge space reads the active ones
alone, so a document of a paused space was unreachable from the chat. Pointing
at it here does not activate anything — the stored file is COPIED into the
attachments store under a fresh UUID name, its text extracted through the
knowledge spaces' own pipeline (the fifteen formats, not the upload's
image-and-PDF allowlist) under the attachments' text cap, and the row is an
UPLOAD (ADR-279): a conversation reset removes it like anything the person
put in, the TTL sweep expires it, the knowledge document is never touched.

Only a ``ready`` document is offered — its extraction is proven; a document of
another account, or of a system space (which belongs to nobody), does not
exist for the caller (``owned_document``). The one edge ``attachments →
rag_spaces`` lives here.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

import structlog
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from src.domains.attachments.repository import AttachmentRepository
from src.domains.rag_spaces.document_access import (
    document_file_path,
    owned_document,
    raise_document_not_found,
)
from src.domains.rag_spaces.models import RAGDocumentStatus
from src.domains.rag_spaces.processing import extract_text
from src.domains.rag_spaces.service import RAGSpaceService
from src.infrastructure.observability.metrics_attachments import attachments_uploaded_total

logger = structlog.get_logger(__name__)

#: The stable code the frontend translates when the document is not `ready`.
DOCUMENT_NOT_READY_CODE = "document_not_ready"


def raise_document_not_ready(document_id: uuid.UUID, doc_status: str) -> NoReturn:
    """409: the document's extraction is not proven yet (or failed)."""
    raise BaseAPIException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": DOCUMENT_NOT_READY_CODE},
        log_event="attachment_knowledge_document_not_ready",
        document_id=str(document_id),
        document_status=doc_status,
    )


def text_is_capped(text: str | None, max_chars: int) -> bool:
    """Whether an extracted text sits AT the cap — the sign it was cut there."""
    return bool(text) and len(text or "") >= max_chars


def _copy_and_extract(
    source: Path, target: Path, content_type: str, max_chars: int
) -> tuple[str, int]:
    """Disk work, off the event loop: copy the file (streamed), extract and cap the text, size it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    text = extract_text(target, content_type)
    return text[:max_chars], target.stat().st_size


async def copy_knowledge_document(
    db: AsyncSession, *, user_id: uuid.UUID, space_id: uuid.UUID, document_id: uuid.UUID
) -> Attachment:
    """Copy one of the person's knowledge documents into their attachments.

    Args:
        db: The request session (committed here).
        user_id: The caller — the space and the document must be theirs.
        space_id: The space the document belongs to (active or not).
        document_id: The document.

    Returns:
        The attachment row, ``ready``, its text extracted.

    Raises:
        BaseAPIException: 404 when the space, the document or its stored file
            is not the caller's; 409 (``document_not_ready``) when the document
            is not ``ready``.
    """
    document = await owned_document(RAGSpaceService(db), space_id, document_id, user_id)
    if document.status != RAGDocumentStatus.READY:
        raise_document_not_ready(document_id, str(document.status))
    source = document_file_path(document)
    if not source.is_file():
        raise_document_not_found(document_id)

    extension = Path(document.filename).suffix
    stored_filename = f"{uuid.uuid4()}{extension}"
    relative_path = f"{user_id}/{stored_filename}"
    target = Path(settings.attachments_storage_path) / relative_path
    extracted_text, file_size = await asyncio.to_thread(
        _copy_and_extract,
        source,
        target,
        document.content_type,
        settings.attachments_max_pdf_text_chars,
    )
    try:
        attachment = await AttachmentRepository(db).create(
            {
                "user_id": user_id,
                "original_filename": document.original_filename,
                "stored_filename": stored_filename,
                "mime_type": document.content_type,
                "file_size": file_size,
                "file_path": relative_path,
                "content_type": AttachmentContentType.DOCUMENT,
                "origin": AttachmentOrigin.UPLOAD.value,
                "extracted_text": extracted_text,
                "status": AttachmentStatus.READY,
                "expires_at": datetime.now(UTC) + timedelta(hours=settings.attachments_ttl_hours),
            }
        )
        await db.commit()
    except Exception:
        # A copy nobody's row points at would outlive every sweep: withdraw it.
        await asyncio.to_thread(target.unlink, True)
        attachments_uploaded_total.labels(
            content_type=AttachmentContentType.DOCUMENT, status="error"
        ).inc()
        raise
    attachments_uploaded_total.labels(
        content_type=AttachmentContentType.DOCUMENT, status="success"
    ).inc()
    logger.info(
        "attachment_copied_from_knowledge_document",
        attachment_id=str(attachment.id),
        user_id=str(user_id),
        space_id=str(space_id),
        document_id=str(document_id),
        mime_type=document.content_type,
        text_chars=len(extracted_text),
        text_capped=text_is_capped(extracted_text, settings.attachments_max_pdf_text_chars),
    )
    return attachment


__all__ = [
    "DOCUMENT_NOT_READY_CODE",
    "copy_knowledge_document",
    "raise_document_not_ready",
    "text_is_capped",
]
