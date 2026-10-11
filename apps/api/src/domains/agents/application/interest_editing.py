"""Creation proposal edits keep the minted identity and reread current source availability."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_bulk_removal import prepare_interest_bulk_removal
from src.domains.agents.application.interest_bulk_schemas import InterestBulkDeleteRequest
from src.domains.agents.application.interest_create_schemas import InterestCreateConfiguration
from src.domains.agents.application.interest_creation import prepare_interest_creation
from src.domains.agents.application.interest_feedback import prepare_interest_feedback
from src.domains.agents.application.interest_feedback_schemas import InterestFeedbackSelection
from src.domains.agents.application.interest_reactivation import prepare_interest_reactivation
from src.domains.agents.application.interest_reactivation_schemas import InterestReactivateRequest
from src.domains.agents.application.interest_removal import prepare_interest_removal
from src.domains.agents.application.interest_removal_schemas import InterestDeleteRequest
from src.domains.agents.application.interest_update import prepare_interest_update
from src.domains.agents.application.interest_update_schemas import InterestUpdateRequest
from src.domains.agents.context.runtime_context import runtime_context_if_running


async def rebuild_interest_draft(
    db: AsyncSession, old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    if old.operation_id == "interests.reactivate":
        dormant_selection = InterestReactivateRequest.model_validate(modified.get("intent"))
        revised = await prepare_interest_reactivation(
            db, old.actor_id, dormant_selection, command_id=old.command_id
        )
    elif old.operation_id == "interests.feedback":
        verdict_selection = InterestFeedbackSelection.model_validate(modified.get("intent"))
        revised = await prepare_interest_feedback(
            db, old.actor_id, verdict_selection, command_id=old.command_id
        )
    elif old.operation_id == "interests.create":
        configuration = InterestCreateConfiguration.model_validate(modified.get("intent"))
        revised = await prepare_interest_creation(
            db, old.actor_id, configuration, command_id=old.command_id
        )
    elif old.operation_id == "interests.delete_all":
        scope = InterestBulkDeleteRequest.model_validate(modified.get("intent"))
        revised = await prepare_interest_bulk_removal(
            db, old.actor_id, scope, command_id=old.command_id
        )
    elif old.operation_id == "interests.delete":
        selection = InterestDeleteRequest.model_validate(modified.get("intent"))
        revised = await prepare_interest_removal(
            db, old.actor_id, selection, command_id=old.command_id
        )
    elif old.operation_id == "interests.update":
        request = InterestUpdateRequest.model_validate(modified.get("intent"))
        revised = await prepare_interest_update(
            db, old.actor_id, request, command_id=old.command_id
        )
    else:
        raise CommandRejected("UNKNOWN_OPERATION")
    if not await replace_pending_command(db, old, revised):
        raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
