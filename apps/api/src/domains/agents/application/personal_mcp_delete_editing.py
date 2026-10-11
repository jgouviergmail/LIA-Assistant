"""Refresh a deletion preview without allowing an amendment to select another server."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_delete import prepare_personal_mcp_delete
from src.domains.agents.application.personal_mcp_delete_schemas import (
    PersonalMCPDeleteInput,
    PersonalMCPDeletePatch,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_personal_mcp_delete(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    desired = PersonalMCPDeleteInput.model_validate(modified.get("intent"))
    selected = PersonalMCPDeletePatch.model_validate(old.intent).personal_mcp_server_delete
    if desired.server_id != selected.request.server_id:
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_personal_mcp_delete(
            db, old.actor_id, desired, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
