"""Finite reviewed sources share transfer mechanics without sharing resource authority."""

from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.management_export_spec import (
    INTEREST_EXPORT_OPERATION,
    JOURNAL_EXPORT_OPERATION,
    MEMORY_EXPORT_OPERATION,
)
from src.domains.agents.application.operation_spec import ApplicationOperationSpec
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.interests.management_commands import lock_interest_actor
from src.domains.interests.management_export import InterestExportRecord, iter_interest_export
from src.domains.journals.management_export import (
    JOURNAL_CSV_FIELDS,
    journal_export_metadata,
    journal_export_rows,
    lock_journal_export_actor,
)
from src.domains.journals.schemas import JournalEntryResponse
from src.domains.memories.management_commands import lock_memory_actor
from src.domains.memories.management_export import MemoryCSVExportRecord, memory_export_rows
from src.domains.memories.schemas import MemoryResponse
from src.domains.users.models import User

ExportRows = Callable[
    [AsyncSession, UUID, Literal["csv", "json"], datetime, bool],
    AsyncGenerator[Mapping[str, object]],
]
ExportMetadata = Callable[
    [AsyncSession, UUID, Literal["csv", "json"], datetime], Awaitable[Mapping[str, object]]
]


async def _interest_rows(
    db: AsyncSession,
    actor_id: UUID,
    format: Literal["csv", "json"],
    observed_at: datetime,
    for_update: bool,
) -> AsyncGenerator[Mapping[str, object]]:
    async with aclosing(
        iter_interest_export(db, actor_id, observed_at=observed_at, for_update=for_update)
    ) as rows:
        async for row in rows:
            yield row.model_dump(mode="json")


@dataclass(frozen=True)
class ManagementExportSource:
    collection: Literal["interests", "memories", "journals"]
    operation: ApplicationOperationSpec
    digest_seed: bytes
    csv_fields: tuple[str, ...]
    rows: ExportRows
    lock_actor: Callable[[AsyncSession, UUID], Awaitable[User]]
    json_model: type[BaseModel]
    json_collection: str | None = None
    metadata: ExportMetadata | None = None

    async def require_available(self, db: AsyncSession) -> None:
        for capability in self.operation.required_capabilities:
            await require_capability_fresh(db, capability)

    async def export_metadata(
        self,
        db: AsyncSession,
        actor_id: UUID,
        format: Literal["csv", "json"],
        observed_at: datetime,
        count: int,
    ) -> Mapping[str, object]:
        if self.metadata is not None:
            return await self.metadata(db, actor_id, format, observed_at)
        return {
            "user_id": str(actor_id),
            "exported_at": observed_at.isoformat(),
            f"total_{self.collection}": count,
        }

    def digest_prefix(self, format: Literal["csv", "json"]) -> bytes:
        contract = {
            "format": format,
            "columns": self.csv_fields,
            "json_schema": self.json_model.model_json_schema() if format == "json" else None,
        }
        return self.digest_seed + bytes.fromhex(payload_digest(contract))


MANAGEMENT_EXPORT_SOURCES = {
    "interests.export": ManagementExportSource(
        "interests",
        INTEREST_EXPORT_OPERATION,
        b"lia-interest-export-v1",
        tuple(InterestExportRecord.model_fields),
        _interest_rows,
        lock_interest_actor,
        InterestExportRecord,
    ),
    "memories.export": ManagementExportSource(
        "memories",
        MEMORY_EXPORT_OPERATION,
        b"lia-memory-export-v1",
        tuple(MemoryCSVExportRecord.model_fields),
        memory_export_rows,
        lock_memory_actor,
        MemoryResponse,
    ),
    "journals.export": ManagementExportSource(
        "journals",
        JOURNAL_EXPORT_OPERATION,
        b"lia-journal-export-v1",
        JOURNAL_CSV_FIELDS,
        journal_export_rows,
        lock_journal_export_actor,
        JournalEntryResponse,
        json_collection="entries",
        metadata=journal_export_metadata,
    ),
}
