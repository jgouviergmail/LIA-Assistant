"""The person's own files, attached to a message they write (ADR-369).

What they uploaded and what LIA produced for them, while alive
(``attachments.attachable_queries``) — never the device's file system (spec,
phase 1). A selection is attached WHOLE or refused: an id gone since it was
offered (deleted, expired, swept from the disk) refuses the message
(``item_gone``), and so do files whose total passes what the provider carries
(``too_large`` with the bound) — a message leaves whole or not at all. The
listing pages the files with their exact total (ADR-185). The rows are read on
a short session, closed before anything is sent (ADR-304); the bytes off the
event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from src.core.config import settings
from src.domains.attachments.attachable_queries import build_attachable_statement
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.errors import ITEM_GONE, TOO_LARGE, refuse
from src.domains.workbench.schemas.mail_compose import AttachableFile, AttachablePage
from src.infrastructure.database.session import get_db_context
from src.infrastructure.email.outgoing import OutgoingAttachment


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
