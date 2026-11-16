"""An import's amendment needs fresh approval and never retargets another attached file."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_import import prepare_memory_import
from src.domains.agents.application.memory_import_schemas import (
    MemoryImportInput,
    MemoryImportPatch,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_memory_import(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    desired = MemoryImportInput.model_validate(modified.get("intent"))
    selected = MemoryImportPatch.model_validate(old.intent).memories_import
    async with get_db_context() as db:
        revised = await prepare_memory_import(db, old.actor_id, desired, command_id=old.command_id)
        # The amendment reads the same file, or it is refused: never another attachment.
        resolved = MemoryImportPatch.model_validate(revised.intent).memories_import
        if resolved.attachment_id != selected.attachment_id:
            raise CommandRejected("INVALID_INPUT")
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
