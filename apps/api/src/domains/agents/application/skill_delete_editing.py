"""Removal amendments require fresh approval and never retarget another skill."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_delete import prepare_skill_deletion
from src.domains.agents.application.skill_delete_schemas import SkillDeleteInput, SkillDeletePatch
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_skill_delete(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    desired = SkillDeleteInput.model_validate(modified.get("intent"))
    selected = SkillDeletePatch.model_validate(old.intent).skill_to_delete
    if desired.skill_id != selected.request.skill_id:
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_skill_deletion(db, old.actor_id, desired, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
