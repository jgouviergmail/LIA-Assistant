"""Edited discussion controls replace the approved snapshot with a fresh native draft."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.discussion_commands import prepare_discussion_action
from src.domains.agents.application.discussion_specs import DISCUSSION_SPECS
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_discussion_draft(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    """Replace a pending discussion draft by a fresh one built from the person's edit.

    Args:
        old: The pending draft.
        modified: The edited intent; removing fields is refused.

    Returns:
        The new draft, serialised.

    Raises:
        CommandRejected: Another person's draft (``FORBIDDEN``), a removal
            (``INVALID_INPUT``), or a draft replaced meanwhile (``STALE_STATE``).
    """
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    selected = DISCUSSION_SPECS[old.operation_id].input_model.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_discussion_action(
            db, old.actor_id, selected, operation=old.operation_id, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


DISCUSSION_EDITORS = dict.fromkeys(DISCUSSION_SPECS, rebuild_discussion_draft)
