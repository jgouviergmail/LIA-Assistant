"""Revised requests resolve fresh owned facts and replace the same pending command."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_template_preparation import (
    prepare_template_creation,
    prepare_template_removal,
    prepare_template_replacement,
)
from src.domains.agents.application.meeting_template_schemas import (
    TemplateCreateInput,
    TemplateCreatePatch,
    TemplateDeleteInput,
    TemplateUpdateInput,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_meeting_template(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        if old.operation_id == "meeting_template.create":
            selection = TemplateCreatePatch.model_validate(old.intent).meeting_template_create
            revised = await prepare_template_creation(
                db,
                old.actor_id,
                TemplateCreateInput.model_validate(modified.get("intent")),
                command_id=old.command_id,
                created_id=selection.created_id,
            )
        elif old.operation_id == "meeting_template.update":
            revised = await prepare_template_replacement(
                db,
                old.actor_id,
                TemplateUpdateInput.model_validate(modified.get("intent")),
                command_id=old.command_id,
            )
        elif old.operation_id == "meeting_template.delete":
            revised = await prepare_template_removal(
                db,
                old.actor_id,
                TemplateDeleteInput.model_validate(modified.get("intent")),
                command_id=old.command_id,
            )
        else:
            raise CommandRejected("INVALID_INPUT")
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
