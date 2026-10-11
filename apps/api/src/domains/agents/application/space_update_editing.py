"""Edits keep the selected source space and rebuild exact consent on the pending command."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_update import prepare_space_update
from src.domains.agents.application.space_update_schemas import SpaceUpdateInput, SpaceUpdatePatch
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_space_update(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = SpaceUpdateInput.model_validate(modified.get("intent"))
    if (
        request.space_id
        != SpaceUpdatePatch.model_validate(old.intent).space_update.request.space_id
    ):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_space_update(db, old.actor_id, request, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
