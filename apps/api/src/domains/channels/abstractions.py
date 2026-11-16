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
from enum import StrEnum
from typing import Any

from src.domains.channels.models import ChannelType


@dataclass(frozen=True, slots=True)
class ChannelLocation:
    """A point shared on a channel: the person's position, or a place they name.

    A place (a venue, Telegram's « location » picker naming a spot) is never
    the person's position: only a plain position is the turn's geolocation.

    Attributes:
        latitude: Degrees, -90 to 90.
        longitude: Degrees, -180 to 180.
        accuracy_m: The position's radius of uncertainty in metres, when the
            client measured one.
        title: The place's name; None for the person's position.
        address: The place's address, when the client gave one.
    """

    latitude: float
    longitude: float
    accuracy_m: float | None = None
    title: str | None = None
    address: str | None = None

    @property
    def is_place(self) -> bool:
        """Whether the point names a place rather than where the person is."""
        return self.title is not None


class ChannelFileKind(StrEnum):
    """What a channel sent a file as (Telegram lot 11)."""

    PHOTO = "photo"  # A picture the client compressed; always JPEG.
    DOCUMENT = "document"  # A file sent as itself, any type.


@dataclass(frozen=True, slots=True)
class ChannelFile:
    """A file a person sent on a channel, as the channel describes it.

    What the file IS is decided from its bytes when it is stored, never from
    what is declared here (``AttachmentService.upload``).

    Attributes:
        file_id: The channel's handle to download it.
        kind: Sent as a photo or as a document.
        filename: Its name, when the channel gives one.
        mime_type: The type the sender's client declared, when it did.
        size_bytes: Its size as declared, when it was.
    """

    file_id: str
    kind: ChannelFileKind
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None


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
    press_id: str | None = None  # Provider-specific ID of a button press, to answer it
    location: ChannelLocation | None = None  # A shared point (position or place)
    quoted_text: str | None = None  # The words of the message this one replies to
    files: tuple[ChannelFile, ...] = ()  # Photos and documents sent with it (lot 11)
    album_id: str | None = None  # The album the message is one part of (Telegram media group)
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
    async def send_file(
        self, channel_user_id: str, content: bytes, *, filename: str, mime_type: str
    ) -> bool:
        """
        Send a file the person can open: a picture drawn as one, anything else as a document.

        Args:
            channel_user_id: Provider-specific user identifier.
            content: The file's bytes.
            filename: The name it is shown and saved under.
            mime_type: What the file is.

        Returns:
            True if sent, False when the provider refused it.
        """

    @abstractmethod
    async def send_voice(self, channel_user_id: str, audio: bytes) -> bool:
        """
        Send an answer heard, as a voice message.

        Args:
            channel_user_id: Provider-specific user identifier.
            audio: The MP3 bytes.

        Returns:
            True if sent, False when the provider refused it.
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
        *,
        language: str | None = None,
    ) -> bool:
        """
        Send a proactive notification to a channel user.

        Args:
            channel_user_id: Provider-specific user identifier.
            title: Notification title.
            body: Notification body as the chat shows it (Markdown, an answer
                with its cards, an HTML document): each channel draws it.
            data: Optional metadata.
            language: The reader's language (default: the declared language).

        Returns:
            True if sent successfully, False otherwise.
        """

    @abstractmethod
    async def acknowledge(self, channel_user_id: str, message_id: str) -> bool:
        """
        Mark the person's message as received, without a message of its own.

        Args:
            channel_user_id: Provider-specific user identifier.
            message_id: Provider-specific ID of the person's message.

        Returns:
            True when the mark is on the message, False when the provider refused.
        """

    @abstractmethod
    async def remove_keyboard(self, channel_user_id: str, message_id: str) -> bool:
        """
        Take the buttons off a message, its text kept (a HITL question answered).

        Args:
            channel_user_id: Provider-specific user identifier.
            message_id: Provider-specific ID of the message carrying the buttons.

        Returns:
            True if the buttons are off, False when the provider refused.
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
