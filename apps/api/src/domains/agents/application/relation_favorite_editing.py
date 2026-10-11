"""An edited favorite gets fresh source identity facts and another exact approval."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.relation_favorite import prepare_relation_favorite
from src.domains.agents.application.relation_favorite_schemas import RelationFavoriteRequest
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_relation_favorite_draft(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = RelationFavoriteRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_relation_favorite(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
