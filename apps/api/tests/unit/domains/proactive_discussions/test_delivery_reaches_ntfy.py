"""A proactive discussion reaches ntfy too, under the same rules as its push (ADR-391).

The opening's push is masked when the opening is private; ntfy receives exactly what the push
shows, opens the discussion it belongs to, and is asked only while the opening may still go out.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.core.constants import CHAT_DISCUSSION_LINK_TEMPLATE
from src.core.notification_privacy import NotificationPrivacy
from src.domains.notifications.ntfy_delivery import NtfyBatch, NtfyTargetsUnreadable
from src.domains.proactive_discussions.outbox_repository import DiscussionDelivery
from src.infrastructure.external.ntfy_client import NtfyOutcome
from src.infrastructure.proactive import discussion_delivery as module

pytestmark = pytest.mark.unit


def _envelope(*, sensitive: bool = False) -> DiscussionDelivery:
    return DiscussionDelivery(
        owner_id=uuid4(),
        opening_id=uuid4(),
        attempt=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        run_id=uuid4(),
        context_epoch=1,
        language="fr",
        text="Et si on reparlait du voyage ?",
        sensitive=sensitive,
        metadata={},
    )


@pytest.fixture
def no_device(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def session() -> Any:
        yield Mock()

    service = Mock(get_active_tokens=AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "get_db_context", session)
    monkeypatch.setattr(module, "FCMNotificationService", Mock(return_value=service))


@pytest.mark.usefixtures("no_device")
class TestTheOpeningReachesNtfy:
    async def test_it_opens_its_own_discussion_and_counts_as_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = AsyncMock(return_value=NtfyBatch(outcomes=(NtfyOutcome.SENT,)))
        monkeypatch.setattr(module, "push_to_ntfy", door)
        monkeypatch.setattr(module, "_may_send", AsyncMock(return_value=True))
        envelope = _envelope()

        assert await module._send_pushes(envelope) is True

        door.assert_awaited_once()
        assert door.await_args_list[-1].args == (envelope.owner_id,)
        kwargs = door.await_args_list[-1].kwargs
        assert kwargs["click_path"] == CHAT_DISCUSSION_LINK_TEMPLATE.format(
            conversation_id=envelope.conversation_id
        )
        assert kwargs["body"] == envelope.text
        assert kwargs["privacy"] is NotificationPrivacy.NORMAL

    async def test_a_private_opening_leaves_as_its_push_does_without_its_words(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = AsyncMock(return_value=NtfyBatch())
        monkeypatch.setattr(module, "push_to_ntfy", door)
        monkeypatch.setattr(module, "_may_send", AsyncMock(return_value=True))

        await module._send_pushes(_envelope(sensitive=True))

        kwargs = door.await_args_list[-1].kwargs
        assert kwargs["privacy"] is NotificationPrivacy.IN_APP_SENSITIVE
        assert "voyage" not in kwargs["body"]

    async def test_an_opening_that_may_no_longer_go_out_is_not_published(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        door = AsyncMock(return_value=NtfyBatch())
        monkeypatch.setattr(module, "push_to_ntfy", door)
        monkeypatch.setattr(module, "_may_send", AsyncMock(return_value=False))

        assert await module._send_pushes(_envelope()) is False
        door.assert_not_awaited()

    @pytest.mark.parametrize("failure", [NtfyTargetsUnreadable(), RuntimeError("bug")])
    async def test_a_failing_topic_is_said_and_never_breaks_the_delivery(
        self, monkeypatch: pytest.MonkeyPatch, failure: Exception
    ) -> None:
        """No device reached and no topic: the opening reads as not delivered, as it is."""
        monkeypatch.setattr(module, "push_to_ntfy", AsyncMock(side_effect=failure))
        monkeypatch.setattr(module, "_may_send", AsyncMock(return_value=True))

        assert await module._send_pushes(_envelope()) is False
