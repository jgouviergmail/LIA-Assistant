"""What a proactive push tells the client, versus what the archive tells it.

A proactive notification reaches the reader by two roads that must describe the
SAME card: the archived message (SSE / history) and the FCM data payload the
service worker turns into a live bubble. The frontend rebuilds the card's
metadata from whichever arrived first.

Two divergences lived in the FCM half:

- **no ``run_id``** — the archived card carries it and the interest feedback
  route needs it to record a verdict on the exact notification (and, since
  2026-08-03, to avoid locking every other card of that interest). A card built
  from a push therefore produced an unattributable vote even once the audit
  join was repaired;
- **``feedback_enabled`` hardcoded to ``"true"``** while the archived metadata
  reads ``settings.proactive_feedback_enabled``. With the setting off, the push
  card offered buttons the product had disabled.

FCM data values must be strings — that is a transport constraint, not a licence
to send a different answer than the archive.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.field_names import (
    FIELD_FEEDBACK_ENABLED,
    FIELD_RUN_ID,
    FIELD_TARGET_ID,
)
from src.infrastructure.proactive.notification import NotificationDispatcher

pytestmark = pytest.mark.unit


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.language = "fr"
    return user


async def _dispatch_and_capture(*, run_id: str | None, feedback_enabled: bool) -> dict[str, str]:
    """Dispatch FCM only, and return the data payload that was sent."""
    dispatcher = NotificationDispatcher(
        fcm_enabled=True, sse_enabled=False, archive_enabled=False, channel_enabled=False
    )
    fcm_service = MagicMock()
    fcm_service.send_to_user = AsyncMock(return_value=MagicMock(success_count=1, failure_count=0))

    with (
        patch(
            "src.domains.notifications.service.FCMNotificationService",
            return_value=fcm_service,
        ),
        patch(
            "src.infrastructure.proactive.notification.settings.proactive_feedback_enabled",
            feedback_enabled,
        ),
    ):
        await dispatcher.dispatch(
            user=_user(),
            content="something worth reading",
            task_type="interest",
            target_id=str(uuid4()),
            metadata={},
            db=AsyncMock(),
            run_id=run_id,
        )

    return dict(fcm_service.send_to_user.await_args.kwargs["data"])


class TestTheFcmPayloadMatchesTheArchivedCard:
    async def test_it_carries_the_run_id(self) -> None:
        """Without it, a vote from a push card cannot name its notification."""
        data = await _dispatch_and_capture(
            run_id="proactive_interest_abc_deadbeef", feedback_enabled=True
        )

        assert data[FIELD_RUN_ID] == "proactive_interest_abc_deadbeef"

    async def test_the_run_id_is_absent_rather_than_empty_when_there_is_none(self) -> None:
        """An empty string is a value; the client would forward it as a run_id.

        `run_id` is optional on the dispatcher, so a task running outside the
        runner sends none — and the payload must say nothing rather than say
        "".
        """
        data = await _dispatch_and_capture(run_id=None, feedback_enabled=True)

        assert FIELD_RUN_ID not in data

    async def test_feedback_enabled_follows_the_setting(self) -> None:
        """The archived half reads the setting; this half used to say "true".

        Two answers to "may this card be rated?" for one notification is a
        contract divergence, and the push half was the permissive one.
        """
        data = await _dispatch_and_capture(run_id="r", feedback_enabled=False)

        assert data[FIELD_FEEDBACK_ENABLED] == "false"

    async def test_every_value_stays_a_string(self) -> None:
        """FCM rejects non-string data values — the transport constraint."""
        data = await _dispatch_and_capture(run_id="r", feedback_enabled=True)

        assert all(isinstance(value, str) for value in data.values())
        assert data[FIELD_FEEDBACK_ENABLED] == "true"
        assert data[FIELD_TARGET_ID]
