"""Manual reactivation owns the source reset and invalidates superseded extraction runs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.core.i18n_api_messages import APIMessages
from src.domains.interests.management_commands import (
    get_managed_interest,
    lock_interest_actor,
    preview_interest_update,
)
from src.domains.interests.management_schemas import InterestConfiguration
from src.domains.interests.models import InterestStatus, UserInterest
from src.domains.interests.repository import InterestRepository
from src.domains.interests.schemas import InterestUpdate
from src.domains.users.extraction_consent import invalidate_extractions


class InterestReactivationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    configuration: InterestConfiguration
    status: InterestStatus
    subject: str | None
    last_mentioned_at: datetime
    last_notified_at: datetime | None
    dormant_since: datetime | None


def interest_reactivation_snapshot(row: UserInterest) -> InterestReactivationSnapshot:
    return InterestReactivationSnapshot(
        id=row.id,
        configuration=preview_interest_update(row, InterestUpdate()),
        status=row.status,
        subject=row.subject,
        last_mentioned_at=row.last_mentioned_at,
        last_notified_at=row.last_notified_at,
        dormant_since=row.dormant_since,
    )


def require_dormant_interest(row: UserInterest) -> None:
    if row.status != InterestStatus.DORMANT.value:
        raise ResourceConflictError("interest", detail=APIMessages.interest_not_dormant())


async def reactivate_managed_interest(
    db: AsyncSession,
    actor_id: UUID,
    identity: UUID,
    *,
    expected: InterestReactivationSnapshot | None = None,
) -> UserInterest:
    actor = await lock_interest_actor(db, actor_id)
    row = await get_managed_interest(db, actor_id, identity, lock=True)
    if expected is not None and interest_reactivation_snapshot(row) != expected:
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})
    require_dormant_interest(row)
    invalidate_extractions(actor)
    return await InterestRepository(db).reactivate(row)
