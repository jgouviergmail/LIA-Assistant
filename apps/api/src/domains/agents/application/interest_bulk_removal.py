"""Global erasure compares every approved source fact without sending its text to the model."""

from hashlib import sha256
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_bulk_schemas import (
    InterestBulkDeletePatch,
    InterestBulkDeleteRequest,
    InterestBulkSnapshot,
)
from src.domains.agents.application.interest_creation import interest_creation_fence
from src.domains.agents.application.interest_spec import INTEREST_BULK_DELETE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.interests.management_bulk import iter_owned_interests
from src.domains.interests.management_commands import (
    delete_all_managed_interests,
    lock_interest_actor,
)
from src.domains.interests.models import InterestCategory, InterestStatus
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def interest_bulk_snapshot(
    db: AsyncSession, actor_id: UUID, *, locked: bool = False
) -> InterestBulkSnapshot:
    digest = sha256(b"lia-interest-erasure-v1")
    categories = {item.value: 0 for item in InterestCategory}
    statuses = {item.value: 0 for item in InterestStatus}
    selected = unknown_categories = unknown_statuses = 0
    async for row in iter_owned_interests(db, actor_id, for_update=locked):
        selected += 1
        if row.category in categories:
            categories[row.category] += 1
        else:
            unknown_categories += 1
        if row.status in statuses:
            statuses[row.status] += 1
        else:
            unknown_statuses += 1
        digest.update(
            bytes.fromhex(
                payload_digest(
                    {
                        "id": row.id,
                        "topic": row.topic,
                        "category": row.category,
                        "status": row.status,
                        "subject": row.subject,
                        "positive_signals": row.positive_signals,
                        "negative_signals": row.negative_signals,
                    }
                )
            )
        )
    return InterestBulkSnapshot(
        selected_count=selected,
        by_category=categories,
        by_status=statuses,
        unknown_category_count=unknown_categories,
        unknown_status_count=unknown_statuses,
        selection_digest=digest.hexdigest(),
    )


async def prepare_interest_bulk_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: InterestBulkDeleteRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    InterestBulkDeleteRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    patch = InterestBulkDeletePatch(interests_to_delete=await interest_bulk_snapshot(db, actor_id))
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        INTEREST_BULK_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"interests_to_delete": None},
        command_id=command_id,
    )


async def execute_interest_bulk_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    expected = InterestBulkDeletePatch.model_validate(draft.intent).interests_to_delete
    if draft.intent != draft.before or draft.after != {"interests_to_delete": None}:
        raise ValueError("Global deletion must retain the confirmed complete scope")
    await interest_creation_fence(db, actor_id, draft)
    await lock_interest_actor(db, actor_id)
    await interest_creation_fence(db, actor_id, draft)
    if await interest_bulk_snapshot(db, actor_id, locked=True) != expected:
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})
    receipt.no_op = expected.selected_count == 0
    if not receipt.no_op:
        removed = await delete_all_managed_interests(db, actor_id)
        if removed != expected.selected_count:
            raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})
    await interest_creation_fence(db, actor_id, draft)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
