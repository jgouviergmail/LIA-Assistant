"""Exact sparse editing prepares vectors after approval and before source write locks."""

from functools import partial
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_create_schemas import MemoryCreateConfiguration
from src.domains.agents.application.memory_creation_embeddings import (
    prepare_memory_creation_embeddings,
)
from src.domains.agents.application.memory_pin import (
    _memory_pin_fence,
    memory_pin_snapshot,
    memory_snapshot_matches,
)
from src.domains.agents.application.memory_spec import MEMORY_UPDATE_OPERATION
from src.domains.agents.application.memory_update_schemas import (
    MemoryUpdatePatch,
    MemoryUpdateRequest,
    MemoryUpdateValues,
)
from src.domains.memories.management_commands import (
    get_active_owned_memory,
    lock_active_owned_memory,
)
from src.domains.memories.models import Memory
from src.domains.memories.schemas import MemoryUpdate
from src.domains.memories.service import MemoryService, preview_memory_update
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_memory_update(
    db: AsyncSession,
    actor_id: UUID,
    request: MemoryUpdateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = MemoryUpdateRequest.model_validate(request.model_dump(exclude_unset=True))
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await get_active_owned_memory(db, actor_id, selected.memory_id)
    expected = memory_pin_snapshot(row)
    previous = MemoryUpdateValues(
        expected=expected,
        changes=selected.changes,
        configuration=MemoryCreateConfiguration.model_validate(
            preview_memory_update(row, MemoryUpdate()).model_dump()
        ),
    )
    desired = previous.model_copy(
        update={
            "configuration": MemoryCreateConfiguration.model_validate(
                preview_memory_update(row, selected.changes).model_dump()
            )
        }
    )
    before, after = MemoryUpdatePatch(memory_configuration=previous), MemoryUpdatePatch(
        memory_configuration=desired
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        MEMORY_UPDATE_OPERATION,
        after,
        before.model_dump(mode="json", exclude_unset=True),
        after.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def _current_update_row(
    db: AsyncSession, actor_id: UUID, expected: MemoryUpdateValues, *, locked: bool
) -> Memory:
    """Both pre-spend and locked rechecks use the exact active source fact."""
    try:
        row = await (
            lock_active_owned_memory(db, actor_id, expected.expected.id)
            if locked
            else get_active_owned_memory(db, actor_id, expected.expected.id)
        )
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"}) from exc
    if not memory_snapshot_matches(row, expected.expected):
        raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"})
    return row


async def execute_memory_update(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    desired = MemoryUpdatePatch.model_validate(draft.intent).memory_configuration
    previous = MemoryUpdatePatch.model_validate(draft.before).memory_configuration
    if (
        desired.expected != previous.expected
        or desired.changes != previous.changes
        or draft.intent != draft.after
    ):
        raise ValueError("An edit cannot replace its confirmed fact or delta")
    guard = partial(_memory_pin_fence, db, actor_id, draft)
    await guard()
    await _current_update_row(db, actor_id, previous, locked=False)
    vector_change = (
        previous.configuration.content != desired.configuration.content
        or previous.configuration.trigger_topic != desired.configuration.trigger_topic
    )
    prepared = (
        await prepare_memory_creation_embeddings(
            actor_id,
            draft.command_id,
            desired.configuration.content,
            desired.configuration.trigger_topic,
            guard,
        )
        if vector_change
        else None
    )
    await guard()
    row = await _current_update_row(db, actor_id, previous, locked=True)
    if (
        preview_memory_update(row, MemoryUpdate()).model_dump()
        != previous.configuration.model_dump()
        or preview_memory_update(row, desired.changes).model_dump()
        != desired.configuration.model_dump()
    ):
        raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"})
    receipt.no_op = previous.configuration == desired.configuration
    if not receipt.no_op:
        actor = await load_actor(db, actor_id)
        invalidate_extractions(actor)
        updated = await MemoryService(
            db, embedder=prepared.resolve if prepared else None
        ).update_from_management(row, desired.changes)
        if (
            preview_memory_update(updated, MemoryUpdate()).model_dump()
            != desired.configuration.model_dump()
        ):
            raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"})
    await guard()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
