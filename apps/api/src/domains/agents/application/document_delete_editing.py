"""Refresh the same document deletion selection and replace its pending consent."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_delete import prepare_document_deletion
from src.domains.agents.application.document_delete_schemas import (
    DocumentDeleteInput,
    DocumentDeletePatch,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_document_deletion(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = DocumentDeleteInput.model_validate(modified.get("intent"))
    original = DocumentDeletePatch.model_validate(old.intent).documents_to_delete.request
    if request != original:
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_document_deletion(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
