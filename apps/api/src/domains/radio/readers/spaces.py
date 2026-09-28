"""Documents newly ready in the listener's knowledge spaces, for the personal corner.

A document the person added to one of their knowledge spaces in the last few
days — and that indexing has READY — may be mentioned: « three days ago a new
document joined your space… ». Only the spaces the person made themselves: a
space another domain manages by its role (meetings' minutes, kept answers —
ADR-258, ADR-291) repeats what those sources already say.

Read through the spaces repository's own « ready documents of every space »
query (the composer's « + » list), newest first — the end kept by the read.
The read opens its own short session and closes it before returning (ADR-304).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Final, Protocol
from uuid import UUID

from src.domains.radio.facts import FactKind, Sensitivity, local_time_text
from src.domains.radio.personal import MAX_PER_SOURCE, PersonalDraft, PersonalSource
from src.domains.rag_spaces.repository import RAGDocumentRepository
from src.infrastructure.database.session import get_db_context

#: How far back a document is still « new ».
DOCUMENT_RECENT_DAYS: Final[int] = 3
#: How many of the newest ready documents are read to find them.
_SCAN_ROWS: Final[int] = 10


@dataclass(frozen=True, slots=True)
class NewDocument:
    """A document newly ready in a space the person made.

    Attributes:
        id: The document.
        name: Its display name.
        space: The space's name.
        added_at: When it was added (aware).
    """

    id: UUID
    name: str
    space: str
    added_at: datetime


class SpaceRow(Protocol):
    """The columns of a space the radio reads."""

    @property
    def name(self) -> str: ...

    @property
    def kind(self) -> str | None: ...


class DocumentRow(Protocol):
    """The columns of a ready document the radio reads."""

    @property
    def id(self) -> UUID: ...

    @property
    def original_filename(self) -> str: ...

    @property
    def created_at(self) -> datetime: ...

    @property
    def space(self) -> SpaceRow: ...


def new_documents(rows: Sequence[DocumentRow], *, since: datetime) -> list[NewDocument]:
    """The documents added after ``since`` to a space the person made, in the order given."""
    return [
        NewDocument(
            id=row.id, name=row.original_filename, space=row.space.name, added_at=row.created_at
        )
        for row in rows
        if row.created_at >= since and row.space.kind is None
    ]


def document_drafts(documents: Sequence[NewDocument], *, tz: tzinfo) -> list[PersonalDraft]:
    """The new documents as drafts."""
    return [
        PersonalDraft(
            FactKind.SPACE,
            f'New in the knowledge space "{document.space}": "{document.name}", added on '
            f"{local_time_text(document.added_at.astimezone(tz))}",
            f"space_document:{document.id}",
            Sensitivity.PERSONAL,
        )
        for document in documents
    ]


async def read_spaces(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The documents newly ready in the spaces the listener made.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    since = now - timedelta(days=DOCUMENT_RECENT_DAYS)
    async with get_db_context() as db:
        rows, _total = await RAGDocumentRepository(db).search_ready_for_user(
            user_id, needle=None, limit=_SCAN_ROWS, offset=0
        )
        documents = new_documents(rows, since=since)
    return document_drafts(documents[: MAX_PER_SOURCE[PersonalSource.SPACES]], tz=tz)


__all__ = [
    "DOCUMENT_RECENT_DAYS",
    "DocumentRow",
    "NewDocument",
    "SpaceRow",
    "document_drafts",
    "new_documents",
    "read_spaces",
]
