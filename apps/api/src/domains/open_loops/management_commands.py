"""Owned public comparison facts and shared source transitions for management."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.open_loops.schemas import CloseLoopRequest, UpdateLoopRequest


class OpenLoopSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", from_attributes=True)
    id: UUID
    subject: str
    counterparty: str | None
    direction: str
    due_hint: datetime | None
    status: Literal["open", "closed", "expired"]
    closed_reason: str | None
    created_at: datetime


async def managed_open_loop(
    db: AsyncSession, actor_id: UUID, loop_id: UUID, *, lock: bool = False
) -> OpenLoopSnapshot:
    query = select(*(getattr(OpenLoop, name) for name in OpenLoopSnapshot.model_fields)).where(
        OpenLoop.id == loop_id, OpenLoop.user_id == actor_id
    )
    if lock:
        query = query.with_for_update()
    row = (await db.execute(query)).mappings().one_or_none()
    if row is None:
        raise ResourceNotFoundError("open_loop", loop_id)
    return OpenLoopSnapshot.model_validate(dict(row))


def require_open_loop(snapshot: OpenLoopSnapshot) -> None:
    if snapshot.status != OpenLoopStatus.OPEN.value:
        raise ResourceConflictError("open_loop", detail={"error_code": "STALE_STATE"})


def changed_open_loop(
    before: OpenLoopSnapshot, changes: UpdateLoopRequest | CloseLoopRequest
) -> OpenLoopSnapshot:
    if isinstance(changes, CloseLoopRequest):
        return before.model_copy(
            update={
                "status": "closed",
                "closed_reason": "api" if changes.action == "done" else "dismissed",
            }
        )
    values = before.model_dump()
    if changes.subject is not None:
        values["subject"] = changes.subject
    if changes.clear_due_hint:
        values["due_hint"] = None
    elif changes.due_hint is not None:
        values["due_hint"] = changes.due_hint
    return OpenLoopSnapshot.model_validate(values)


async def apply_open_loop_change(
    db: AsyncSession,
    actor_id: UUID,
    loop_id: UUID,
    changes: UpdateLoopRequest | CloseLoopRequest,
) -> None:
    repository = OpenLoopRepository(db)
    if isinstance(changes, CloseLoopRequest):
        claimed = await repository.close_loop(
            loop_id,
            actor_id,
            reason="api" if changes.action == "done" else "dismissed",
            emit_metric=False,
        )
    else:
        claimed = await repository.update_loop(
            loop_id,
            actor_id,
            subject=changes.subject,
            due_hint=changes.due_hint,
            clear_due_hint=changes.clear_due_hint,
        )
    if not claimed:
        raise ResourceConflictError("open_loop", detail={"error_code": "STALE_STATE"})
