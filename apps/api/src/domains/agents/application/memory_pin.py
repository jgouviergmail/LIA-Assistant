"""Pin changes retain the exact confirmed fact and use the source's manual write locks."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_pin_schemas import (
    MemoryPinPatch,
    MemoryPinRequest,
    MemoryPinSnapshot,
    MemoryPinValues,
)
from src.domains.agents.application.memory_spec import MEMORY_PIN_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.memories.management_commands import (
    get_active_owned_memory,
    lock_active_owned_memory,
    set_locked_memory_pin,
)
from src.domains.memories.models import Memory
from src.domains.users.preference_cas import PreferenceWriteReceipt


def memory_pin_snapshot(row: Memory) -> MemoryPinSnapshot:
    return MemoryPinSnapshot(
        id=row.id,
        content=row.content,
        category=row.category,
        pinned=row.pinned,
        created_at=row.created_at,
        updated_at=row.updated_at,
        configuration_digest=payload_digest(
            {
                "content": row.content,
                "category": row.category,
                "emotional_weight": row.emotional_weight,
                "trigger_topic": row.trigger_topic,
                "usage_nuance": row.usage_nuance,
                "importance": row.importance,
            }
        ),
    )


def memory_snapshot_matches(row: Memory, expected: MemoryPinSnapshot) -> bool:
    """Recall updates operational timestamps without changing the approved fact."""
    return memory_pin_snapshot(row).model_dump(exclude={"updated_at"}) == expected.model_dump(
        exclude={"updated_at"}
    )


async def prepare_memory_pin(
    db: AsyncSession, actor_id: UUID, request: MemoryPinRequest, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = MemoryPinRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await get_active_owned_memory(db, actor_id, selected.memory_id)
    expected = memory_pin_snapshot(row)
    before = MemoryPinPatch(memory_pin=MemoryPinValues(expected=expected, pinned=expected.pinned))
    after = MemoryPinPatch(memory_pin=MemoryPinValues(expected=expected, pinned=selected.pinned))
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        MEMORY_PIN_OPERATION,
        after,
        before.model_dump(mode="json"),
        after.model_dump(mode="json"),
        command_id=command_id,
    )


async def _memory_pin_fence(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def execute_memory_pin(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    desired = MemoryPinPatch.model_validate(draft.intent).memory_pin
    previous = MemoryPinPatch.model_validate(draft.before).memory_pin
    if (
        desired.expected != previous.expected
        or previous.pinned != previous.expected.pinned
        or draft.intent != draft.after
    ):
        raise ValueError("A pin cannot replace the exact confirmed fact")
    await _memory_pin_fence(db, actor_id, draft)
    try:
        row = await lock_active_owned_memory(db, actor_id, desired.expected.id)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"}) from exc
    if not memory_snapshot_matches(row, previous.expected):
        raise ResourceConflictError("memory", detail={"error_code": "STALE_STATE"})
    await _memory_pin_fence(db, actor_id, draft)
    receipt.no_op = row.pinned == desired.pinned
    if not receipt.no_op:
        await set_locked_memory_pin(db, row, desired.pinned)
    await _memory_pin_fence(db, actor_id, draft)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
