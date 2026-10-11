"""A file amendment retains the exact selected document and original pending command."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_download import prepare_document_download
from src.domains.agents.application.document_download_schemas import (
    DocumentDownloadInput,
    DocumentDownloadPatch,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_document_download(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = DocumentDownloadInput.model_validate(modified.get("intent"))
    original = DocumentDownloadPatch.model_validate(old.intent).document_to_download
    if (request.space_id, request.document_id) != (original.space_id, original.document_id):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_document_download(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
