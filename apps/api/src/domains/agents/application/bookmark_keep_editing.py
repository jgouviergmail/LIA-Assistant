"""A keep amendment rebuilds its exact copy/quota witness and original pending command."""

from src.domains.agents.application.bookmark_keep import prepare_bookmark_keep
from src.domains.agents.application.bookmark_keep_schemas import BookmarkKeepInput
from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_bookmark_keep(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    desired = BookmarkKeepInput.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_bookmark_keep(db, old.actor_id, desired, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
