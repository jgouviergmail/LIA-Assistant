"""Event-loop responsiveness tests for FCM sends (audit wave 3, item A6).

``firebase_admin.messaging.send`` is a synchronous HTTP call. When invoked
directly on the async path it freezes the whole event loop (SSE included)
for the duration of the network round-trip. These tests simulate a slow
Firebase backend and assert the loop keeps scheduling other coroutines.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.domains.notifications.service import FCMNotificationService
from tests.helpers.event_loop import measure_max_loop_stall

# Simulated Firebase round-trip. Must be much larger than the assertion
# threshold so a blocking implementation fails unambiguously.
_SIMULATED_SEND_SECONDS = 0.25
_MAX_ALLOWED_STALL_SECONDS = 0.15


def _slow_send(message: object) -> str:
    """Stand-in for messaging.send: blocks the calling thread like real HTTP."""
    time.sleep(_SIMULATED_SEND_SECONDS)
    return "projects/test/messages/fake-id"


@pytest.fixture
def fcm_service() -> FCMNotificationService:
    """FCM service with a stubbed Firebase app (no real credentials)."""
    service = FCMNotificationService(MagicMock())
    service._get_firebase_app = MagicMock(return_value=object())  # type: ignore[method-assign]
    return service


@pytest.mark.unit
class TestFCMSendEventLoop:
    """FCM sends must not block the event loop."""

    async def test_send_to_token_does_not_block_event_loop(
        self, fcm_service: FCMNotificationService
    ) -> None:
        """A slow messaging.send must not stall concurrent coroutines."""
        with patch("firebase_admin.messaging.send", side_effect=_slow_send):
            max_stall, result = await measure_max_loop_stall(
                lambda: fcm_service._send_to_token(
                    token="tok-1234567890abcdef",
                    title="Title",
                    body="Body",
                )
            )

        assert result.success is True
        assert result.message_id == "projects/test/messages/fake-id"
        assert max_stall < _MAX_ALLOWED_STALL_SECONDS, (
            f"event loop stalled {max_stall * 1000:.0f} ms during messaging.send "
            f"(threshold {_MAX_ALLOWED_STALL_SECONDS * 1000:.0f} ms)"
        )

    async def test_send_multicast_does_not_block_event_loop(
        self, fcm_service: FCMNotificationService
    ) -> None:
        """A multi-token broadcast must not stall concurrent coroutines."""
        tokens = [f"tok-{i:04d}" for i in range(2)]

        with patch("firebase_admin.messaging.send", side_effect=_slow_send):
            max_stall, (sent, failed) = await measure_max_loop_stall(
                lambda: fcm_service.send_multicast(
                    tokens=tokens,
                    title="Title",
                    body="Body",
                )
            )

        assert sent == len(tokens)
        assert failed == 0
        assert max_stall < _MAX_ALLOWED_STALL_SECONDS, (
            f"event loop stalled {max_stall * 1000:.0f} ms during multicast "
            f"(threshold {_MAX_ALLOWED_STALL_SECONDS * 1000:.0f} ms)"
        )

    async def test_send_multicast_counts_failures(
        self, fcm_service: FCMNotificationService
    ) -> None:
        """Send errors are counted as failures, not raised."""

        def _failing_send(message: object) -> str:
            raise RuntimeError("boom")

        with patch("firebase_admin.messaging.send", side_effect=_failing_send):
            sent, failed = await fcm_service.send_multicast(
                tokens=["tok-a", "tok-b"],
                title="Title",
                body="Body",
            )

        assert sent == 0
        assert failed == 2
