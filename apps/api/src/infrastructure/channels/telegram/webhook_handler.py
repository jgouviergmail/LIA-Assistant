"""
Telegram webhook handler for signature validation and Update parsing.

Converts raw Telegram webhook payloads into the generic
ChannelInboundMessage format for the channel message router.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import hmac

from src.core.config import settings
from src.domains.channels.abstractions import BaseChannelWebhookHandler, ChannelInboundMessage
from src.domains.channels.models import ChannelType
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class TelegramWebhookHandler(BaseChannelWebhookHandler):
    """
    Validates Telegram webhook signatures and parses Updates
    into ChannelInboundMessage instances.
    """

    async def validate_signature(self, body: bytes, signature: str) -> bool:
        """
        Validate the X-Telegram-Bot-Api-Secret-Token header.

        Telegram sends the secret_token configured via set_webhook()
        as a plain string header (not HMAC). We use constant-time
        comparison to prevent timing attacks.

        Args:
            body: Raw request body (unused for Telegram, kept for interface).
            signature: Value of X-Telegram-Bot-Api-Secret-Token header.

        Returns:
            True if the signature matches the configured secret.
        """
        expected = getattr(settings, "telegram_webhook_secret", None)
        if not expected:
            # No secret configured — accept all (dev mode)
            logger.warning("telegram_webhook_no_secret_configured")
            return True

        if not signature:
            return False

        return hmac.compare_digest(signature, expected)

    async def parse_update(self, payload: dict) -> ChannelInboundMessage | None:
        """
        Parse a Telegram Update payload into a ChannelInboundMessage.

        Handles:
        - Regular text messages
        - Voice messages (audio notes)
        - Callback queries (inline keyboard button presses)

        Ignores:
        - Edited messages
        - Channel posts
        - Other update types

        Args:
            payload: Parsed JSON from the Telegram webhook.

        Returns:
            ChannelInboundMessage or None if the update should be skipped.
        """
        # Handle callback_query (HITL button press)
        callback_query = payload.get("callback_query")
        if callback_query:
            return self._parse_callback_query(callback_query)

        # Handle regular message
        message = payload.get("message")
        if not message:
            logger.debug("telegram_webhook_ignored_update_type", keys=list(payload.keys()))
            return None

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            logger.warning("telegram_webhook_missing_chat_id")
            return None

        # Voice message
        voice = message.get("voice")
        if voice:
            return ChannelInboundMessage(
                channel_type=ChannelType.TELEGRAM,
                channel_user_id=chat_id,
                voice_file_id=voice.get("file_id"),
                voice_duration_seconds=voice.get("duration"),
                message_id=str(message.get("message_id", "")),
                raw_data=payload,
            )

        # Text message
        text = message.get("text")
        if text:
            return ChannelInboundMessage(
                channel_type=ChannelType.TELEGRAM,
                channel_user_id=chat_id,
                text=text,
                message_id=str(message.get("message_id", "")),
                raw_data=payload,
            )

        # Unsupported message type (photo, document, sticker, etc.)
        logger.debug(
            "telegram_webhook_unsupported_message_type",
            chat_id=chat_id,
            message_keys=list(message.keys()),
        )
        return None

    def _parse_callback_query(self, callback_query: dict) -> ChannelInboundMessage | None:
        """Parse a callback_query (inline keyboard button press)."""
        message = callback_query.get("message", {})
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        if not chat_id:
            return None

        return ChannelInboundMessage(
            channel_type=ChannelType.TELEGRAM,
            channel_user_id=chat_id,
            callback_data=callback_query.get("data"),
            message_id=str(message.get("message_id", "")),
            raw_data={"callback_query": callback_query},
        )
