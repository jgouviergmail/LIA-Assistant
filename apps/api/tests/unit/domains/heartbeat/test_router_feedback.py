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
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=1)

            await submit_heartbeat_feedback(
                notification_id=notification_id,
                data=HeartbeatFeedbackRequest(feedback="thumbs_down"),
                user=user,
                db=AsyncMock(),
            )

            # target_id is the notification id — the same key the archived
            # metadata carries for a proactive_heartbeat card.
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
