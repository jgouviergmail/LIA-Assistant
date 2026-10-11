"""Complete owned export projection; embeddings and internal provenance never leave it."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import aclosing
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.interests.management_bulk import iter_owned_interests
from src.domains.interests.models import UserInterest
from src.domains.interests.repository import InterestRepository


async def interest_export_rows(
    db: AsyncSession, actor_id: UUID, observed_at: datetime
) -> AsyncGenerator[Mapping[str, object]]:
    async with aclosing(iter_interest_export(db, actor_id, observed_at=observed_at)) as records:
        async for record in records:
            yield record.model_dump(mode="json")


class InterestExportRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    id: str
    topic: str
    category: str
    status: str
    positive_signals: int
    negative_signals: int
    weight: float
    last_mentioned_at: str
    last_notified_at: str
    created_at: str


def interest_export_record(
    row: UserInterest, repo: InterestRepository, observed_at: datetime
) -> InterestExportRecord:
    return InterestExportRecord(
        id=str(row.id),
        topic=row.topic,
        category=row.category,
        status=row.status,
        positive_signals=row.positive_signals,
        negative_signals=row.negative_signals,
        weight=round(repo.calculate_effective_weight(row, now=observed_at), 4),
        last_mentioned_at=row.last_mentioned_at.isoformat(),
        last_notified_at=row.last_notified_at.isoformat() if row.last_notified_at else "",
        created_at=row.created_at.isoformat(),
    )


async def iter_interest_export(
    db: AsyncSession,
    actor_id: UUID,
    *,
    observed_at: datetime | None = None,
    for_update: bool = False,
) -> AsyncGenerator[InterestExportRecord]:
    """One cursor and clock cover every status; allocation is bounded by the source batch."""
    repo = InterestRepository(db)
    now = observed_at or datetime.now(UTC)
    async with aclosing(iter_owned_interests(db, actor_id, for_update=for_update)) as rows:
        async for row in rows:
            yield interest_export_record(row, repo, now)
