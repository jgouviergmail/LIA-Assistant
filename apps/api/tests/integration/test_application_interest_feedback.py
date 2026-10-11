"""Feedback binds its actual source interest and optional notification before approval."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application import interest_feedback
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.interest_feedback_schemas import InterestFeedbackSelection
from src.domains.agents.application.interest_history import read_interest_history
from src.domains.agents.application.interest_history_schemas import InterestHistoryRead
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


async def test_notification_verdict_updates_only_its_card_and_entity_scope_keeps_source_breadth(
    async_session: AsyncSession, test_user: User
) -> None:
    owner = test_user.id
    row = UserInterest(
        user_id=owner, topic="Card topic", category="science", last_mentioned_at=datetime.now(UTC)
    )
    conversation = Conversation(user_id=owner)
    async_session.add_all([row, conversation])
    await async_session.flush()
    notifications, cards = [], []
    for index in range(2):
        run_id = f"card-{uuid4()}"
        notification = InterestNotification(
            user_id=owner,
            interest_id=row.id,
            run_id=run_id,
            content=f"Delivered {index}",
            content_hash=str(index) * 64,
            source="test",
        )
        card = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=f"Delivered {index}",
            message_metadata={
                "type": "proactive_interest",
                "target_id": str(row.id),
                "run_id": run_id,
                "feedback_enabled": True,
            },
        )
        notifications.append(notification)
        cards.append(card)
    async_session.add_all([*notifications, *cards])
    await async_session.commit()
    with patch("src.domains.habits.presence.record_presence", new_callable=AsyncMock):
        draft = await interest_feedback.prepare_interest_feedback(
            async_session,
            owner,
            InterestFeedbackSelection(notification_id=notifications[1].id, feedback="thumbs_down"),
        )
        await interest_feedback.execute_interest_feedback(
            async_session, owner, draft, PreferenceWriteReceipt()
        )
        for item in [*notifications, *cards]:
            await async_session.refresh(item)
        assert (
            notifications[0].user_feedback is None
            and notifications[1].user_feedback == "thumbs_down"
        )
        assert not cards[0].message_metadata.get("feedback_submitted")
        assert cards[1].message_metadata["feedback_submitted"] is True
        assert cards[1].message_metadata["feedback_value"] == "thumbs_down"
        draft = await interest_feedback.prepare_interest_feedback(
            async_session, owner, InterestFeedbackSelection(interest_id=row.id, feedback="block")
        )
        await interest_feedback.execute_interest_feedback(
            async_session, owner, draft, PreferenceWriteReceipt()
        )
        for item in [*notifications, *cards]:
            await async_session.refresh(item)
        assert (
            notifications[0].user_feedback is None
            and notifications[1].user_feedback == "thumbs_down"
        )
        assert all(
            card.message_metadata["feedback_submitted"] is True
            and card.message_metadata["feedback_value"] == "block"
            for card in cards
        )


@pytest.mark.parametrize(
    "scenario",
    [
        "thumbs_up",
        "thumbs_down",
        "block",
        "notification",
        "notification_block",
        "stale",
        "deleted",
        "feedback_changed",
        "late_disabled",
        "disabled_during_effects",
        "unknown_commit",
    ],
)
async def test_confirmed_interest_feedback_and_audit_truth(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    owner = test_user.id
    row = UserInterest(
        user_id=owner,
        topic="Owned topic",
        category="science",
        positive_signals=4,
        negative_signals=1,
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.flush()
    notification = InterestNotification(
        user_id=owner,
        interest_id=row.id,
        run_id=f"feedback-{uuid4()}",
        content="Delivered text",
        content_hash="a" * 64,
        source="test",
    )
    async_session.add(notification)
    await async_session.commit()
    identity, notification_id, revision = row.id, notification.id, test_user.extraction_revision
    feedback = (
        "block"
        if scenario in {"block", "notification_block"}
        else ("thumbs_down" if scenario == "thumbs_down" else "thumbs_up")
    )
    selection = InterestFeedbackSelection(
        **(
            {"notification_id": notification_id}
            if scenario in {"notification", "notification_block", "feedback_changed"}
            else {"interest_id": identity}
        ),
        feedback=feedback,
    )

    async def record_presence(*args, **kwargs):
        if scenario == "disabled_during_effects":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return "disabled"

    presence = AsyncMock(side_effect=record_presence)
    with patch("src.domains.habits.presence.record_presence", presence):
        draft = await interest_feedback.prepare_interest_feedback(async_session, owner, selection)
        presence.assert_not_called()
        assert row.positive_signals == 4 and notification.user_feedback is None
        assert notification.run_id not in str(draft.before)
        if scenario == "stale":
            await async_session.execute(
                update(UserInterest).where(UserInterest.id == identity).values(negative_signals=2)
            )
            await async_session.commit()
        elif scenario == "deleted":
            await async_session.delete(row)
            await async_session.commit()
        elif scenario == "feedback_changed":
            await async_session.execute(
                update(InterestNotification)
                .where(InterestNotification.id == notification_id)
                .values(user_feedback="thumbs_down", feedback_at=datetime.now(UTC))
            )
            await async_session.commit()
        elif scenario == "late_disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        receipt = PreferenceWriteReceipt()
        if scenario in {"stale", "deleted", "feedback_changed"}:
            with pytest.raises(ResourceConflictError):
                await interest_feedback.execute_interest_feedback(
                    async_session, owner, draft, receipt
                )
            await async_session.rollback()
            presence.assert_not_called()
            return
        if scenario in {"late_disabled", "disabled_during_effects"}:
            with pytest.raises(AuthorizationError):
                await interest_feedback.execute_interest_feedback(
                    async_session, owner, draft, receipt
                )
            await async_session.rollback()
            if scenario == "late_disabled":
                presence.assert_not_called()
            else:
                await async_session.refresh(row)
                await async_session.refresh(test_user)
                assert row.positive_signals == 4 and test_user.extraction_revision == revision
                presence.assert_awaited_once()
            return
        if scenario == "unknown_commit":
            with patch.object(async_session, "commit", side_effect=SQLAlchemyError("ack lost")):
                with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                    await interest_feedback.execute_interest_feedback(
                        async_session, owner, draft, receipt
                    )
            await async_session.rollback()
            assert not receipt.committed
            return
        await interest_feedback.execute_interest_feedback(async_session, owner, draft, receipt)
        assert receipt.committed
        await async_session.refresh(row)
        await async_session.refresh(notification)
        await async_session.refresh(test_user)
        assert (row.positive_signals, row.negative_signals, row.status) == (
            6 if feedback == "thumbs_up" else 4,
            3 if feedback == "thumbs_down" else 1,
            "blocked" if feedback == "block" else "active",
        )
        assert test_user.extraction_revision == revision + 1
        assert notification.user_feedback == (
            feedback if selection.notification_id is not None else None
        )
        assert (await read_interest_history(async_session, owner, InterestHistoryRead())).total == 1
        presence.assert_awaited_once()


async def test_notification_selection_refuses_a_foreign_interest_relationship(
    async_session: AsyncSession, test_user: User
) -> None:
    foreign = User(
        id=uuid4(),
        email=f"feedback-other-{uuid4()}@example.test",
        full_name="Other",
        is_active=True,
        is_verified=True,
    )
    async_session.add(foreign)
    await async_session.flush()
    row = UserInterest(
        user_id=foreign.id,
        topic="Foreign topic",
        category="science",
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.flush()
    notification = InterestNotification(
        user_id=test_user.id,
        interest_id=row.id,
        run_id=f"malformed-{uuid4()}",
        content="Own delivered text",
        content_hash="b" * 64,
        source="test",
    )
    async_session.add(notification)
    await async_session.commit()
    with pytest.raises(ResourceNotFoundError):
        await interest_feedback.prepare_interest_feedback(
            async_session,
            test_user.id,
            InterestFeedbackSelection(notification_id=notification.id, feedback="block"),
        )
