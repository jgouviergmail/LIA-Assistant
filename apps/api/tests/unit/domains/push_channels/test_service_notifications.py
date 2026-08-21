"""Push channel notification handling (lot H, 2026-08).

Security and idempotency contract of the webhook processing path:

- Unknown channel → ignored (could be a stale channel or a probe; never
  reveal existence, always 200 at the router).
- Known channel with a wrong token → ignored (constant-time compare).
- ``sync`` handshake → acknowledged without cache invalidation.
- Valid notification → per-provider cache invalidation, debounced per channel
  against notification storms.
- Gmail (phase 2): platform push token gate + historyId dedup (out-of-order
  and duplicate Pub/Sub deliveries are expected).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.push_channels.models import PushChannelProvider
from src.domains.push_channels.notifications import ChannelNotification, GmailPushEvent
from src.domains.push_channels.service import NotificationOutcome, PushChannelService

pytestmark = pytest.mark.unit


def _notif(**overrides: Any) -> ChannelNotification:
    base: dict[str, Any] = {
        "channel_id": "chan-1",
        "token": "secret",
        "resource_id": "res-1",
        "resource_state": "exists",
        "message_number": 7,
    }
    base.update(overrides)
    return ChannelNotification(**base)


def _channel(**overrides: Any) -> MagicMock:
    channel = MagicMock()
    channel.id = uuid4()
    channel.user_id = uuid4()
    channel.provider = PushChannelProvider.GOOGLE_CALENDAR.value
    channel.channel_id = "chan-1"
    channel.token = "secret"
    channel.resource_id = "res-1"
    channel.last_history_id = None
    for key, value in overrides.items():
        setattr(channel, key, value)
    return channel


def _service(channel: MagicMock | None) -> PushChannelService:
    repo = MagicMock()
    repo.get_by_channel_id = AsyncMock(return_value=channel)
    repo.get_by_provider_target = AsyncMock(return_value=channel)
    db = MagicMock()
    db.commit = AsyncMock()
    return PushChannelService(db, repository=repo)


class TestChannelNotifications:
    async def test_unknown_channel_is_ignored(self) -> None:
        service = _service(channel=None)
        outcome = await service.handle_channel_notification(_notif())
        assert outcome is NotificationOutcome.IGNORED_UNKNOWN

    async def test_bad_token_is_ignored(self) -> None:
        service = _service(_channel(token="other-secret"))
        outcome = await service.handle_channel_notification(_notif(token="forged"))
        assert outcome is NotificationOutcome.IGNORED_BAD_TOKEN

    async def test_sync_handshake_acks_without_invalidation(self) -> None:
        service = _service(_channel())
        with patch(
            "src.domains.push_channels.service.invalidate_for_provider", new=AsyncMock()
        ) as invalidate:
            outcome = await service.handle_channel_notification(_notif(resource_state="sync"))
        assert outcome is NotificationOutcome.SYNC_ACK
        invalidate.assert_not_awaited()

    async def test_valid_notification_invalidates_provider_caches(self) -> None:
        channel = _channel()
        service = _service(channel)
        with (
            patch(
                "src.domains.push_channels.service.invalidate_for_provider", new=AsyncMock()
            ) as invalidate,
            patch.object(service, "_try_acquire_debounce", new=AsyncMock(return_value=True)),
        ):
            outcome = await service.handle_channel_notification(_notif())
        assert outcome is NotificationOutcome.PROCESSED
        invalidate.assert_awaited_once_with(
            PushChannelProvider.GOOGLE_CALENDAR.value, channel.user_id
        )

    async def test_notification_storm_is_debounced(self) -> None:
        service = _service(_channel())
        with (
            patch(
                "src.domains.push_channels.service.invalidate_for_provider", new=AsyncMock()
            ) as invalidate,
            patch.object(service, "_try_acquire_debounce", new=AsyncMock(return_value=False)),
        ):
            outcome = await service.handle_channel_notification(_notif())
        assert outcome is NotificationOutcome.DEBOUNCED
        invalidate.assert_not_awaited()


class TestGmailPush:
    _EVENT = GmailPushEvent(email_address="user@gmail.com", history_id=100)

    async def test_wrong_platform_token_is_ignored(self) -> None:
        service = _service(_channel(provider=PushChannelProvider.GOOGLE_GMAIL.value))
        with patch("src.domains.push_channels.service.settings") as mock_settings:
            mock_settings.gmail_pubsub_push_token = "platform-secret"
            outcome = await service.handle_gmail_push(self._EVENT, provided_token="wrong")
        assert outcome is NotificationOutcome.IGNORED_BAD_TOKEN

    async def test_unknown_mailbox_is_ignored(self) -> None:
        service = _service(channel=None)
        with patch("src.domains.push_channels.service.settings") as mock_settings:
            mock_settings.gmail_pubsub_push_token = "platform-secret"
            outcome = await service.handle_gmail_push(self._EVENT, provided_token="platform-secret")
        assert outcome is NotificationOutcome.IGNORED_UNKNOWN

    async def test_stale_history_id_is_deduplicated(self) -> None:
        channel = _channel(provider=PushChannelProvider.GOOGLE_GMAIL.value, last_history_id=100)
        service = _service(channel)
        with (
            patch("src.domains.push_channels.service.settings") as mock_settings,
            patch(
                "src.domains.push_channels.service.invalidate_for_provider", new=AsyncMock()
            ) as invalidate,
        ):
            mock_settings.gmail_pubsub_push_token = "platform-secret"
            outcome = await service.handle_gmail_push(self._EVENT, provided_token="platform-secret")
        assert outcome is NotificationOutcome.IGNORED_STALE
        invalidate.assert_not_awaited()

    async def test_new_history_id_processes_and_advances_the_ledger(self) -> None:
        channel = _channel(provider=PushChannelProvider.GOOGLE_GMAIL.value, last_history_id=50)
        service = _service(channel)
        with (
            patch("src.domains.push_channels.service.settings") as mock_settings,
            patch(
                "src.domains.push_channels.service.invalidate_for_provider", new=AsyncMock()
            ) as invalidate,
            patch.object(service, "_try_acquire_debounce", new=AsyncMock(return_value=True)),
        ):
            mock_settings.gmail_pubsub_push_token = "platform-secret"
            outcome = await service.handle_gmail_push(self._EVENT, provided_token="platform-secret")
        assert outcome is NotificationOutcome.PROCESSED
        assert channel.last_history_id == 100
        invalidate.assert_awaited_once_with(PushChannelProvider.GOOGLE_GMAIL.value, channel.user_id)
