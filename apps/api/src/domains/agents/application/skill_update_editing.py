"""A skill amendment changes only the explicit personal state and requires fresh approval."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_update import prepare_skill_update
from src.domains.agents.application.skill_update_schemas import SkillUpdateInput, SkillUpdatePatch
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_skill_update(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    desired = SkillUpdateInput.model_validate(modified.get("intent"))
    selected = SkillUpdatePatch.model_validate(old.intent).skill_personal_state
    if desired.skill_id != selected.request.skill_id:
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_skill_update(db, old.actor_id, desired, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
