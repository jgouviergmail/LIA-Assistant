"""Complete current-memory exports reuse the UI display projection and its privacy boundary."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import aclosing
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.management_bulk import iter_owned_memories
from src.domains.memories.read_models import build_retention_config, memory_to_response
from src.domains.memories.schemas import MemoryResponse


class MemoryCSVExportRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    content: str
    category: str
    emotional_weight: int
    trigger_topic: str
    usage_nuance: str
    importance: float
    pinned: str
    usage_count: int
    last_accessed_at: str
    created_at: str
    updated_at: str


def memory_csv_export_record(memory: MemoryResponse) -> MemoryCSVExportRecord:
    return MemoryCSVExportRecord(
        id=memory.id,
        content=memory.content,
        category=memory.category,
        emotional_weight=memory.emotional_weight,
        trigger_topic=memory.trigger_topic,
        usage_nuance=memory.usage_nuance,
        importance=memory.importance,
        pinned=str(memory.pinned),
        usage_count=memory.usage_count,
        last_accessed_at=memory.last_accessed_at.isoformat() if memory.last_accessed_at else "",
        created_at=memory.created_at.isoformat() if memory.created_at else "",
        updated_at=memory.updated_at.isoformat() if memory.updated_at else "",
    )


async def memory_export_rows(
    db: AsyncSession,
    actor_id: UUID,
    format: Literal["csv", "json"],
    observed_at: datetime,
    for_update: bool = False,
) -> AsyncGenerator[Mapping[str, object]]:
    policy = build_retention_config()
    async with aclosing(
        iter_owned_memories(db, actor_id, for_update=for_update, include_invalidated=False)
    ) as rows:
        async for row in rows:
            memory = memory_to_response(row, observed_at, policy)
            record = memory_csv_export_record(memory) if format == "csv" else memory
            yield record.model_dump(mode="json")
