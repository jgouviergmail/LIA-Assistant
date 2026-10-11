"""Fresh owned dormancy and complete reset facts are required for exact HITL execution."""

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
from src.domains.agents.application.interest_reactivation_schemas import (
    InterestReactivateRequest,
    InterestReactivationPatch,
    InterestReactivationValues,
    canonical_interest_reactivation,
    reactivation_result,
)
from src.domains.agents.application.interest_spec import INTEREST_REACTIVATE_OPERATION
from src.domains.interests.management_commands import get_managed_interest, lock_interest_actor
from src.domains.interests.management_reactivation import (
    interest_reactivation_snapshot,
    reactivate_managed_interest,
    require_dormant_interest,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_interest_reactivation(
    db: AsyncSession,
    actor_id: UUID,
    selection: InterestReactivateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    request = InterestReactivateRequest.model_validate(selection.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await get_managed_interest(db, actor_id, request.interest_id)
    require_dormant_interest(row)
    values = InterestReactivationValues(
        expected=interest_reactivation_snapshot(row), result=reactivation_result()
    )
    patch = InterestReactivationPatch(interest_to_reactivate=values)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        INTEREST_REACTIVATE_OPERATION,
        patch,
        {"interest_to_reactivate": values.expected.model_dump(mode="json")},
        {"interest_to_reactivate": values.result.model_dump(mode="json")},
        command_id=command_id,
    )


async def execute_interest_reactivation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    values = InterestReactivationPatch.model_validate(draft.intent).interest_to_reactivate
    if not canonical_interest_reactivation(draft):
        raise ValueError("Reactivation must retain the source reset and confirmed target")
    await interest_creation_fence(db, actor_id, draft)
    await lock_interest_actor(db, actor_id)
    await interest_creation_fence(db, actor_id, draft)
    try:
        await reactivate_managed_interest(
            db, actor_id, values.expected.id, expected=values.expected
        )
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"}) from exc
    await interest_creation_fence(db, actor_id, draft)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
