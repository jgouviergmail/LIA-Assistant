"""Exact deletion scopes are complete, owned and streamed outside model context."""

import json
from hashlib import sha256
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import String, cast, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.journals.evidence_models import JournalEvidenceEvent
from src.domains.journals.models import JournalEntry
from src.domains.journals.schemas import JournalEntryResponse
from src.domains.users.models import User

JOURNAL_EXPOSURE_FIELDS = frozenset({"injection_count", "last_injected_at", "updated_at"})


def _semantic_values(
    model: type[JournalEntry] | type[JournalEvidenceEvent], row: RowMapping
) -> dict[str, Any]:
    """Exposure bookkeeping is not changed journal meaning or deletion scope."""
    ignored = JOURNAL_EXPOSURE_FIELDS if model is JournalEntry else frozenset()
    return {
        column.name: row[column.name]
        for column in model.__table__.columns
        if column.name not in ignored
    }


class JournalRemovalSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entry_id: UUID | None
    entries: int = Field(ge=0, strict=True)
    evidence_events: int = Field(ge=0, strict=True)
    total_chars: int = Field(ge=0, strict=True)
    entry: JournalEntryResponse | None = None
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            "entries": self.entries,
            "evidence_events": self.evidence_events,
            "total_chars": self.total_chars,
            "entry": self.entry.model_dump(mode="json") if self.entry else None,
        }

    def matches(self, current: JournalRemovalSnapshot) -> bool:
        return (
            self.entry_id,
            self.entries,
            self.evidence_events,
            self.total_chars,
            self.digest,
        ) == (
            current.entry_id,
            current.entries,
            current.evidence_events,
            current.total_chars,
            current.digest,
        )


async def journal_removal_snapshot(
    db: AsyncSession, actor: User, entry_id: UUID | None, *, locked: bool = False
) -> JournalRemovalSnapshot:
    filters = [JournalEntry.user_id == actor.id]
    if entry_id is not None:
        filters.append(JournalEntry.id == entry_id)
    statements = (
        (
            JournalEntry,
            select(
                *(
                    (
                        cast(column, String).label(column.name)
                        if isinstance(column.type, Vector)
                        else column
                    )
                    for column in JournalEntry.__table__.columns
                )
            )
            .where(*filters)
            .order_by(JournalEntry.id),
        ),
        (
            JournalEvidenceEvent,
            select(*JournalEvidenceEvent.__table__.columns)
            .where(
                JournalEvidenceEvent.journal_entry_id.in_(select(JournalEntry.id).where(*filters))
            )
            .order_by(JournalEvidenceEvent.id),
        ),
    )
    digest = sha256()
    digest.update(
        json.dumps(
            {
                name: getattr(actor, name)
                for name in (
                    "journal_revision",
                    "journal_portrait_full",
                    "journal_portrait_brief",
                    "journal_portrait_compiled_at",
                    "journal_portrait_sources",
                )
            },
            sort_keys=True,
            default=str,
            allow_nan=False,
        ).encode()
    )
    counts: list[int] = []
    total_chars = 0
    entry = None
    for model, statement in statements:
        digest.update(
            json.dumps([model.__tablename__, list(model.__table__.columns.keys())]).encode()
        )
        if locked:
            statement = statement.with_for_update()
        cursor = await db.stream(statement.execution_options(yield_per=200))
        count = 0
        try:
            async for row in cursor.mappings():
                digest.update(
                    json.dumps(
                        _semantic_values(model, row),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                        allow_nan=False,
                    ).encode()
                )
                digest.update(b"\n")
                count += 1
                if model is JournalEntry:
                    total_chars += row["char_count"]
                    if entry_id is not None:
                        entry = JournalEntryResponse.model_validate(row)
        finally:
            await cursor.close()
        counts.append(count)
    if entry_id is not None and counts[0] != 1:
        raise ResourceNotFoundError("journal_entry", entry_id)
    return JournalRemovalSnapshot(
        entry_id=entry_id,
        entries=counts[0],
        evidence_events=counts[1],
        total_chars=total_chars,
        entry=entry,
        digest=digest.hexdigest(),
    )
