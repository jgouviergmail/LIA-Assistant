"""Every SMS edit rebuilds source snapshots and replaces the approval digest."""

from pydantic import JsonValue, TypeAdapter

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.sms_action_spec import SMS_ACTION_SPECS
from src.domains.agents.application.sms_actions import prepare_sms_action
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context

_JSON = TypeAdapter(dict[str, JsonValue])


async def rebuild_sms_draft(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    selected = _JSON.validate_python(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_sms_action(
            db,
            old.actor_id,
            old.operation_id,
            selected,
            origin=context.application_origin,
            command_id=old.command_id,
        )
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


SMS_EDITORS = dict.fromkeys(SMS_ACTION_SPECS, rebuild_sms_draft)
