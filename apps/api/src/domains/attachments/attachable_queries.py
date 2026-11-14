"""The files a person may attach to a message they write (ADR-369).

Their OWN files — what they uploaded and what LIA produced for them — while
they are alive: a file past its deadline, or one the cleanup marked expired, is
neither offered nor attached (a kept file has no deadline, ADR-319). The
listing and its exact total come from the SAME ``WHERE`` (ADR-185), the needle
is data (``escape_like``), and the order is total (the id breaks every tie).
A selection by ids or by names reads through the same filter, so a foreign,
expired or unknown one simply finds no row.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final

from sqlalchemy import Select, func, or_, select

from src.core.sql_search import escape_like
from src.domains.attachments.models import Attachment, AttachmentOrigin, AttachmentStatus
from src.domains.attachments.origin import GENERATED_ORIGINS

#: Where an attachable file comes from: the person's uploads and LIA's files for them.
ATTACHABLE_ORIGINS: Final = frozenset({*GENERATED_ORIGINS, AttachmentOrigin.UPLOAD})


def build_attachable_statement(
    user_id: uuid.UUID,
    *,
    now: datetime,
    query: str | None = None,
    ids: Sequence[uuid.UUID] | None = None,
    names: Sequence[str] | None = None,
    count: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> Select[Any]:
    """The account's live attachable files, or the exact count of them.

    Args:
        user_id: Whose files.
        now: The instant a deadline is compared with.
        query: A needle matched against the title and the original name.
        ids: Only these files (a selection to attach).
        names: Only the files of these exact names, title or original name, whatever the case.
        count: True for the total over the WHOLE filtered set.
        limit: Page size (none: every row).
        offset: Page start.

    Returns:
        The statement.
    """
    columns = func.count() if count else Attachment
    statement = select(columns).where(
        Attachment.user_id == user_id,
        Attachment.origin.in_([origin.value for origin in ATTACHABLE_ORIGINS]),
        Attachment.status == AttachmentStatus.READY,
        or_(Attachment.expires_at.is_(None), Attachment.expires_at > now),
    )
    if ids is not None:
        statement = statement.where(Attachment.id.in_(list(ids)))
    if names is not None:
        lowered = [name.lower() for name in names]
        statement = statement.where(
            or_(
                func.lower(Attachment.title).in_(lowered),
                func.lower(Attachment.original_filename).in_(lowered),
            )
        )
    needle = (query or "").strip()
    if needle:
        pattern = f"%{escape_like(needle.lower())}%"
        statement = statement.where(
            or_(
                func.lower(Attachment.title).like(pattern, escape="\\"),
                func.lower(Attachment.original_filename).like(pattern, escape="\\"),
            )
        )
    if count:
        return statement
    ordered = statement.order_by(Attachment.created_at.desc(), Attachment.id.desc())
    return ordered.limit(limit).offset(offset) if limit is not None else ordered.offset(offset)
