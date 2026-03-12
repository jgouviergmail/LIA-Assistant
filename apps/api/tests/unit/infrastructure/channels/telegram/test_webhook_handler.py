"""Tests for Telegram webhook handler."""

from unittest.mock import patch

import pytest

from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.models import ChannelType
from src.infrastructure.channels.telegram.webhook_handler import TelegramWebhookHandler


@pytest.fixture
def handler() -> TelegramWebhookHandler:
    return TelegramWebhookHandler()


# =============================================================================
# validate_signature
# =============================================================================


class TestValidateSignature:
    """Tests for webhook signature validation."""

    @pytest.mark.asyncio
    async def test_valid_signature(self, handler: TelegramWebhookHandler) -> None:
        with patch(
            "src.infrastructure.channels.telegram.webhook_handler.settings"
        ) as mock_settings:
            mock_settings.telegram_webhook_secret = "my-secret"
            result = await handler.validate_signature(b"body", "my-secret")
            assert result is True

    @pytest.mark.asyncio
    async def test_invalid_signature(self, handler: TelegramWebhookHandler) -> None:
        with patch(
            "src.infrastructure.channels.telegram.webhook_handler.settings"
        ) as mock_settings:
            mock_settings.telegram_webhook_secret = "my-secret"
            result = await handler.validate_signature(b"body", "wrong-secret")
            assert result is False

    @pytest.mark.asyncio
    async def test_empty_signature_rejected(self, handler: TelegramWebhookHandler) -> None:
        with patch(
            "src.infrastructure.channels.telegram.webhook_handler.settings"
        ) as mock_settings:
            mock_settings.telegram_webhook_secret = "my-secret"
            result = await handler.validate_signature(b"body", "")
            assert result is False

    @pytest.mark.asyncio
    async def test_no_secret_configured_accepts_all(self, handler: TelegramWebhookHandler) -> None:
        """Dev mode: no secret configured → accept everything."""
        with patch(
            "src.infrastructure.channels.telegram.webhook_handler.settings"
        ) as mock_settings:
            mock_settings.telegram_webhook_secret = None
            result = await handler.validate_signature(b"body", "anything")
            assert result is True

    @pytest.mark.asyncio
    async def test_no_secret_attr_accepts_all(self, handler: TelegramWebhookHandler) -> None:
        """Settings missing the attribute entirely → accept (dev mode)."""
        with patch(
            "src.infrastructure.channels.telegram.webhook_handler.settings"
        ) as mock_settings:
            del mock_settings.telegram_webhook_secret
            result = await handler.validate_signature(b"body", "anything")
            assert result is True


# =============================================================================
# parse_update — text messages
# =============================================================================


class TestParseUpdateTextMessage:
    """Tests for parsing text message updates."""

    @pytest.mark.asyncio
    async def test_basic_text_message(self, handler: TelegramWebhookHandler) -> None:
        payload = {
            "message": {
                "message_id": 42,
                "chat": {"id": 123456, "type": "private"},
                "from": {"id": 123456, "username": "testuser"},
                "text": "Hello bot",
            }
        }
        result = await handler.parse_update(payload)

        assert result is not None
        assert isinstance(result, ChannelInboundMessage)
        assert result.channel_type == ChannelType.TELEGRAM
        assert result.channel_user_id == "123456"
        assert result.text == "Hello bot"
        assert result.message_id == "42"
        assert result.voice_file_id is None
        assert result.callback_data is None
        assert result.raw_data == payload

    @pytest.mark.asyncio
    async def test_start_command_with_otp(self, handler: TelegramWebhookHandler) -> None:
        """Should parse /start {code} as a regular text message."""
        payload = {
            "message": {
                "message_id": 1,
                "chat": {"id": 999, "type": "private"},
                "from": {"id": 999},
                "text": "/start 123456",
            }
        }
        result = await handler.parse_update(payload)

        assert result is not None
        assert result.text == "/start 123456"
        assert result.channel_user_id == "999"

    @pytest.mark.asyncio
    async def test_message_without_username(self, handler: TelegramWebhookHandler) -> None:
        """Private accounts may not have a username."""
        payload = {
            "message": {
                "message_id": 10,
                "chat": {"id": 555},
                "from": {"id": 555},
                "text": "Hi",
            }
        }
        result = await handler.parse_update(payload)

        assert result is not None
        assert result.text == "Hi"


# =============================================================================
# parse_update — voice messages
# =============================================================================


