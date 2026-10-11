"""One exact human-approved creation reuses source normalization, rights and quota caps."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, raise_not_found_or_unauthorized
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.workboard_create_schemas import (
    WorkboardCreateInput,
    WorkboardCreatePatch,
    WorkboardCreateSelection,
)
from src.domains.agents.application.workboard_create_spec import WORKBOARD_CREATE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.models import PeerConnection, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.creation_fence import lock_creation_scope
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.schemas import TicketRow
from src.domains.workboard.service import WorkboardService


async def creation_access(db: AsyncSession, actor_id: UUID) -> User:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.WORKBOARD)
    return await load_actor(db, actor_id)


async def _assignment_access(
    db: AsyncSession, actor_id: UUID, request: WorkboardCreateInput
) -> None:
    if request.assignee_user_id is not None and request.assignee_user_id != actor_id:
        await require_capability_fresh(db, PlatformCapability.PEERS)


async def _creation_selection(
    db: AsyncSession, actor: User, request: WorkboardCreateInput
) -> WorkboardCreateSelection:
    service = WorkboardService(db)
    normalized, kind, holder = await service.validate_creation(actor, request)
    parent = None
    parent_title = None
    if request.parent_id is not None:
        parent = await db.scalar(
            select(func.to_jsonb(WorkboardTicket.__table__.table_valued())).where(
                WorkboardTicket.id == request.parent_id, WorkboardTicket.owner_user_id == actor.id
            )
        )
        if parent is None:
            raise_not_found_or_unauthorized("ticket", request.parent_id)
        parent_title = parent["title"]
    pair = None
    name = None
    if holder is not None:
        lo, hi = canonical_pair(actor.id, holder)
        pair = await db.scalar(
            select(func.to_jsonb(PeerConnection.__table__.table_valued())).where(
                PeerConnection.user_a_id == lo, PeerConnection.user_b_id == hi
            )
        )
        peer = await db.get(User, holder, populate_existing=True)
        if peer is None or not peer.is_active or peer.deleted_at is not None:
            raise_not_found_or_unauthorized("peer", holder)
        name = peer.full_name
    return WorkboardCreateSelection(
        request=WorkboardCreateInput.model_validate(normalized.model_dump()),
        assignee_kind=kind,
        holder_id=holder,
        holder_name=name,
        parent_title=parent_title,
        owned_count=await service.repo.count_owned(actor.id),
        max_tickets=settings.workboard_max_tickets_per_user,
        state_digest=payload_digest(
            {
                "parent": parent,
                "pair": pair,
                "max_children": settings.workboard_max_children_per_ticket,
            }
        ),
    )


async def prepare_workboard_creation(
    db: AsyncSession,
    actor_id: UUID,
    request: WorkboardCreateInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = WorkboardCreateInput.model_validate(request.model_dump())
    actor = await creation_access(db, actor_id)
    await _assignment_access(db, actor_id, selected)
    scope = await _creation_selection(db, actor, selected)
    await creation_access(db, actor_id)
    await _assignment_access(db, actor_id, selected)
    return build_action_content(
        actor_id,
        WORKBOARD_CREATE_OPERATION,
        WorkboardCreatePatch(workboard_create=scope),
        {"workboard_create": scope.public_scope()},
        {"workboard_create": scope.public_scope(after=True)},
        command_id=command_id,
    )


def canonical_workboard_creation(draft: ApplicationActionDraftContent) -> bool:
    scope = WorkboardCreatePatch.model_validate(draft.intent).workboard_create
    return draft.before == {"workboard_create": scope.public_scope()} and draft.after == {
        "workboard_create": scope.public_scope(after=True)
    }


async def _verify_created_ticket(
    db: AsyncSession, actor_id: UUID, identity: UUID, expected: WorkboardCreateSelection
) -> TicketRow:
    actual = await db.scalar(
        select(WorkboardTicket)
        .where(WorkboardTicket.id == identity)
        .execution_options(populate_existing=True)
    )
    if actual is None or actual.owner_user_id != actor_id:
        raise ValueError("Source creation did not persist an owned ticket")
    if (
        actual.assignee_kind != expected.assignee_kind
        or actual.assignee_user_id != expected.holder_id
    ):
        raise ValueError("Source creation differs from approved configuration")
    for name, value in expected.request.model_dump(
        exclude={"assignee", "assignee_user_id"}
    ).items():
        field = "follow_owner" if name == "follow" else name
        if getattr(actual, field) != value:
            raise ValueError("Source creation differs from an approved source field")
    return TicketRow.model_validate(actual)


async def execute_workboard_creation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "workboard_ticket.create":
        raise CommandRejected("FORBIDDEN")
    if not canonical_workboard_creation(draft):
        raise ValueError("Creation requires an exact canonical configuration")
    expected = WorkboardCreatePatch.model_validate(draft.intent).workboard_create

    async def check() -> User:
        actor = await creation_access(db, actor_id)
        await _assignment_access(db, actor_id, expected.request)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")
        return actor

    await check()
    await lock_creation_scope(db, actor_id, expected.request)
    actor = await check()
    current = await _creation_selection(db, actor, expected.request)
    if current != expected:
        raise ResourceConflictError("workboard_create", detail={"error_code": "STALE_STATE"})
    if (
        await db.scalar(select(WorkboardTicket.id).where(WorkboardTicket.id == draft.command_id))
        is not None
    ):
        raise ResourceConflictError("workboard_create", detail={"error_code": "STALE_STATE"})
    created = await WorkboardService(db).create(actor, expected.request, ticket_id=draft.command_id)
    if created.id != draft.command_id:
        raise ValueError("Source must persist the approved creation identity")
    await db.flush()
    actual = await _verify_created_ticket(db, actor_id, created.id, expected)
    public = {
        **expected.public_scope(after=True),
        "ticket_id": str(actual.id),
        "ticket": actual.model_dump(mode="json"),
    }
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    receipt.values = {"workboard_create": public}
