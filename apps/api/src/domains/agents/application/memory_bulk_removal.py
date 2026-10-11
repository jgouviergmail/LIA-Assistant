"""Global erasure locks the source scope and confirms exact bounded summaries."""

from hashlib import sha256
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_bulk_schemas import (
    MemoryBulkDeletePatch,
    MemoryBulkDeleteRequest,
    MemoryBulkSnapshot,
)
from src.domains.agents.application.memory_pin import _memory_pin_fence, memory_pin_snapshot
from src.domains.agents.application.memory_spec import MEMORY_BULK_DELETE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.memories.management_bulk import iter_owned_memories
from src.domains.memories.management_commands import lock_memory_actor
from src.domains.memories.repository import MemoryRepository
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def memory_bulk_snapshot(
    db: AsyncSession, actor_id: UUID, preserve_pinned: bool, *, locked: bool = False
) -> MemoryBulkSnapshot:
    digest = sha256(b"lia-memory-erasure-v1")
    selected = preserved = pinned = procedural = invalidated = 0
    categories: dict[str, int] = {}
    async for row in iter_owned_memories(db, actor_id, for_update=locked):
        if preserve_pinned and row.pinned:
            preserved += 1
            continue
        selected += 1
        pinned += int(row.pinned)
        procedural += int(row.category == "procedural")
        invalidated += int(row.invalidated_at is not None)
        categories[row.category] = categories.get(row.category, 0) + 1
        digest.update(
            bytes.fromhex(
                payload_digest(
                    {
                        "fact": memory_pin_snapshot(row).model_dump(
                            mode="json", exclude={"updated_at"}
                        ),
                        "invalidated_at": row.invalidated_at,
                        "superseded_by_id": row.superseded_by_id,
                    }
                )
            )
        )
    return MemoryBulkSnapshot(
        preserve_pinned=preserve_pinned,
        selected_count=selected,
        preserved_count=preserved,
        pinned_count=pinned,
        procedural_count=procedural,
        invalidated_count=invalidated,
        by_category=categories,
        selection_digest=digest.hexdigest(),
    )


async def prepare_memory_bulk_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: MemoryBulkDeleteRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = MemoryBulkDeleteRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    patch = MemoryBulkDeletePatch(
        memories_to_delete=await memory_bulk_snapshot(db, actor_id, selected.preserve_pinned)
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        MEMORY_BULK_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"memories_to_delete": None},
        command_id=command_id,
    )


async def execute_memory_bulk_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    expected = MemoryBulkDeletePatch.model_validate(draft.intent).memories_to_delete
    if draft.intent != draft.before or draft.after != {"memories_to_delete": None}:
        raise ValueError("Global erasure must retain the confirmed source selection")
    await _memory_pin_fence(db, actor_id, draft)
    actor = await lock_memory_actor(db, actor_id)
    await _memory_pin_fence(db, actor_id, draft)
    actual = await memory_bulk_snapshot(db, actor_id, expected.preserve_pinned, locked=True)
    if actual != expected:
        raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"})
    receipt.no_op = expected.selected_count == 0
    if not receipt.no_op:
        invalidate_extractions(actor)
        removed = await MemoryRepository(db).delete_all_for_user(actor_id, expected.preserve_pinned)
        if removed != expected.selected_count:
            raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"})
    await _memory_pin_fence(db, actor_id, draft)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
