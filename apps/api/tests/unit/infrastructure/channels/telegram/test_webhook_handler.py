"""Tests for Telegram webhook handler."""

from unittest.mock import patch

import pytest

from src.domains.channels.abstractions import (
    ChannelFile,
    ChannelFileKind,
    ChannelInboundMessage,
    ChannelLocation,
)
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
    async def test_no_secret_configured_rejects_everything(
        self, handler: TelegramWebhookHandler
    ) -> None:
        """SEC-024: no secret configured → refuse, never accept.

        This test asserted the opposite ("dev mode: accept everything"). The
        webhook route is mounted whenever CHANNELS_ENABLED is true — including
        in long-polling mode, where no secret exists — so that dev-mode
        exception was reachable on a public production URL, turning the
        endpoint into an unauthenticated entry point to the message router,
        the OTP flow and pending HITL interruptions.
        """
        with patch(
            "src.infrastructure.channels.telegram.webhook_handler.settings"
        ) as mock_settings:
            mock_settings.telegram_webhook_secret = None
            result = await handler.validate_signature(b"body", "anything")
            assert result is False

    @pytest.mark.asyncio
    async def test_no_secret_attr_rejects_everything(self, handler: TelegramWebhookHandler) -> None:
        """SEC-024: a settings object without the attribute is refused too.

        A missing attribute is a misconfiguration, not an authorisation.
        """
        with patch(
            "src.infrastructure.channels.telegram.webhook_handler.settings"
        ) as mock_settings:
            del mock_settings.telegram_webhook_secret
            result = await handler.validate_signature(b"body", "anything")
            assert result is False

    @pytest.mark.asyncio
    async def test_empty_secret_string_rejects_everything(
        self, handler: TelegramWebhookHandler
    ) -> None:
        """SEC-024: an empty secret is as good as none — refuse.

        Covers the `TELEGRAM_WEBHOOK_SECRET=` (declared but blank) case, which a
        truthiness check treats like an absent secret.
        """
        with patch(
            "src.infrastructure.channels.telegram.webhook_handler.settings"
        ) as mock_settings:
            mock_settings.telegram_webhook_secret = ""
            result = await handler.validate_signature(b"body", "")
            assert result is False


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
    async def test_video_message_unsupported(self, handler: TelegramWebhookHandler) -> None:
        """A video is no file LIA reads (lot 11 reads photos and documents) → None."""
        payload = {
            "message": {
                "message_id": 1,
                "chat": {"id": 123},
                "from": {"id": 123},
                "video": {"file_id": "video_id", "width": 100, "height": 100, "duration": 3},
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


# =============================================================================
# Shared locations and quoted replies (lot 8)
# =============================================================================


def _message(**fields: object) -> dict[str, object]:
    return {
        "update_id": 1,
        "message": {"message_id": 9, "chat": {"id": 123}, "from": {"id": 123}, **fields},
    }


class TestASharedLocationIsRead:
    """A pin reached nobody: LIA answered nothing to a shared location (lot 8)."""

    async def test_a_shared_position_is_the_person_s(self, handler: TelegramWebhookHandler) -> None:
        payload = _message(
            location={"latitude": 48.85661, "longitude": 2.35222, "horizontal_accuracy": 12.5}
        )

        parsed = await handler.parse_update(payload)

        assert parsed is not None and parsed.text is None
        assert parsed.location == ChannelLocation(48.85661, 2.35222, accuracy_m=12.5)
        assert parsed.location.is_place is False

    async def test_a_venue_is_a_place_not_the_person(self, handler: TelegramWebhookHandler) -> None:
        """A place's names are read on one line: a break would open markup in the app."""
        payload = _message(
            location={"latitude": 48.85837, "longitude": 2.29448},
            venue={
                "location": {"latitude": 48.85837, "longitude": 2.29448},
                "title": "Tour\n# Eiffel",
                "address": "Champ de Mars,\n  Paris",
            },
        )

        parsed = await handler.parse_update(payload)

        assert parsed is not None
        assert parsed.location == ChannelLocation(
            48.85837, 2.29448, title="Tour # Eiffel", address="Champ de Mars, Paris"
        )
        assert parsed.location.is_place is True

    async def test_a_venue_with_no_name_is_never_taken_for_the_person(
        self, handler: TelegramWebhookHandler
    ) -> None:
        """Its point is somewhere else: read as a position, « near me » would go there."""
        payload = _message(
            location={"latitude": 48.85837, "longitude": 2.29448},
            venue={"location": {"latitude": 48.85837, "longitude": 2.29448}, "title": "  "},
        )

        assert await handler.parse_update(payload) is None

    @pytest.mark.parametrize(
        "location",
        [
            {"latitude": 91.0, "longitude": 2.0},
            {"latitude": 48.0, "longitude": -181.0},
            {"latitude": "48.8", "longitude": 2.3},
            {"latitude": 48.8},
            {"latitude": True, "longitude": 2.3},
        ],
        ids=["lat_out_of_range", "lon_out_of_range", "text", "missing", "bool"],
    )
    async def test_a_position_that_is_none_is_ignored(
        self, handler: TelegramWebhookHandler, location: dict[str, object]
    ) -> None:
        assert await handler.parse_update(_message(location=location)) is None


class TestAQuotedReplyIsRead:
    """Replying to an earlier message said which one: LIA read the words alone."""

    async def test_the_selected_part_wins(self, handler: TelegramWebhookHandler) -> None:
        payload = _message(
            text="and this one?",
            reply_to_message={"message_id": 4, "text": "1. Paris\n2. Lyon\n3. Nice"},
            quote={"text": "2. Lyon", "position": 9},
        )

        parsed = await handler.parse_update(payload)

        assert parsed is not None and parsed.quoted_text == "2. Lyon"

    async def test_a_whole_message_is_quoted_by_its_text_or_caption(
        self, handler: TelegramWebhookHandler
    ) -> None:
        texted = await handler.parse_update(
            _message(text="why?", reply_to_message={"message_id": 4, "text": "No."})
        )
        captioned = await handler.parse_update(
            _message(text="where?", reply_to_message={"message_id": 5, "caption": "The view"})
        )

        assert texted is not None and texted.quoted_text == "No."
        assert captioned is not None and captioned.quoted_text == "The view"

    async def test_a_reply_to_something_wordless_quotes_nothing(
        self, handler: TelegramWebhookHandler
    ) -> None:
        parsed = await handler.parse_update(
            _message(text="nice", reply_to_message={"message_id": 4, "sticker": {}})
        )

        assert parsed is not None and parsed.quoted_text is None


class TestAFileIsRead:
    """A photo or a document reached nobody: LIA answered nothing (lot 11)."""

    async def test_a_photo_is_read_at_its_largest_size_with_its_caption(
        self, handler: TelegramWebhookHandler
    ) -> None:
        payload = _message(
            photo=[
                {"file_id": "small", "file_unique_id": "u", "width": 90, "height": 60},
                {
                    "file_id": "large",
                    "file_unique_id": "u",
                    "width": 1280,
                    "height": 853,
                    "file_size": 120_000,
                },
                {"file_id": "medium", "file_unique_id": "u", "width": 320, "height": 213},
            ],
            caption="what is this?",
        )

        parsed = await handler.parse_update(payload)

        assert parsed is not None and parsed.text == "what is this?"
        assert parsed.files == (
            ChannelFile("large", ChannelFileKind.PHOTO, "photo.jpg", "image/jpeg", 120_000),
        )

    async def test_a_document_keeps_its_name_type_and_size(
        self, handler: TelegramWebhookHandler
    ) -> None:
        payload = _message(
            document={
                "file_id": "doc",
                "file_unique_id": "d",
                "file_name": "report.pdf",
                "mime_type": "application/pdf",
                "file_size": 52_000,
            }
        )

        parsed = await handler.parse_update(payload)

        assert parsed is not None and parsed.text is None
        assert parsed.files == (
            ChannelFile("doc", ChannelFileKind.DOCUMENT, "report.pdf", "application/pdf", 52_000),
        )

    async def test_a_document_with_nothing_declared_is_still_read(
        self, handler: TelegramWebhookHandler
    ) -> None:
        parsed = await handler.parse_update(_message(document={"file_id": "doc"}))

        assert parsed is not None
        assert parsed.files == (ChannelFile("doc", ChannelFileKind.DOCUMENT, None, None, None),)

    async def test_an_album_s_part_names_its_album(self, handler: TelegramWebhookHandler) -> None:
        payload = _message(
            photo=[{"file_id": "p1", "width": 10, "height": 10}], media_group_id="album-7"
        )

        parsed = await handler.parse_update(payload)

        assert parsed is not None and parsed.album_id == "album-7"

    @pytest.mark.parametrize(
        "fields",
        [
            {"photo": []},
            {"photo": [{"width": 10, "height": 10}]},
            {"document": {"file_name": "x.pdf"}},
            {"document": {"file_id": ""}},
        ],
        ids=["no_size", "photo_without_id", "document_without_id", "empty_id"],
    )
    async def test_a_file_with_no_id_is_ignored(
        self, handler: TelegramWebhookHandler, fields: dict[str, object]
    ) -> None:
        assert await handler.parse_update(_message(**fields)) is None
