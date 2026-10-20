"""Sensitive model-derived notifications cannot leave the in-app boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.infrastructure.proactive.notification import NotificationDispatcher

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("sensitive", [True, False])
async def test_sensitive_delivery_masks_push_and_never_forwards_to_channels(sensitive):
    from src.core.notification_privacy import NotificationPrivacy

    dispatcher = NotificationDispatcher(
        fcm_enabled=True, sse_enabled=True, archive_enabled=True, channel_enabled=True
    )
    dispatcher._archive_message = AsyncMock(return_value={"archived": True})
    dispatcher._send_fcm = AsyncMock(return_value={"success": 1})
    dispatcher._publish_sse = AsyncMock()
    dispatcher._send_channels = AsyncMock(return_value=1)
    text = "PRIVATE_SMS rendez-vous médical Alice"
    await dispatcher.dispatch(
        user=SimpleNamespace(id=uuid4(), language="fr"),
        content=text,
        task_type="heartbeat",
        target_id=str(uuid4()),
        metadata={"sensitive_in_app_only": False},
        db=AsyncMock(),
        title="PRIVATE_SMS title",
        privacy=NotificationPrivacy.IN_APP_SENSITIVE if sensitive else NotificationPrivacy.NORMAL,
    )
    push = dispatcher._send_fcm.await_args.kwargs
    archived = dispatcher._archive_message.await_args.kwargs
    assert archived["content"] == text
    assert dispatcher._publish_sse.await_args.kwargs["content"] == text
    if sensitive:
        assert "PRIVATE_SMS" not in push["body"] + push["title"]
        assert archived["metadata"]["sensitive_in_app_only"] is True
        dispatcher._send_channels.assert_not_awaited()
    else:
        assert push["body"] == text
        dispatcher._send_channels.assert_awaited_once()