class TestParseUpdateVoiceMessage:
    """Tests for parsing voice message updates."""

    @pytest.mark.asyncio
    async def test_voice_message(self, handler: TelegramWebhookHandler) -> None:
        payload = {
            "message": {
                "message_id": 7,
                "chat": {"id": 444, "type": "private"},
                "from": {"id": 444},
                "voice": {
                    "file_id": "AwACAgIAAx0CX_abc123",
                    "duration": 5,
                    "mime_type": "audio/ogg",
                    "file_size": 12345,
                },
            }
        }
        result = await handler.parse_update(payload)

        assert result is not None
        assert result.voice_file_id == "AwACAgIAAx0CX_abc123"
        assert result.voice_duration_seconds == 5
        assert result.text is None
        assert result.channel_user_id == "444"

    @pytest.mark.asyncio
    async def test_voice_takes_precedence_over_text(self, handler: TelegramWebhookHandler) -> None:
        """If both voice and text are present (caption), voice wins."""
        payload = {
            "message": {
                "message_id": 8,
                "chat": {"id": 444},
                "from": {"id": 444},
                "voice": {"file_id": "voice_id", "duration": 3},
                "text": "some caption",
            }
        }
        result = await handler.parse_update(payload)

        assert result is not None
        assert result.voice_file_id == "voice_id"
        # Voice message parsing does not capture text
        assert result.text is None


# =============================================================================
# parse_update — callback queries
# =============================================================================


class TestParseUpdateCallbackQuery:
    """Tests for parsing callback query (inline keyboard) updates."""

    @pytest.mark.asyncio
    async def test_callback_query(self, handler: TelegramWebhookHandler) -> None:
        payload = {
            "callback_query": {
                "id": "cb_123",
                "from": {"id": 777},
                "message": {
                    "message_id": 99,
                    "chat": {"id": 777, "type": "private"},
                },
                "data": "hitl:approve:conv-id-abc",
            }
        }
        result = await handler.parse_update(payload)

        assert result is not None
        assert result.callback_data == "hitl:approve:conv-id-abc"
        assert result.channel_user_id == "777"
        assert result.message_id == "99"
        assert result.text is None
        assert result.voice_file_id is None

    @pytest.mark.asyncio
    async def test_callback_query_no_chat_id(self, handler: TelegramWebhookHandler) -> None:
        """Callback without chat_id → None."""
        payload = {
            "callback_query": {
                "id": "cb_456",
                "from": {"id": 888},
                "message": {},
                "data": "some_data",
            }
        }
        result = await handler.parse_update(payload)

        assert result is None

    @pytest.mark.asyncio
    async def test_callback_query_takes_precedence(self, handler: TelegramWebhookHandler) -> None:
        """If both callback_query and message exist, callback_query wins."""
        payload = {
            "callback_query": {
                "id": "cb_789",
                "from": {"id": 111},
                "message": {
                    "message_id": 50,
                    "chat": {"id": 111, "type": "private"},
                },
                "data": "hitl:reject:xyz",
            },
            "message": {
                "message_id": 51,
                "chat": {"id": 111},
                "text": "ignore this",
            },
        }
        result = await handler.parse_update(payload)

        assert result is not None
        assert result.callback_data == "hitl:reject:xyz"
        assert result.text is None


# =============================================================================
# parse_update — ignored / unsupported
# =============================================================================


class TestParseUpdateIgnored:
    """Tests for update types that should be ignored."""

    @pytest.mark.asyncio
    async def test_edited_message_ignored(self, handler: TelegramWebhookHandler) -> None:
        payload = {
            "edited_message": {
                "message_id": 1,
                "chat": {"id": 123},
                "text": "edited text",
            }
        }
        result = await handler.parse_update(payload)
        assert result is None

    @pytest.mark.asyncio
    async def test_channel_post_ignored(self, handler: TelegramWebhookHandler) -> None:
        payload = {
            "channel_post": {
                "message_id": 1,
                "chat": {"id": -100123, "type": "channel"},
                "text": "channel post",
            }
        }
        result = await handler.parse_update(payload)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_payload(self, handler: TelegramWebhookHandler) -> None:
        result = await handler.parse_update({})
        assert result is None

    @pytest.mark.asyncio
    async def test_message_without_chat_id(self, handler: TelegramWebhookHandler) -> None:
        """Message missing chat.id → None."""
        payload = {
            "message": {
                "message_id": 1,
                "chat": {},
                "text": "test",
            }
        }
        result = await handler.parse_update(payload)
        assert result is None

    @pytest.mark.asyncio
    async def test_photo_message_unsupported(self, handler: TelegramWebhookHandler) -> None:
        """Photo messages are not supported → None."""
        payload = {
            "message": {
                "message_id": 1,
                "chat": {"id": 123},
                "from": {"id": 123},
                "photo": [{"file_id": "photo_id", "width": 100, "height": 100}],
            }
        }
        result = await handler.parse_update(payload)
        assert result is None

    @pytest.mark.asyncio
    async def test_sticker_message_unsupported(self, handler: TelegramWebhookHandler) -> None:
        payload = {
            "message": {
                "message_id": 1,
                "chat": {"id": 123},
                "from": {"id": 123},
                "sticker": {"file_id": "sticker_id"},
            }
        }
        result = await handler.parse_update(payload)
        assert result is None
