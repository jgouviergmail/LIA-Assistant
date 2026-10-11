"""Exact human approval precedes the source's owned hard deletion and revision fence."""

from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_creation import interest_creation_fence
from src.domains.agents.application.interest_removal_schemas import (
    InterestDeletePatch,
    InterestDeleteRequest,
    InterestDeleteValues,
)
from src.domains.agents.application.interest_spec import INTEREST_DELETE_OPERATION
from src.domains.agents.application.interest_update import interest_edit_snapshot
from src.domains.interests.management_commands import (
    delete_managed_interest,
    get_managed_interest,
    preview_interest_update,
)
from src.domains.interests.management_schemas import InterestConfiguration
from src.domains.interests.schemas import InterestUpdate
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_interest_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: InterestDeleteRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = InterestDeleteRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await get_managed_interest(db, actor_id, selected.interest_id)
    patch = InterestDeletePatch(
        interest_to_delete=InterestDeleteValues(
            expected=interest_edit_snapshot(row),
            configuration=InterestConfiguration.model_validate(
                preview_interest_update(row, InterestUpdate()).model_dump()
            ),
        )
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        INTEREST_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"interest_to_delete": None},
        command_id=command_id,
    )


async def execute_interest_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    target = InterestDeletePatch.model_validate(draft.intent).interest_to_delete
    if draft.intent != draft.before or draft.after != {"interest_to_delete": None}:
        raise ValueError("Deletion must retain the exact confirmed interest")
    await interest_creation_fence(db, actor_id, draft)
    try:
        await delete_managed_interest(
            db,
            actor_id,
            target.expected.id,
            expected=target.configuration,
            expected_status=target.expected.status.value,
            expected_subject=target.expected.subject,
        )
    except ResourceNotFoundError as exc:
        await interest_creation_fence(db, actor_id, draft)
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"}) from exc
    await interest_creation_fence(db, actor_id, draft)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
