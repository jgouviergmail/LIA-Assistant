"""Amend only the meeting request and regenerate every consent fact."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_email_schemas import MeetingEmailInput
from src.domains.agents.application.meeting_email_send import prepare_meeting_email
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_meeting_email(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if old.operation_id != "meeting_report.email" or modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_meeting_email(
            db,
            old.actor_id,
            MeetingEmailInput.model_validate(modified.get("intent")),
            command_id=old.command_id,
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
