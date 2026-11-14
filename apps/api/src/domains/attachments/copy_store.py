"""How a COPY enters the attachments store — its file, its text, its row.

Three doors put a copy of something the person already holds into a message:
a knowledge-space document (ADR-295), a kept answer and a generated file
(2026-10-24). Each copy is an UPLOAD (ADR-279): a conversation reset removes
it, the TTL sweep expires it, the original is never touched. They share the
disk work — a fresh UUID name, a streamed copy or a written text, the text
extracted through the knowledge spaces' pipeline under the attachments' cap —
and the durable publication protocol shared with ordinary uploads. The row
owns the path before writing; failed writes remain recorded until removal.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionRevoked
from src.core.conversation_target import ConversationRef
from src.domains.attachments.file_contracts import FileWriteResult, UploadMetadata
from src.domains.attachments.file_publication import publish_file
from src.domains.attachments.models import Attachment
from src.domains.attachments.publication_errors import raise_retired_file_source
from src.domains.rag_spaces.processing import extract_text
from src.infrastructure.observability.metrics_attachments import attachments_uploaded_total


def copy_and_extract(
    source: Path, target: Path, content_type: str | None, max_chars: int
) -> tuple[str | None, int]:
    """Disk work, off the event loop: copy (streamed), extract and cap the text, size it.

    Args:
        source: The file copied.
        target: Where the copy goes.
        content_type: The MIME type to extract text by; None for an image.
        max_chars: The attachments' text cap.

    Returns:
        ``(capped text or None, copied size)``.

    Raises:
        Exception: Copy/extraction failure; the publisher retains the cleanup intent.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    text = extract_text(target, content_type)[:max_chars] if content_type else None
    return text, target.stat().st_size


def write_text_copy(target: Path, text: str) -> int:
    """Disk work, off the event loop: write a text the copy IS, size it.

    Raises:
        OSError: The write failed; the publisher retains the cleanup intent.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target.stat().st_size


async def publish_copy(
    db: AsyncSession,
    *,
    user_id: UUID,
    metadata: UploadMetadata,
    target: ConversationRef | None,
    write: Callable[[Path], FileWriteResult],
) -> Attachment:
    """Use the upload's durable, joined publication and record the copy's outcome."""
    try:
        attachment = await publish_file(
            db, owner_id=user_id, metadata=metadata, target=target, write=write
        )
    except ExecutionRevoked as exc:
        attachments_uploaded_total.labels(content_type=metadata.content_type, status="error").inc()
        raise_retired_file_source(exc)
    except Exception:
        attachments_uploaded_total.labels(content_type=metadata.content_type, status="error").inc()
        raise
    attachments_uploaded_total.labels(content_type=metadata.content_type, status="success").inc()
    return attachment


__all__ = [
    "copy_and_extract",
    "publish_copy",
    "write_text_copy",
]
