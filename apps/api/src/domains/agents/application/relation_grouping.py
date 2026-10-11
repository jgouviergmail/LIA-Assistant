"""Exact approved grouping changes reuse source semantics and commit their own receipt."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.relation_grouping_schemas import (
    RelationGroupingPatch,
    RelationGroupingRequest,
)
from src.domains.agents.application.relation_grouping_spec import RELATION_GROUPING_OPERATION
from src.domains.relations.grouping_commands import (
    RelationGroupingSelection,
    grouping_debriefs,
    read_relation_grouping,
)
from src.domains.relations.preference_commands import lock_relation_owner
from src.domains.relations.service import RelationsService
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_relation_grouping(
    db: AsyncSession,
    actor_id: UUID,
    request: RelationGroupingRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = RelationGroupingRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    expected = await read_relation_grouping(
        db, actor_id, action=selected.action, source=selected.source, target=selected.target
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        RELATION_GROUPING_OPERATION,
        RelationGroupingPatch(relation_grouping=expected),
        {"relation_grouping": expected.public_scope()},
        {"relation_grouping": expected.public_scope(after=True)},
        command_id=command_id,
    )


def canonical_relation_grouping(draft: ApplicationActionDraftContent) -> bool:
    expected = RelationGroupingPatch.model_validate(draft.intent).relation_grouping
    return draft.before == {"relation_grouping": expected.public_scope()} and draft.after == {
        "relation_grouping": expected.public_scope(after=True)
    }


async def execute_relation_grouping(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "relation_grouping.update":
        raise CommandRejected("FORBIDDEN")
    if not canonical_relation_grouping(draft):
        raise ValueError("Grouping requires exact approved identities and invalidation scope")
    expected = RelationGroupingPatch.model_validate(draft.intent).relation_grouping

    async def check() -> None:
        await require_application_tools(db)
        await load_actor(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await lock_relation_owner(db, actor_id)
    await check()
    current = await read_relation_grouping(
        db,
        actor_id,
        action=expected.action,
        source=expected.source,
        target=expected.target,
        lock_debriefs=True,
    )
    if current != expected:
        raise ResourceConflictError("relation_grouping", detail={"error_code": "STALE_STATE"})
    await check()
    if expected.no_op:
        receipt.committed = True
        receipt.no_op = True
        return
    await _apply_grouping(db, actor_id, expected)
    await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True


async def _apply_grouping(
    db: AsyncSession, actor_id: UUID, expected: RelationGroupingSelection
) -> None:
    """Use source writes and verify every approved invalidation before committing."""
    service = RelationsService(actor_id)
    if expected.action == "merge":
        assert expected.target is not None
        actual = await service.merge_in_session(db, source=expected.source, target=expected.target)
        if actual != expected.target_canonical:
            raise ValueError("Source merge did not establish approved target")
    else:
        if not await service.split_in_session(db, expected.source):
            raise ValueError("Source split did not remove the approved alias")
    after = await read_relation_grouping(
        db, actor_id, action=expected.action, source=expected.source, target=expected.target
    )
    if not after.no_op:
        raise ValueError("Source grouping postcondition differs from approved result")
    invalidated = list(
        dict.fromkeys([expected.source_key, expected.source_canonical, expected.target_canonical])
    )
    if await grouping_debriefs(db, actor_id, invalidated):
        raise ValueError("Source grouping did not invalidate all approved stored debriefs")
