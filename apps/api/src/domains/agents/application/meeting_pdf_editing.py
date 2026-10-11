"""Refreshing PDF consent preserves the original meeting and browser binding."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_pdf_download import prepare_meeting_pdf
from src.domains.agents.application.meeting_pdf_schemas import MeetingPDFInput, MeetingPDFPatch
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_meeting_pdf(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    desired = MeetingPDFInput.model_validate(modified.get("intent"))
    if (
        modified.get("remove_fields")
        or desired.meeting_id
        != MeetingPDFPatch.model_validate(old.intent).meeting_pdf_download.meeting_id
    ):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_meeting_pdf(db, old.actor_id, desired, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
