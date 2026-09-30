"""The files a skill command wrote become the person's generated files (ADR-327 lot 2).

They land where every file LIA produces lands (ADR-279): an ``attachments``
row of the person, in the gallery, under the same lifetime, shown under the
answer by the chat's own cards. What they ARE is decided here — by their name
AND their first bytes, never by the command — because they are served from
the API's own origin:

- a document or an image the product already shows keeps its type, once its
  content matches it (a page wearing a ``.png`` name is left out);
- a page a skill wrote — Markdown, HTML, SVG, XML — comes back as TEXT: the
  document viewer renders Markdown with remote images (a channel for what the
  command read), and HTML or SVG served inline would run in LIA's origin;
- anything else is named with its reason and left out.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from src.core.config import settings
from src.domains.attachments.models import (
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from src.domains.attachments.repository import AttachmentRepository
from src.domains.attachments.thread_id import conversation_uuid
from src.domains.attachments.urls import attachment_url
from src.domains.document_generation.document_store import PendingDocument, store_pending_document
from src.domains.image_generation.image_store import sanitize_alt_text, store_pending_image
from src.domains.skills.command_bundle import OutputFile
from src.infrastructure.database.errors import database_error_fields
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

__all__ = ["Deliverable", "DeliveredFile", "Delivery", "classify", "deliver_outputs"]

logger = get_logger(__name__)

Family = Literal["document", "image"]

#: Why a file was left out.
SKIP_TYPE_NOT_ALLOWED = "type_not_allowed"
SKIP_CONTENT_MISMATCH = "content_mismatch"
SKIP_EMPTY = "empty"
SKIP_NOT_SAVED = "not_saved"

_ZIP = (b"PK\x03\x04",)
_OFFICE = "application/vnd.openxmlformats-officedocument"

#: Served as what they are: extension → (MIME type, family, accepted signatures).
#: No signature means text, which is served as a download and never sniffed.
_NATIVE: dict[str, tuple[str, Family, tuple[bytes, ...]]] = {
    "pdf": ("application/pdf", "document", (b"%PDF-",)),
    "docx": (f"{_OFFICE}.wordprocessingml.document", "document", _ZIP),
    "xlsx": (f"{_OFFICE}.spreadsheetml.sheet", "document", _ZIP),
    "pptx": (f"{_OFFICE}.presentationml.presentation", "document", _ZIP),
    "csv": ("text/csv", "document", ()),
    "txt": ("text/plain", "document", ()),
    "json": ("application/json", "document", ()),
    "png": ("image/png", "image", (b"\x89PNG\r\n\x1a\n",)),
    "jpg": ("image/jpeg", "image", (b"\xff\xd8\xff",)),
    "jpeg": ("image/jpeg", "image", (b"\xff\xd8\xff",)),
    "gif": ("image/gif", "image", (b"GIF87a", b"GIF89a")),
    "webp": ("image/webp", "image", (b"RIFF",)),
}

#: Pages and sources a skill wrote: handed back as text, never drawn.
_AS_TEXT = frozenset(
    {"md", "markdown", "html", "htm", "svg", "xml", "yaml", "yml", "log", "js", "ts", "py", "sh"}
)
_TEXT = "txt"

_ORIGIN: dict[Family, AttachmentOrigin] = {
    "document": AttachmentOrigin.GENERATED_DOCUMENT,
    "image": AttachmentOrigin.GENERATED_IMAGE,
}
_CONTENT_TYPE: dict[Family, str] = {
    "document": AttachmentContentType.DOCUMENT,
    "image": AttachmentContentType.IMAGE,
}


@dataclass(frozen=True, slots=True)
class Deliverable:
    """A file that may be handed to the person, and as what.

    Attributes:
        name: The name the person downloads (a page gains ``.txt``).
        extension: The stored file's extension, lower-case.
        mime_type: What it is served as.
        family: Where it shows: a document card or an image card.
        data: Its bytes.
    """

    name: str
    extension: str
    mime_type: str
    family: Family
    data: bytes

    @property
    def origin(self) -> AttachmentOrigin:
        """The gallery it belongs to (ADR-279)."""
        return _ORIGIN[self.family]


@dataclass(frozen=True, slots=True)
class DeliveredFile:
    """A file the person now has: its name, size and family."""

    name: str
    size: int
    family: Family


@dataclass(frozen=True, slots=True)
class Delivery:
    """What reached the person, and what did not, with its reason."""

    delivered: tuple[DeliveredFile, ...]
    skipped: tuple[tuple[str, str], ...]


def _signature_matches(data: bytes, extension: str, signatures: tuple[bytes, ...]) -> bool:
    if not signatures:
        return True
    if extension == "webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return data.startswith(signatures)


def classify(file: OutputFile) -> Deliverable | str:
    """What a file the command wrote may be handed back as.

    Args:
        file: The file, under its safe basename.

    Returns:
        The deliverable, or the reason it is left out.
    """
    stem, dot, raw_extension = file.name.rpartition(".")
    extension = raw_extension.lower() if dot and stem else ""
    if not file.data:
        return SKIP_EMPTY
    if extension in _AS_TEXT:
        mime_type, family, _ = _NATIVE[_TEXT]
        return Deliverable(f"{file.name}.{_TEXT}", _TEXT, mime_type, family, file.data)
    if extension not in _NATIVE:
        return SKIP_TYPE_NOT_ALLOWED
    mime_type, family, signatures = _NATIVE[extension]
    if not _signature_matches(file.data, extension, signatures):
        return SKIP_CONTENT_MISMATCH
    return Deliverable(file.name, extension, mime_type, family, file.data)


def _write(root: Path, relative: str, data: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _unlink(root: Path, relatives: Sequence[str]) -> None:
    for relative in relatives:
        # Best effort: the TTL sweep never sees a file with no row.
        with contextlib.suppress(OSError):
            (root / relative).unlink()


async def _file(
    kept: Sequence[Deliverable], user_id: uuid.UUID, conversation_id: str
) -> list[tuple[Deliverable, str, str | None]]:
    """Write the files, then their rows in ONE short session; undo the files on failure.

    Returns:
        ``(deliverable, attachment id, expires_at ISO)`` per file.

    Raises:
        Exception: Whatever the write or the rows raised (files removed first).
    """
    root = Path(settings.attachments_storage_path)
    stored = [f"{user_id}/{uuid.uuid4()}.{item.extension}" for item in kept]
    expires_at = datetime.now(UTC) + timedelta(hours=settings.attachments_ttl_hours)
    written: list[str] = []
    try:
        for item, relative in zip(kept, stored, strict=True):
            await asyncio.to_thread(_write, root, relative, item.data)
            written.append(relative)
        rows = []
        async with get_db_context() as db:
            repository = AttachmentRepository(db)
            for item, relative in zip(kept, stored, strict=True):
                row = await repository.create(
                    {
                        "user_id": user_id,
                        "original_filename": item.name,
                        "stored_filename": Path(relative).name,
                        "mime_type": item.mime_type,
                        "file_size": len(item.data),
                        "file_path": relative,
                        "content_type": _CONTENT_TYPE[item.family],
                        "origin": item.origin.value,
                        "title": item.name,
                        "conversation_id": conversation_uuid(conversation_id),
                        "status": AttachmentStatus.READY,
                        "expires_at": expires_at,
                    }
                )
                expires = row.expires_at.isoformat() if row.expires_at else None
                rows.append((item, str(row.id), expires))
            await db.commit()
    except BaseException:
        # A cancellation too: a file left without its row is swept by nothing.
        await asyncio.shield(asyncio.to_thread(_unlink, root, written))
        raise
    return rows


def _show(conversation_id: str, item: Deliverable, attachment_id: str, expires: str | None) -> None:
    """Queue the chat's own card under the answer (ADR-226, ADR-279)."""
    url = attachment_url(attachment_id)
    if item.family == "image":
        store_pending_image(
            conversation_id, url=url, alt_text=sanitize_alt_text(item.name), expires_at=expires
        )
        return
    store_pending_document(
        conversation_id,
        PendingDocument(
            url=url,
            filename=item.name,
            doc_type=item.extension,
            size_bytes=len(item.data),
            expires_at=expires,
        ),
    )


