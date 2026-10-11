"""Exact confirmation precedes shared source feedback and its current ownership fence."""

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
from src.domains.agents.application.interest_feedback_schemas import (
    InterestFeedbackNotification,
    InterestFeedbackPatch,
    InterestFeedbackSelection,
    InterestFeedbackValues,
)
from src.domains.agents.application.interest_spec import INTEREST_FEEDBACK_OPERATION
from src.domains.agents.application.interest_update import interest_edit_snapshot
from src.domains.agents.effects.digest import payload_digest
from src.domains.interests.feedback_policy import feedback_signal_changes
from src.domains.interests.management_commands import (
    get_managed_interest,
    lock_interest_actor,
    preview_interest_update,
)
from src.domains.interests.management_feedback import (
    apply_interest_feedback_effects,
    get_feedback_notification,
    record_interest_feedback_metric,
)
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.interests.schemas import InterestUpdate
from src.domains.users.preference_cas import PreferenceWriteReceipt


def feedback_notification_snapshot(row: InterestNotification) -> InterestFeedbackNotification:
    assert row.interest_id is not None
    return InterestFeedbackNotification(
        id=row.id,
        interest_id=row.interest_id,
        created_at=row.created_at,
        user_feedback=row.user_feedback,
        feedback_at=row.feedback_at,
        source_digest=payload_digest(
            {"run_id": row.run_id, "content_hash": row.content_hash, "source": row.source}
        ),
    )


def feedback_after(previous: InterestFeedbackValues) -> InterestFeedbackValues:
    positive, negative, status = feedback_signal_changes(
        previous.configuration.positive_signals,
        previous.configuration.negative_signals,
        previous.expected.status.value,
        previous.feedback,
    )
    return InterestFeedbackValues.model_validate(
        {
            **previous.model_dump(),
            "expected": {**previous.expected.model_dump(), "status": status},
            "configuration": {
                **previous.configuration.model_dump(),
                "positive_signals": positive,
                "negative_signals": negative,
            },
        }
    )


async def _feedback_target(
    db: AsyncSession, owner: UUID, selection: InterestFeedbackSelection, *, lock: bool = False
) -> tuple[UserInterest, InterestNotification | None]:
    notification = None
    if selection.notification_id is not None:
        # Read the link, then lock in account -> interest -> notification order.
        notification = await get_feedback_notification(db, owner, selection.notification_id)
        interest_id = notification.interest_id
        assert interest_id is not None
    else:
        assert selection.interest_id is not None
        interest_id = selection.interest_id
    row = await get_managed_interest(db, owner, interest_id, lock=lock)
    if lock and notification is not None:
        notification = await get_feedback_notification(db, owner, notification.id, lock=True)
        if notification.interest_id != row.id:
            raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})
    return row, notification


async def prepare_interest_feedback(
    db: AsyncSession,
    actor_id: UUID,
    selection: InterestFeedbackSelection,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    request = InterestFeedbackSelection.model_validate(selection.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row, notification = await _feedback_target(db, actor_id, request)
    previous = InterestFeedbackValues(
        expected=interest_edit_snapshot(row),
        configuration=preview_interest_update(row, InterestUpdate()),
        feedback=request.feedback,
        notification=(
            feedback_notification_snapshot(notification) if notification is not None else None
        ),
        card_scope="one_notification" if notification is not None else "all_interest_cards",
    )
    before = InterestFeedbackPatch(interest_feedback=previous)
    after = InterestFeedbackPatch(interest_feedback=feedback_after(previous))
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        INTEREST_FEEDBACK_OPERATION,
        after,
        before.model_dump(mode="json"),
        after.model_dump(mode="json"),
        command_id=command_id,
    )


def require_feedback_snapshot(
    row: UserInterest, notification: InterestNotification | None, previous: InterestFeedbackValues
) -> None:
    observed_notification = feedback_notification_snapshot(notification) if notification else None
    if (
        interest_edit_snapshot(row) != previous.expected
        or preview_interest_update(row, InterestUpdate()) != previous.configuration
        or observed_notification != previous.notification
    ):
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})


async def execute_interest_feedback(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    previous = InterestFeedbackPatch.model_validate(draft.before).interest_feedback
    desired = InterestFeedbackPatch.model_validate(draft.intent).interest_feedback
    if feedback_after(previous) != desired or draft.intent != draft.after:
        raise ValueError("Confirmed feedback must match the source verdict and target")
    if previous.card_scope != (
        "one_notification" if previous.notification else "all_interest_cards"
    ):
        raise ValueError("Notification scope must match the selected source")
    await interest_creation_fence(db, actor_id, draft)
    actor = await lock_interest_actor(db, actor_id)
    await interest_creation_fence(db, actor_id, draft)
    selection = InterestFeedbackSelection(
        feedback=previous.feedback,
        interest_id=None if previous.notification else previous.expected.id,
        notification_id=previous.notification.id if previous.notification else None,
    )
    try:
        row, notification = await _feedback_target(db, actor_id, selection, lock=True)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"}) from exc
    require_feedback_snapshot(row, notification, previous)
    effects = await apply_interest_feedback_effects(
        db,
        actor,
        row,
        previous.feedback,
        run_id=notification.run_id if notification else None,
    )
    if notification is not None and not effects.audit_updated:
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})
    await interest_creation_fence(db, actor_id, draft)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    record_interest_feedback_metric(previous.feedback)
