"""The person's own files, attached to a message they write (ADR-369).

What they uploaded and what LIA produced for them, while alive
(``attachments.attachable_queries``), and a file of their drive, read when the
message leaves. A file of the device is kept first, as any upload is and under
the same deadline: the chat's door takes what a model reads, a message carries
anything, so its type is what its bytes say and only then what its form
declares. A selection is attached WHOLE or refused: an id gone since it was
offered (deleted, expired, swept from the disk) refuses the message
(``item_gone``), and so do files whose total passes what the provider carries
(``too_large`` with the bound) — a message leaves whole or not at all. The
listing pages the files with their exact total (ADR-185). The rows are read on
a short session, closed before anything is sent (ADR-304); the bytes off the
event loop.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final
from uuid import UUID

from src.core.config import settings
from src.core.content_disposition import served_media_type
from src.domains.attachments.attachable_queries import build_attachable_statement
from src.domains.attachments.file_contracts import FileWriteResult, UploadMetadata
from src.domains.attachments.file_publication import publish_file
from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
)
from src.domains.workbench import files_service
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.errors import INVALID_REQUEST, ITEM_GONE, TOO_LARGE, refuse
from src.domains.workbench.schemas.files import DownloadQuery
from src.domains.workbench.schemas.mail_compose import AttachableFile, AttachablePage
from src.infrastructure.database.session import get_db_context
from src.infrastructure.email.outgoing import OutgoingAttachment

#: What a file whose form named nothing is called, as the chat's door calls it.
UNNAMED_FILE: Final = "unnamed"
_CONTROL_CHARACTERS: Final = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class DeviceFile:
    """A file of the person's device, as its form brought it: nothing here is vouched for."""

    filename: str
    declared_type: str
    data: bytes


async def list_attachable(user_id: UUID, *, query: str | None, offset: int) -> AttachablePage:
    """One page of the person's live files, newest first, and their exact total."""
    now = datetime.now(UTC)
    async with get_db_context() as db:
        page = await db.execute(
            build_attachable_statement(
                user_id, now=now, query=query, limit=listing_page_size(), offset=offset
            )
        )
        rows = list(page.scalars().all())
        counted = await db.execute(
            build_attachable_statement(user_id, now=now, query=query, count=True)
        )
        total = int(counted.scalar_one())
    reached = offset + len(rows)
    return AttachablePage(
        items=[_file(row) for row in rows],
        total=total,
        next_offset=reached if rows and reached < total else None,
    )


async def outgoing_files(
    user_id: UUID, ids: Sequence[UUID], *, max_bytes: int
) -> tuple[OutgoingAttachment, ...]:
    """The selected files, read whole, in the selection's order.

    Raises:
        BaseAPIException: ``item_gone`` when one is not (or no longer) the
            person's live file; ``too_large`` with ``max_bytes`` when their
            total passes what the provider carries.
    """
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return ()
    async with get_db_context() as db:
        found = await db.execute(
            build_attachable_statement(user_id, now=datetime.now(UTC), ids=wanted)
        )
        rows = {row.id: row for row in found.scalars().all()}
    if len(rows) != len(wanted):
        refuse(ITEM_GONE)
    if sum(int(row.file_size) for row in rows.values()) > max_bytes:
        refuse(TOO_LARGE, max_bytes=max_bytes)
    try:
        return tuple([await _read(rows[file_id]) for file_id in wanted])
    except FileNotFoundError:
        # The cleanup took it between the check and the read.
        refuse(ITEM_GONE)


async def drive_files(
    user_id: UUID, ids: Sequence[str], *, max_bytes: int
) -> tuple[OutgoingAttachment, ...]:
    """Files of the person's drive, read whole, in the selection's order.

    One at a time, under the account's one transfer; a Google document leaves as its first
    export. Reading stops the moment their total passes what the provider carries.

    Raises:
        BaseAPIException: ``too_large`` with ``max_bytes``; what the drive refuses otherwise.
    """
    read: list[OutgoingAttachment] = []
    total = 0
    for file_id in dict.fromkeys(ids):
        file = await files_service.download_file(user_id, DownloadQuery(id=file_id))
        total += len(file.data)
        if total > max_bytes:
            refuse(TOO_LARGE, max_bytes=max_bytes)
        read.append(OutgoingAttachment(file.filename, file.mime_type, file.data))
    return tuple(read)


async def carried_files(
    user_id: UUID, own_ids: Sequence[UUID], drive_ids: Sequence[str], *, max_bytes: int
) -> tuple[OutgoingAttachment, ...]:
    """A message's files, the person's own then their drive's, within what the provider carries.

    Raises:
        BaseAPIException: See :func:`outgoing_files` and :func:`drive_files`.
    """
    own = await outgoing_files(user_id, own_ids, max_bytes=max_bytes)
    if not drive_ids:
        return own
    room = max_bytes - sum(len(file.data) for file in own)
    return own + await drive_files(user_id, drive_ids, max_bytes=room)


async def keep_device_file(user_id: UUID, file: DeviceFile) -> AttachableFile:
    """Keep a file of the device for a message, as the person's upload.

    Its path is durably owned before writing, using the chat upload's publication
    protocol. It remains unbound to a discussion until a turn accepts it.

    Raises:
        BaseAPIException: ``invalid_request`` for a name past what can be kept.
    """
    name = _kept_name(file.filename)
    if len(name) > Attachment.original_filename.type.length:
        refuse(INVALID_REQUEST)
    mime_type = _type_of(file)

    def write(path: Path) -> FileWriteResult:
        _write(path, file.data)
        return FileWriteResult(len(file.data))

    async with get_db_context() as db:
        row = await publish_file(
            db,
            owner_id=user_id,
            target=None,
            metadata=UploadMetadata(name, mime_type, _category_of(mime_type), ".bin"),
            write=write,
        )
        return _file(row)


def _kept_name(sent: str) -> str:
    """A file's own name: never a path, and nothing a mail header could be split on."""
    name = PurePosixPath(sent.replace("\\", "/")).name
    return _CONTROL_CHARACTERS.sub("", name).strip() or UNNAMED_FILE


def _type_of(file: DeviceFile) -> str:
    """What the bytes say they are, else what the form declares, when well formed."""
    import filetype  # type: ignore[import-untyped]

    kind = filetype.guess(file.data)
    return str(kind.mime) if kind else served_media_type(file.declared_type)


def _category_of(mime_type: str) -> str:
    return (
        AttachmentContentType.IMAGE
        if mime_type.startswith("image/")
        else AttachmentContentType.DOCUMENT
    )


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


async def _read(row: Any) -> OutgoingAttachment:
    path = Path(settings.attachments_storage_path) / str(row.file_path)
    data = await asyncio.to_thread(path.read_bytes)
    return OutgoingAttachment(str(row.original_filename), str(row.mime_type), data)


def _file(row: Any) -> AttachableFile:
    return AttachableFile(
        id=row.id,
        filename=str(row.title or row.original_filename),
        mime_type=str(row.mime_type),
        size=int(row.file_size),
        origin=str(row.origin),
        expires_at=row.expires_at,
    )
