"""Full private sample comparison is streamed; approval exposes only kind and owned counts."""

import json
from hashlib import sha256
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.health_metrics.models import HealthSample


class HealthRemovalSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: str | None
    count: int = Field(ge=0)
    counts_by_kind: dict[str, int]
    digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            "kind": self.kind,
            "samples": self.count,
            "counts_by_kind": dict(self.counts_by_kind),
        }


async def health_removal_snapshot(
    db: AsyncSession, actor_id: UUID, kind: str | None, *, locked: bool = False
) -> HealthRemovalSnapshot:
    columns = tuple(HealthSample.__table__.columns)
    statement = select(*columns).where(HealthSample.user_id == actor_id)
    if kind is not None:
        statement = statement.where(HealthSample.kind == kind)
    statement = statement.order_by(HealthSample.id)
    if locked:
        statement = statement.with_for_update()
    digest = sha256(json.dumps([column.name for column in columns]).encode())
    counts: dict[str, int] = {}
    cursor = await db.stream(statement.execution_options(yield_per=200))
    try:
        async for row in cursor.mappings():
            digest.update(
                json.dumps(dict(row), sort_keys=True, default=str, allow_nan=False).encode()
            )
            digest.update(b"\n")
            counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    finally:
        await cursor.close()
    return HealthRemovalSnapshot(
        kind=kind, count=sum(counts.values()), counts_by_kind=counts, digest=digest.hexdigest()
    )
