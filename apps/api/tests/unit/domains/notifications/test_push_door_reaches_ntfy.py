"""The push door reaches ntfy too (ADR-391).

``FCMNotificationService.send_to_user`` is where every push of a person starts — reminders,
routines, proactive notices, a new sign-in, an export, a broken connector. Publishing to ntfy here,
once, is what makes every one of them reach a person who has no Firebase device; and a
publication a server accepted counts as delivered, like a push.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.core.notification_privacy import PRIVATE_NOTIFICATION_MARKER, NotificationPrivacy
from src.domains.notifications import service as push_service
from src.domains.notifications.ntfy_delivery import NtfyBatch, NtfyTargetsUnreadable
from src.domains.notifications.service import FCMNotificationService, FCMSendResult
from src.infrastructure.external.ntfy_client import NtfyOutcome

pytestmark = pytest.mark.unit


def _service(tokens: list[Any]) -> FCMNotificationService:
    service = FCMNotificationService(db=Mock())
    service.get_active_tokens = AsyncMock(return_value=tokens)  # type: ignore[method-assign]
    service.repository = Mock(update_last_used=AsyncMock(), deactivate_token=AsyncMock())
    return service


@pytest.fixture
def ntfy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    door = AsyncMock(return_value=NtfyBatch(outcomes=(NtfyOutcome.SENT,)))
    monkeypatch.setattr(push_service, "push_to_ntfy", door)
    return door


async def test_a_person_with_no_device_is_reached_through_ntfy(ntfy: AsyncMock) -> None:
    user = uuid4()

    result = await _service([]).send_to_user(user, "Rappel", "Appeler Marie", data={"type": "x"})

    assert (result.success_count, result.failure_count) == (1, 0)
    ntfy.assert_awaited_once()
    assert ntfy.await_args_list[-1].args == (user,)
    assert ntfy.await_args_list[-1].kwargs["title"] == "Rappel"
    assert ntfy.await_args_list[-1].kwargs["body"] == "Appeler Marie"


async def test_devices_and_topics_are_counted_together(ntfy: AsyncMock) -> None:
    ntfy.return_value = NtfyBatch(outcomes=(NtfyOutcome.SENT, NtfyOutcome.AUTH_REFUSED))
    service = _service([Mock(id=uuid4(), token="t1")])
    service._send_to_token = AsyncMock(  # type: ignore[method-assign]
        return_value=FCMSendResult(success=True, token="t1")
    )

    result = await service.send_to_user(uuid4(), "T", "B")

    assert (result.success_count, result.failure_count) == (2, 1)


async def test_the_link_and_the_privacy_travel_with_the_notification(ntfy: AsyncMock) -> None:
    await _service([]).send_to_user(
        uuid4(),
        "LIA",
        "Un point",
        data={"url": "/dashboard/chat?conversation=c1", PRIVATE_NOTIFICATION_MARKER: "true"},
    )

    kwargs = ntfy.await_args_list[-1].kwargs
    assert kwargs["click_path"] == "/dashboard/chat?conversation=c1"
    assert kwargs["privacy"] is NotificationPrivacy.IN_APP_SENSITIVE


async def test_an_ordinary_notification_is_not_kept_in_lia(ntfy: AsyncMock) -> None:
    await _service([]).send_to_user(uuid4(), "T", "B", data={"type": "reminder"})

    kwargs = ntfy.await_args_list[-1].kwargs
    assert kwargs["click_path"] is None
    assert kwargs["privacy"] is NotificationPrivacy.NORMAL


async def test_topics_are_published_before_any_device_status_is_written(
    ntfy: AsyncMock,
) -> None:
    """A status write takes a row lock the caller's transaction keeps: nothing waits on a
    server while it is held (ADR-304)."""
    order: list[str] = []

    async def publish(*args: Any, **kwargs: Any) -> NtfyBatch:
        order.append("ntfy")
        return NtfyBatch(outcomes=(NtfyOutcome.SENT,))

    async def write_status(*args: Any) -> None:
        order.append("status")

    ntfy.side_effect = publish
    service = _service([Mock(id=uuid4(), token="t1")])
    service._send_to_token = AsyncMock(  # type: ignore[method-assign]
        return_value=FCMSendResult(success=True, token="t1")
    )
    service.repository = Mock(update_last_used=AsyncMock(side_effect=write_status))

    await service.send_to_user(uuid4(), "T", "B")

    assert order == ["ntfy", "status"]


@pytest.mark.parametrize("failure", [NtfyTargetsUnreadable(), RuntimeError("bug")])
async def test_a_failing_topic_never_unsays_the_devices(
    ntfy: AsyncMock, failure: Exception
) -> None:
    """The pushes left: a caller that saw an exception would send them again."""
    ntfy.side_effect = failure
    service = _service([Mock(id=uuid4(), token="t1")])
    service._send_to_token = AsyncMock(  # type: ignore[method-assign]
        return_value=FCMSendResult(success=True, token="t1")
    )
    repository = Mock(update_last_used=AsyncMock(), deactivate_token=AsyncMock())
    service.repository = repository

    result = await service.send_to_user(uuid4(), "T", "B")

    assert (result.success_count, result.failure_count) == (1, 0)
    repository.update_last_used.assert_awaited_once()
