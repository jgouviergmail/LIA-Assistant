"""Exact management edits spend after approval and reuse one source write owner."""

from functools import partial
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_creation import interest_creation_fence
from src.domains.agents.application.interest_embeddings import prepare_interest_embedding
from src.domains.agents.application.interest_spec import INTEREST_UPDATE_OPERATION
from src.domains.agents.application.interest_update_schemas import (
    InterestEditSnapshot,
    InterestUpdatePatch,
    InterestUpdateRequest,
    InterestUpdateValues,
)
from src.domains.interests.management_commands import (
    get_managed_interest,
    preview_interest_update,
    require_available_interest_configuration,
    update_managed_interest,
)
from src.domains.interests.management_schemas import InterestConfiguration
from src.domains.interests.models import UserInterest
from src.domains.interests.schemas import InterestUpdate
from src.domains.users.preference_cas import PreferenceWriteReceipt


def interest_edit_snapshot(row: UserInterest) -> InterestEditSnapshot:
    return InterestEditSnapshot(id=row.id, status=row.status, subject=row.subject)


async def prepare_interest_update(
    db: AsyncSession,
    actor_id: UUID,
    request: InterestUpdateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = InterestUpdateRequest.model_validate(request.model_dump(exclude_unset=True))
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await get_managed_interest(db, actor_id, selected.interest_id)
    previous = InterestUpdateValues(
        expected=interest_edit_snapshot(row),
        changes=selected.changes,
        configuration=InterestConfiguration.model_validate(
            preview_interest_update(row, InterestUpdate()).model_dump()
        ),
    )
    configuration = preview_interest_update(row, selected.changes)
    await require_available_interest_configuration(db, row, configuration)
    desired = previous.model_copy(
        update={"configuration": InterestConfiguration.model_validate(configuration.model_dump())}
    )
    before, after = InterestUpdatePatch(interest_configuration=previous), InterestUpdatePatch(
        interest_configuration=desired
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        INTEREST_UPDATE_OPERATION,
        after,
        before.model_dump(mode="json", exclude_unset=True),
        after.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def _current_interest(
    db: AsyncSession, actor_id: UUID, expected: InterestUpdateValues
) -> UserInterest:
    try:
        row = await get_managed_interest(db, actor_id, expected.expected.id)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"}) from exc
    if (
        interest_edit_snapshot(row) != expected.expected
        or preview_interest_update(row, InterestUpdate()).model_dump()
        != expected.configuration.model_dump()
    ):
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})
    return row


async def execute_interest_update(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    desired = InterestUpdatePatch.model_validate(draft.intent).interest_configuration
    previous = InterestUpdatePatch.model_validate(draft.before).interest_configuration
    if (
        desired.expected != previous.expected
        or desired.changes != previous.changes
        or draft.intent != draft.after
    ):
        raise ValueError("An interest edit cannot replace its confirmed fact or delta")
    guard = partial(interest_creation_fence, db, actor_id, draft)
    await guard()
    row = await _current_interest(db, actor_id, previous)
    if (
        preview_interest_update(row, desired.changes).model_dump()
        != desired.configuration.model_dump()
    ):
        raise ValueError("The confirmed interest result must match its source delta")
    await require_available_interest_configuration(db, row, desired.configuration)
    topic_changed = desired.configuration.topic != previous.configuration.topic
    assert desired.configuration.topic is not None
    embedding = (
        await prepare_interest_embedding(
            actor_id, draft.command_id, desired.configuration.topic, guard
        )
        if topic_changed
        else None
    )
    await guard()
    try:
        _, receipt.no_op = await update_managed_interest(
            db,
            actor_id,
            row,
            desired.changes,
            embedding=embedding,
            expected=previous.configuration,
            expected_status=previous.expected.status.value,
            expected_subject=previous.expected.subject,
        )
    except IntegrityError as exc:
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"}) from exc
    except ResourceNotFoundError as exc:
        await guard()
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"}) from exc
    await guard()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
