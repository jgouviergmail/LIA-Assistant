"""How a COPY enters the attachments store — its file, its text, its row.

Three doors put a copy of something the person already holds into a message:
a knowledge-space document (ADR-295), a kept answer and a generated file
(2026-10-24). Each copy is an UPLOAD (ADR-279): a conversation reset removes
it, the TTL sweep expires it, the original is never touched. They share the
disk work — a fresh UUID name, a streamed copy or a written text, the text
extracted through the knowledge spaces' pipeline under the attachments' cap —
the reads ended before that disk work, and the commit that withdraws a file no
row points at.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.domains.rag_spaces.processing import extract_text
from src.infrastructure.observability.metrics_attachments import attachments_uploaded_total

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.attachments.models import Attachment
    from src.domains.attachments.repository import AttachmentRepository


def copy_target(storage_root: str, user_id: uuid.UUID, extension: str) -> tuple[str, str, Path]:
    """A fresh place for a copy: ``(stored filename, relative path, absolute path)``."""
    stored_filename = f"{uuid.uuid4()}{extension}"
    relative_path = f"{user_id}/{stored_filename}"
    return stored_filename, relative_path, Path(storage_root) / relative_path


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
        Exception: Whatever the copy or the reader raised — the copy withdrawn
            first, since no row will ever point at it.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(source, target)
        text = extract_text(target, content_type)[:max_chars] if content_type else None
        return text, target.stat().st_size
    except Exception:
        target.unlink(missing_ok=True)
        raise


def write_text_copy(target: Path, text: str) -> int:
    """Disk work, off the event loop: write a text the copy IS, size it.

    Raises:
        OSError: The write failed — what it left withdrawn first.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(text, encoding="utf-8")
        return target.stat().st_size
    except OSError:
        target.unlink(missing_ok=True)
        raise


async def run_after_reads[T](db: AsyncSession, work: Callable[..., T], *args: Any) -> T:
    """Run a copy's disk work in a thread once the reads that found its source ended.

    Copying a file and extracting its text can take seconds: the source's read
    would otherwise keep its transaction idle — and a pooled connection held —
    the whole time. A session lives no longer than the queries it serves.

    Args:
        db: The request session the source was read on (committed here).
        work: ``copy_and_extract`` or ``write_text_copy``.
        *args: Its arguments.

    Returns:
        What ``work`` returned.
    """
    await db.commit()
    return await asyncio.to_thread(work, *args)


async def record_copy(
    repo: AttachmentRepository, db: AsyncSession, target: Path, row: dict[str, Any]
) -> Attachment:
    """Create the copy's row and commit; a file no row points at is withdrawn.

    Args:
        repo: The attachments repository on ``db``.
        db: The request session (committed here).
        target: The copied file.
        row: The attachment's columns.

    Returns:
        The committed row.
    """
    content_type = row["content_type"]
    try:
        attachment = await repo.create(row)
        await db.commit()
    except Exception:
        # A copy nobody's row points at would outlive every sweep: withdraw it.
        await asyncio.to_thread(target.unlink, True)
        attachments_uploaded_total.labels(content_type=content_type, status="error").inc()
        raise
    attachments_uploaded_total.labels(content_type=content_type, status="success").inc()
    return attachment


__all__ = [
    "copy_and_extract",
    "copy_target",
    "record_copy",
    "run_after_reads",
    "write_text_copy",
]
