"""
Generic channel abstractions for multi-channel messaging.

These abstract base classes define the interface that each channel
implementation (Telegram, Discord, WhatsApp, etc.) must fulfill.
Telegram is the first concrete implementation.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.domains.channels.models import ChannelType


@dataclass
class ChannelInboundMessage:
    """
    Normalized inbound message from any channel.

    Channel-specific webhook handlers parse raw platform data
    into this generic format for the message router.
    """

    channel_type: ChannelType
    channel_user_id: str  # Provider-specific (e.g., Telegram chat_id)
    text: str | None = None
    voice_file_id: str | None = None
    voice_duration_seconds: int | None = None
    callback_data: str | None = None  # HITL button press (inline keyboard)
    message_id: str | None = None  # Provider-specific message ID
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelOutboundMessage:
    """
    Normalized outbound message to any channel.

    Services create these generic messages; channel-specific senders
    handle the actual delivery with platform-specific formatting.
    """

    text: str
    parse_mode: str = "HTML"
    reply_markup: dict | None = None  # Inline keyboard (HITL buttons)


class BaseChannelSender(ABC):
    """
    Abstract sender for delivering messages to a channel.

    Each channel implementation (Telegram, Discord, etc.) provides
    a concrete sender that handles platform-specific API calls,
    formatting, and error handling.
    """

    @abstractmethod
    async def send_message(
        self,
        channel_user_id: str,
        message: ChannelOutboundMessage,
    ) -> str | None:
        """
        Send a message to a channel user.

        Args:
            channel_user_id: Provider-specific user identifier.
            message: Outbound message to send.

        Returns:
            Provider-specific message ID if available, None otherwise.
        """

    @abstractmethod
    async def send_typing_indicator(self, channel_user_id: str) -> None:
        """
        Send a typing indicator to show the bot is processing.

        Args:
            channel_user_id: Provider-specific user identifier.
        """

    @abstractmethod
    async def send_notification(
        self,
        channel_user_id: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """
        Send a proactive notification to a channel user.

        Args:
            channel_user_id: Provider-specific user identifier.
            title: Notification title.
            body: Notification body.
            data: Optional metadata.

        Returns:
            True if sent successfully, False otherwise.
        """

    @abstractmethod
    async def edit_message(
        self,
        channel_user_id: str,
        message_id: str,
        new_text: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """
        Edit an existing message (e.g., remove HITL buttons after decision).

        Args:
            channel_user_id: Provider-specific user identifier.
            message_id: Provider-specific message ID to edit.
            new_text: New message text.
            parse_mode: Text formatting mode.

        Returns:
            True if edited successfully, False otherwise.
        """


class BaseChannelWebhookHandler(ABC):
    """
    Abstract webhook handler for validating and parsing inbound updates.

    Each channel implementation provides a concrete handler that
    validates the webhook signature and parses platform-specific
    payloads into the generic ChannelInboundMessage format.
    """

    @abstractmethod
    async def validate_signature(self, body: bytes, signature: str) -> bool:
        """
        Validate the webhook signature/secret token.

        Args:
            body: Raw request body bytes.
            signature: Signature or secret token from request header.

        Returns:
            True if the signature is valid.
        """

    @abstractmethod
    async def parse_update(self, payload: dict) -> ChannelInboundMessage | None:
        """
        Parse a raw webhook payload into a ChannelInboundMessage.

        Returns None if the update type is not supported or should be ignored
        (e.g., channel posts, edited messages, etc.).

        Args:
            payload: Parsed JSON payload from the webhook.

        Returns:
            ChannelInboundMessage or None if the update should be skipped.
        """
