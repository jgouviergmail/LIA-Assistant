"""Changed sparse changes reread source values and require renewed exact consent."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_report_update_schemas import ReportUpdateInput
from src.domains.agents.application.meeting_report_updating import prepare_report_update
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_report_update(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if old.operation_id != "meeting_report.update" or modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_report_update(
            db,
            old.actor_id,
            ReportUpdateInput.model_validate(modified.get("intent")),
            command_id=old.command_id,
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
