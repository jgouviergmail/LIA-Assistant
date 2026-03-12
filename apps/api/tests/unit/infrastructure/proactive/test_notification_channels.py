"""Tests for notification channel dispatch (module-level functions + dispatcher integration)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.proactive.notification import (
    NotificationDispatcher,
    NotificationResult,
    send_notification_to_channels,
)

# Path for the lazy import inside send_notification_to_channels()
_REPO_PATCH = "src.domains.channels.repository.UserChannelBindingRepository"
_SEND_PATCH = "src.infrastructure.proactive.notification._send_to_channel"

# =============================================================================
# NotificationResult
# =============================================================================


class TestNotificationResult:
    """Tests for the NotificationResult dataclass."""

    def test_channel_sent_default_zero(self) -> None:
        result = NotificationResult(success=True)
        assert result.channel_sent == 0

    def test_failure_has_zero_channel_sent(self) -> None:
        result = NotificationResult.failure("test error")
        assert result.channel_sent == 0


# =============================================================================
# NotificationDispatcher.__init__
# =============================================================================


class TestNotificationDispatcherInit:
    """Tests for channel_enabled initialization."""

    def test_channel_enabled_explicit_true(self) -> None:
        dispatcher = NotificationDispatcher(channel_enabled=True)
        assert dispatcher.channel_enabled is True

    def test_channel_enabled_explicit_false(self) -> None:
        dispatcher = NotificationDispatcher(channel_enabled=False)
        assert dispatcher.channel_enabled is False

    @patch("src.infrastructure.proactive.notification.settings")
    def test_channel_enabled_auto_detect_true(self, mock_settings: MagicMock) -> None:
        mock_settings.channels_enabled = True
        dispatcher = NotificationDispatcher()
        assert dispatcher.channel_enabled is True

    @patch("src.infrastructure.proactive.notification.settings")
    def test_channel_enabled_auto_detect_missing(self, mock_settings: MagicMock) -> None:
        """If settings.channels_enabled doesn't exist, defaults to False."""
        del mock_settings.channels_enabled
        dispatcher = NotificationDispatcher()
        assert dispatcher.channel_enabled is False


# =============================================================================
# Helper
# =============================================================================


def _make_binding(channel_type: str = "telegram", channel_user_id: str = "12345678") -> MagicMock:
    """Create a mock UserChannelBinding."""
    binding = MagicMock()
    binding.channel_type = channel_type
    binding.channel_user_id = channel_user_id
    return binding


# =============================================================================
# send_notification_to_channels (module-level function)
# =============================================================================


class TestSendChannels:
    """Tests for the send_notification_to_channels function."""

    @pytest.mark.asyncio
    async def test_sends_to_active_bindings(self) -> None:
        """Should send notification to each active binding."""
        binding = _make_binding()
        db = AsyncMock()

        with (
            patch(_SEND_PATCH, new_callable=AsyncMock) as mock_send,
            patch(_REPO_PATCH) as mock_repo_cls,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_active_for_user = AsyncMock(return_value=[binding])
            mock_send.return_value = True

            result = await send_notification_to_channels(
                user_id=uuid4(),
                title="Test Title",
                body="Test body",
                task_type="interest",
                target_id="target-123",
                db=db,
            )

        assert result == 1
        mock_send.assert_called_once_with(
            channel_type="telegram",
            channel_user_id="12345678",
            title="Test Title",
            body="Test body",
            task_type="interest",
            target_id="target-123",
        )

    @pytest.mark.asyncio
    async def test_no_bindings_returns_zero(self) -> None:
        """No active bindings should return 0."""
        db = AsyncMock()

        with patch(_REPO_PATCH) as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_active_for_user = AsyncMock(return_value=[])

            result = await send_notification_to_channels(
                user_id=uuid4(),
                title="Test",
                body="Body",
                task_type="interest",
                target_id="target",
                db=db,
            )

        assert result == 0

    @pytest.mark.asyncio
    async def test_partial_failure(self) -> None:
        """Should count only successful sends."""
        bindings = [_make_binding(channel_user_id="111"), _make_binding(channel_user_id="222")]
        db = AsyncMock()

        with (
            patch(_SEND_PATCH, new_callable=AsyncMock, side_effect=[True, False]),
            patch(_REPO_PATCH) as mock_repo_cls,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_active_for_user = AsyncMock(return_value=bindings)

            result = await send_notification_to_channels(
                user_id=uuid4(),
                title="Test",
                body="Body",
                task_type="birthday",
                target_id="target",
                db=db,
            )

        assert result == 1

    @pytest.mark.asyncio
    async def test_exception_in_send_continues(self) -> None:
        """Exception in one binding should not prevent others."""
        bindings = [_make_binding(channel_user_id="111"), _make_binding(channel_user_id="222")]
        db = AsyncMock()

        with (
            patch(
                _SEND_PATCH,
                new_callable=AsyncMock,
                side_effect=[RuntimeError("Network error"), True],
            ),
            patch(_REPO_PATCH) as mock_repo_cls,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_active_for_user = AsyncMock(return_value=bindings)

            result = await send_notification_to_channels(
                user_id=uuid4(),
                title="Test",
                body="Body",
                task_type="event",
                target_id="target",
                db=db,
            )

        assert result == 1


# =============================================================================
# _send_to_channel (module-level routing)
# =============================================================================


class TestSendToChannel:
    """Tests for _send_to_channel routing."""

    @pytest.mark.asyncio
    async def test_telegram_channel_delegates(self) -> None:
        """send_notification_to_channels should delegate to _send_to_channel."""
        binding = _make_binding(channel_type="telegram", channel_user_id="99999")
        db = AsyncMock()

        with (
            patch(_SEND_PATCH, new_callable=AsyncMock) as mock_send,
            patch(_REPO_PATCH) as mock_repo_cls,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_active_for_user = AsyncMock(return_value=[binding])
            mock_send.return_value = True

            result = await send_notification_to_channels(
                user_id=uuid4(),
                title="Title",
                body="Body",
                task_type="interest",
                target_id="target-1",
                db=db,
            )

        assert result == 1
        mock_send.assert_called_once_with(
            channel_type="telegram",
            channel_user_id="99999",
            title="Title",
            body="Body",
            task_type="interest",
            target_id="target-1",
        )

    @pytest.mark.asyncio
    async def test_unsupported_channel_returns_false(self) -> None:
        """Unsupported channel types should return False."""
        from src.infrastructure.proactive.notification import _send_to_channel

        result = await _send_to_channel(
            channel_type="discord",
            channel_user_id="12345",
            title="Title",
            body="Body",
            task_type="interest",
            target_id="target-1",
        )

        assert result is False
