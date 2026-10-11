"""Full edited manual configuration receives new source facts and durable approval."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_create_schemas import JournalCreateConfiguration
from src.domains.agents.application.journal_creation import prepare_journal_creation
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_journal_creation_draft(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    selected = JournalCreateConfiguration.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_journal_creation(
            db, old.actor_id, selected, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
