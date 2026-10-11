"""Explicit source erasure overrides pin protection only after exact confirmation."""

from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_pin import (
    _memory_pin_fence,
    memory_pin_snapshot,
    memory_snapshot_matches,
)
from src.domains.agents.application.memory_removal_schemas import (
    MemoryDeletePatch,
    MemoryDeleteRequest,
)
from src.domains.agents.application.memory_spec import MEMORY_DELETE_OPERATION
from src.domains.memories.management_commands import (
    get_active_owned_memory,
    lock_active_owned_memory,
)
from src.domains.memories.service import MemoryService
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_memory_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: MemoryDeleteRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = MemoryDeleteRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await get_active_owned_memory(db, actor_id, selected.memory_id)
    patch = MemoryDeletePatch(memory_to_delete=memory_pin_snapshot(row))
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        MEMORY_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"memory_to_delete": None},
        command_id=command_id,
    )


async def execute_memory_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    expected = MemoryDeletePatch.model_validate(draft.intent).memory_to_delete
    if draft.intent != draft.before or draft.after != {"memory_to_delete": None}:
        raise ValueError("Deletion must retain the exact confirmed source fact")
    await _memory_pin_fence(db, actor_id, draft)
    try:
        row = await lock_active_owned_memory(db, actor_id, expected.id)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"}) from exc
    if not memory_snapshot_matches(row, expected):
        raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"})
    await _memory_pin_fence(db, actor_id, draft)
    actor = await load_actor(db, actor_id)
    invalidate_extractions(actor)
    await MemoryService(db).delete_memory(row)
    await _memory_pin_fence(db, actor_id, draft)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
