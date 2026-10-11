"""UI and native erasure share owner-first source deletion and verified acknowledgement."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.health_metrics.management_lock import lock_health_manager
from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.removal_snapshot import (
    HealthRemovalSnapshot,
    health_removal_snapshot,
)
from src.domains.health_metrics.schemas import HealthMetricDeleteResponse
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.users.preference_cas import PreferenceWriteReceipt


class HealthRemovalCompletionUnknown(RuntimeError):
    """A missing commit acknowledgement cannot establish sample erasure."""


async def remove_health_samples(
    db: AsyncSession,
    actor_id: UUID,
    kind: str | None,
    *,
    expected: HealthRemovalSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> HealthMetricDeleteResponse:
    await lock_health_manager(db, actor_id)
    if check is not None:
        await check()
    observed = await health_removal_snapshot(db, actor_id, kind, locked=True)
    if expected is not None and expected != observed:
        raise ResourceConflictError("health_samples", detail={"error_code": "STALE_STATE"})
    service = HealthMetricsService(db)
    count = (
        await service.delete_all(actor_id)
        if kind is None
        else await service.delete_by_kind(actor_id, kind)
    )
    remaining = (
        select(func.count()).select_from(HealthSample).where(HealthSample.user_id == actor_id)
    )
    if kind is not None:
        remaining = remaining.where(HealthSample.kind == kind)
    await db.flush()
    if count != observed.count or await db.scalar(remaining) != 0:
        raise ValueError("Source sample erasure was not observed")
    result = HealthMetricDeleteResponse.model_validate(
        {"scope": "all" if kind is None else "kind", "kind": kind, "affected_rows": count}
    )
    if check is not None:
        await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise HealthRemovalCompletionUnknown from exc
    if receipt is not None:
        receipt.committed, receipt.no_op = True, count == 0
        receipt.values = {"health_samples_to_delete": result.model_dump(mode="json")}
    return result
