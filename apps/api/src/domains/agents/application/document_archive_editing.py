"""Refresh the same exact ordered document selection; never silently retarget consent."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_archive import prepare_document_archive
from src.domains.agents.application.document_archive_schemas import (
    DocumentArchiveInput,
    DocumentArchivePatch,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_document_archive(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = DocumentArchiveInput.model_validate(modified.get("intent"))
    original = DocumentArchivePatch.model_validate(old.intent).archive_to_download
    if request.space_id != original.space_id or request.document_ids != tuple(
        document.document_id for document in original.documents
    ):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_document_archive(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
