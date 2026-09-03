"""Heartbeat notification feedback: persistence beyond the column.

The endpoint has always written ``heartbeat_notifications.user_feedback``, but
nothing marked the archived chat card — so the buttons (which did not exist at
all until 2026-07-27) would have come back on every reload and the same
notification could be rated indefinitely. The interest route solved that long
ago; this one now shares the mechanism.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ResourceNotFoundError
from src.domains.heartbeat.router import submit_heartbeat_feedback
from src.domains.heartbeat.schemas import HeartbeatFeedbackRequest

pytestmark = pytest.mark.unit


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


class TestSubmitHeartbeatFeedback:
    async def test_the_verdict_reaches_the_notification(self) -> None:
        user = _user()
        notification_id = uuid.uuid4()
        db = AsyncMock()

        with (
            patch("src.domains.heartbeat.router.HeartbeatNotificationRepository") as repo_cls,
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
        ):
            repo_cls.return_value.update_feedback = AsyncMock(return_value=True)
            repo_cls.return_value.get_by_id = AsyncMock(return_value=MagicMock(habit_offer_id=None))
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=1)

            await submit_heartbeat_feedback(
                notification_id=notification_id,
                data=HeartbeatFeedbackRequest(feedback="thumbs_up"),
                user=user,
                db=db,
            )

            repo_cls.return_value.update_feedback.assert_awaited_once_with(
                notification_id=notification_id, user_id=user.id, feedback="thumbs_up"
            )
            db.commit.assert_awaited_once()

    async def test_the_archived_card_is_marked_so_the_buttons_stay_hidden(self) -> None:
        user = _user()
        notification_id = uuid.uuid4()

        with (
            patch("src.domains.heartbeat.router.HeartbeatNotificationRepository") as repo_cls,
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
        ):
            repo_cls.return_value.update_feedback = AsyncMock(return_value=True)
            repo_cls.return_value.get_by_id = AsyncMock(return_value=MagicMock(habit_offer_id=None))
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=1)

            await submit_heartbeat_feedback(
                notification_id=notification_id,
                data=HeartbeatFeedbackRequest(feedback="thumbs_down"),
                user=user,
                db=AsyncMock(),
            )

            # target_id is the notification id — the same key the archived
            # metadata carries for a proactive_heartbeat card. That equality
            # is not an assumption of this test: it is produced by
            # `generate_content` and pinned by
            # tests/unit/domains/heartbeat/test_notification_identity.py.
            # Both halves are mocked here, so this file alone could not tell
            # the difference — and for a long time it did not: the two values
            # diverged while this comment claimed they matched.
            conv_cls.return_value.mark_proactive_feedback_submitted.assert_awaited_once_with(
                user_id=user.id, target_id=notification_id, feedback_value="thumbs_down"
            )

    async def test_an_unknown_notification_is_rejected_and_marks_nothing(self) -> None:
        user = _user()
        db = AsyncMock()

        with (
            patch("src.domains.heartbeat.router.HeartbeatNotificationRepository") as repo_cls,
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
        ):
            repo_cls.return_value.update_feedback = AsyncMock(return_value=False)
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock()

            with pytest.raises(ResourceNotFoundError):
                await submit_heartbeat_feedback(
                    notification_id=uuid.uuid4(),
                    data=HeartbeatFeedbackRequest(feedback="thumbs_up"),
                    user=user,
                    db=db,
                )

            conv_cls.return_value.mark_proactive_feedback_submitted.assert_not_awaited()
            db.commit.assert_not_awaited()

    async def test_a_habit_offer_verdict_bumps_the_habit_signals(self) -> None:
        """ADR-214: a verdict on a notification that carried a missed-routine
        offer is a verdict on the habit itself — thumbs_up bumps positive,
        thumbs_down bumps negative, in the SAME transaction."""
        user = _user()
        notification_id = uuid.uuid4()
        habit_id = uuid.uuid4()
        db = AsyncMock()

        with (
            patch("src.domains.heartbeat.router.HeartbeatNotificationRepository") as repo_cls,
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
            patch("src.domains.habits.repository.HabitsRepository") as habits_cls,
        ):
            repo_cls.return_value.update_feedback = AsyncMock(return_value=True)
            repo_cls.return_value.get_by_id = AsyncMock(
                return_value=MagicMock(habit_offer_id=habit_id)
            )
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=1)
            habits_cls.return_value.record_feedback = AsyncMock()

            await submit_heartbeat_feedback(
                notification_id=notification_id,
                data=HeartbeatFeedbackRequest(feedback="thumbs_down"),
                user=user,
                db=db,
            )

            habits_cls.return_value.record_feedback.assert_awaited_once_with(
                habit_id, user.id, positive=False
            )
            db.commit.assert_awaited_once()


class TestThumbIsPresence:
    """ADR-214 amendment (owner decision 2026-09-03): a thumb is an explicit
    human act — a reading-presence signal for the rhythm detector. The
    notification itself never was."""

    async def test_a_thumb_records_feedback_presence_before_commit(self) -> None:
        user = _user()
        notification_id = uuid.uuid4()
        db = AsyncMock()
        order: list[str] = []
        db.commit = AsyncMock(side_effect=lambda: order.append("commit"))
        recorder = AsyncMock(side_effect=lambda *a, **k: order.append("presence") or "banked")

        with (
            patch("src.domains.heartbeat.router.HeartbeatNotificationRepository") as repo_cls,
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
            patch("src.domains.habits.presence.record_presence", recorder),
        ):
            repo_cls.return_value.update_feedback = AsyncMock(return_value=True)
            repo_cls.return_value.get_by_id = AsyncMock(return_value=MagicMock(habit_offer_id=None))
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=1)

            await submit_heartbeat_feedback(
                notification_id=notification_id,
                data=HeartbeatFeedbackRequest(feedback="thumbs_down"),
                user=user,
                db=db,
            )

        recorder.assert_awaited_once()
        assert recorder.await_args.args[1] is user
        assert recorder.await_args.kwargs["kind"] == "feedback"
        assert order == ["presence", "commit"]  # same transaction as the verdict
