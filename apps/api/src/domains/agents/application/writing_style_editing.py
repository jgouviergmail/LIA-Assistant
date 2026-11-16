"""An edited writing-style card is prepared again on the current record, with a new digest."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.writing_style_forgetting import (
    prepare_writing_style_forgetting,
)
from src.domains.agents.application.writing_style_learning import prepare_writing_style_learning
from src.domains.agents.application.writing_style_schemas import (
    WritingStyleForgetRequest,
    WritingStyleLearnRequest,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_writing_style_draft(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    """Prepare the card again for its own actor, on the state as it is now.

    Raises:
        CommandRejected: Another actor, a field removal, or a card replaced meanwhile.
    """
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        if old.operation_id == "writing_style.learn":
            learn = WritingStyleLearnRequest.model_validate(modified.get("intent"))
            revised = await prepare_writing_style_learning(
                db, old.actor_id, learn, command_id=old.command_id
            )
        else:
            forget = WritingStyleForgetRequest.model_validate(modified.get("intent"))
            revised = await prepare_writing_style_forgetting(
                db, old.actor_id, forget, command_id=old.command_id
            )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


#: The writing-style acts whose edited card is prepared again here, by operation.
WRITING_STYLE_EDITORS = {
    "writing_style.learn": rebuild_writing_style_draft,
    "writing_style.forget": rebuild_writing_style_draft,
}
