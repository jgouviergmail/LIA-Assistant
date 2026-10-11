"""Refresh the same browser-owned package target; a different target needs a new proposal."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_file_upload import prepare_plugin_file_upload
from src.domains.agents.application.plugin_file_upload_schemas import (
    PluginFileUploadInput,
    PluginFileUploadPatch,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_plugin_file_upload(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    desired = PluginFileUploadInput.model_validate(modified.get("intent"))
    selected = PluginFileUploadPatch.model_validate(old.intent).plugin_file_upload
    if modified.get("remove_fields") or desired != selected.request:
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_plugin_file_upload(
            db, old.actor_id, desired, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