async def deliver_outputs(
    files: Sequence[OutputFile], *, user_id: uuid.UUID, conversation_id: str
) -> Delivery:
    """Hand the command's files to the person: stored, filed, shown.

    Args:
        files: What the command wrote under ``out/``, already bounded.
        user_id: The person who owns them.
        conversation_id: The conversation the cards show in.

    Returns:
        What reached the person, and every file that did not, with its reason.
    """
    kept: list[Deliverable] = []
    skipped: list[tuple[str, str]] = []
    for file in files:
        verdict = classify(file)
        if isinstance(verdict, str):
            skipped.append((file.name, verdict))
        else:
            kept.append(verdict)
    if not kept:
        return Delivery(delivered=(), skipped=tuple(skipped))
    try:
        rows = await _file(kept, user_id, conversation_id)
    except Exception as exc:
        # Its facts, never its text (ADR-317): a database error quotes rows.
        logger.error(
            "skill_command_outputs_not_saved",
            user_id=str(user_id),
            count=len(kept),
            error_type=type(exc).__name__,
            **database_error_fields(exc),
        )
        skipped.extend((item.name, SKIP_NOT_SAVED) for item in kept)
        return Delivery(delivered=(), skipped=tuple(skipped))
    for item, attachment_id, expires in rows:
        _show(conversation_id, item, attachment_id, expires)
    logger.info(
        "skill_command_outputs_delivered",
        user_id=str(user_id),
        delivered=len(rows),
        skipped=len(skipped),
    )
    return Delivery(
        delivered=tuple(
            DeliveredFile(name=item.name, size=len(item.data), family=item.family)
            for item, _, _ in rows
        ),
        skipped=tuple(skipped),
    )
