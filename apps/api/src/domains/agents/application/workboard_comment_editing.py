"""An edit rereads the source ticket and replaces the same pending command."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.workboard_comment import prepare_workboard_comment
from src.domains.agents.application.workboard_comment_schemas import WorkboardCommentInput
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_workboard_comment(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = WorkboardCommentInput.model_validate(modified.get("intent"))
    expected = old.before["workboard_comment"]
    if not isinstance(expected, dict) or str(request.ticket_id) != expected.get("ticket_id"):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_workboard_comment(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
