"""All memory proposal edits reread the source and retain single-use command identity."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_bulk_removal import prepare_memory_bulk_removal
from src.domains.agents.application.memory_bulk_schemas import MemoryBulkDeleteRequest
from src.domains.agents.application.memory_create_schemas import MemoryCreateConfiguration
from src.domains.agents.application.memory_creation import prepare_memory_creation
from src.domains.agents.application.memory_pin import prepare_memory_pin
from src.domains.agents.application.memory_pin_schemas import MemoryPinRequest
from src.domains.agents.application.memory_removal import prepare_memory_removal
from src.domains.agents.application.memory_removal_schemas import MemoryDeleteRequest
from src.domains.agents.application.memory_update import prepare_memory_update
from src.domains.agents.application.memory_update_schemas import MemoryUpdateRequest
from src.domains.agents.context.runtime_context import runtime_context_if_running


async def rebuild_memory_draft(
    db: AsyncSession, old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    intent = modified.get("intent")
    if old.operation_id == "memories.delete_all":
        revised = await prepare_memory_bulk_removal(
            db,
            old.actor_id,
            MemoryBulkDeleteRequest.model_validate(intent),
            command_id=old.command_id,
        )
    elif old.operation_id == "memories.create":
        revised = await prepare_memory_creation(
            db,
            old.actor_id,
            MemoryCreateConfiguration.model_validate(intent),
            command_id=old.command_id,
        )
    elif old.operation_id == "memories.update":
        revised = await prepare_memory_update(
            db, old.actor_id, MemoryUpdateRequest.model_validate(intent), command_id=old.command_id
        )
    elif old.operation_id == "memories.delete":
        revised = await prepare_memory_removal(
            db, old.actor_id, MemoryDeleteRequest.model_validate(intent), command_id=old.command_id
        )
    elif old.operation_id == "memories.pin":
        revised = await prepare_memory_pin(
            db, old.actor_id, MemoryPinRequest.model_validate(intent), command_id=old.command_id
        )
    else:
        raise CommandRejected("UNKNOWN_OPERATION")
    if not await replace_pending_command(db, old, revised):
        raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
