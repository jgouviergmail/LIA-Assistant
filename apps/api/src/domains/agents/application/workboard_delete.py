"""Owned subtree deletion reuses the source service, exact fences and verified commit."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.workboard_create import creation_access
from src.domains.agents.application.workboard_delete_schemas import (
    WorkboardDeleteInput,
    WorkboardDeletePatch,
    WorkboardDeleteSelection,
    WorkboardDeleteTarget,
    canonical_workboard_delete,
)
from src.domains.agents.application.workboard_delete_spec import WORKBOARD_DELETE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.comment_fence import lock_comment_ticket
from src.domains.workboard.models import WorkboardComment, WorkboardTicket, WorkboardTicketEvent
from src.domains.workboard.service import WorkboardService


async def _delete_selection(
    db: AsyncSession, actor: User, request: WorkboardDeleteInput
) -> WorkboardDeleteSelection:
    service = WorkboardService(db)
    parent, children = await service.deletable(actor, request.ticket_id)
    rows = list(
        (
            await db.scalars(
                select(WorkboardTicket)
                .where(or_(WorkboardTicket.id == parent.id, WorkboardTicket.parent_id == parent.id))
                .order_by(WorkboardTicket.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if len(rows) != children + 1 or any(row.owner_user_id != actor.id for row in rows):
        raise ValueError("Source deletion subtree is inconsistent")
    identities = [row.id for row in rows]
    raw = list(
        (
            await db.scalars(
                select(func.to_jsonb(WorkboardTicket.__table__.table_valued()))
                .where(WorkboardTicket.id.in_(identities))
                .order_by(WorkboardTicket.id)
            )
        ).all()
    )
    if len(json.dumps(raw, ensure_ascii=False).encode("utf-8")) > 65536:
        raise ValueError("Source subtree exceeds the exact native deletion bound")
    comments = int(
        await db.scalar(
            select(func.count(WorkboardComment.id)).where(
                WorkboardComment.ticket_id.in_(identities)
            )
        )
        or 0
    )
    events = int(
        await db.scalar(
            select(func.count(WorkboardTicketEvent.id)).where(
                WorkboardTicketEvent.ticket_id.in_(identities)
            )
        )
        or 0
    )
    return WorkboardDeleteSelection(
        request=request,
        items=[
            WorkboardDeleteTarget(
                ticket_id=row.id,
                title=row.title,
                status=row.status,
                running=row.run_claimed_at is not None,
                has_pending_action=bool(row.pending_action),
            )
            for row in rows
        ],
        comments=comments,
        events=events,
        owned_count=await service.repo.count_owned(actor.id),
        state_digest=payload_digest(raw),
    )


async def prepare_workboard_delete(
    db: AsyncSession,
    actor_id: UUID,
    request: WorkboardDeleteInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = WorkboardDeleteInput.model_validate(request.model_dump())
    actor = await creation_access(db, actor_id)
    scope = await _delete_selection(db, actor, selected)
    await creation_access(db, actor_id)
    return build_action_content(
        actor_id,
        WORKBOARD_DELETE_OPERATION,
        WorkboardDeletePatch(workboard_delete=scope),
        {"workboard_delete": scope.public_scope()},
        {"workboard_delete": scope.public_scope(after=True)},
        command_id=command_id,
    )


async def _verify_deletion(
    db: AsyncSession, actor_id: UUID, expected: WorkboardDeleteSelection, removed: int
) -> None:
    identities = [item.ticket_id for item in expected.items]
    if type(removed) is not int or removed != len(identities):
        raise ValueError("Source must report the exact confirmed removal")
    remaining = await db.scalar(
        select(func.count(WorkboardTicket.id)).where(WorkboardTicket.id.in_(identities))
    )
    comments = await db.scalar(
        select(func.count(WorkboardComment.id)).where(WorkboardComment.ticket_id.in_(identities))
    )
    events = await db.scalar(
        select(func.count(WorkboardTicketEvent.id)).where(
            WorkboardTicketEvent.ticket_id.in_(identities)
        )
    )
    if (
        remaining
        or comments
        or events
        or await WorkboardService(db).repo.count_owned(actor_id) != expected.owned_count - removed
    ):
        raise ValueError("Source must persist only the exact confirmed subtree removal")


async def execute_workboard_delete(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != WORKBOARD_DELETE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_workboard_delete(draft):
        raise ValueError("Deletion requires exact canonical consent")
    expected = WorkboardDeletePatch.model_validate(draft.intent).workboard_delete

    async def check() -> User:
        actor = await creation_access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")
        return actor

    await check()
    await lock_comment_ticket(db, actor_id, expected.request.ticket_id)
    await db.execute(
        select(WorkboardTicket.id)
        .where(WorkboardTicket.parent_id == expected.request.ticket_id)
        .order_by(WorkboardTicket.id)
        .with_for_update()
    )
    actor = await check()
    if await _delete_selection(db, actor, expected.request) != expected:
        raise ResourceConflictError("workboard_delete", detail={"error_code": "STALE_STATE"})
    removed = await WorkboardService(db).delete(actor, expected.request.ticket_id)
    await db.flush()
    await _verify_deletion(db, actor_id, expected, removed)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    receipt.values = {"workboard_delete": {**expected.public_scope(after=True), "removed": removed}}
