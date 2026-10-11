"""Consent edits reread current selected values and require exact reconfirmation."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.peer_preference_schemas import PeerPreferencePatch
from src.domains.agents.application.peer_preferences import prepare_peer_preferences
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_peer_preference_draft(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    patch = PeerPreferencePatch.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_peer_preferences(db, old.actor_id, patch, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
