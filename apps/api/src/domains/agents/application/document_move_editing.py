"""Rebuild the same selected source documents; changing destination receives fresh consent."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_move import prepare_document_move
from src.domains.agents.application.document_move_schemas import (
    DocumentMoveInput,
    DocumentMovePatch,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_document_move(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = DocumentMoveInput.model_validate(modified.get("intent"))
    original = DocumentMovePatch.model_validate(old.intent).documents_to_move.request
    if request.space_id != original.space_id or request.document_ids != original.document_ids:
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_document_move(db, old.actor_id, request, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
