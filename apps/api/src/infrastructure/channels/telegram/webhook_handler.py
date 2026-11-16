"""
Telegram webhook handler for signature validation and Update parsing.

Converts raw Telegram webhook payloads into the generic
ChannelInboundMessage format for the channel message router.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import hmac
import math
from typing import Any

from src.core.config import settings
from src.core.i18n import language_from_header
from src.domains.channels.abstractions import (
    BaseChannelWebhookHandler,
    ChannelFile,
    ChannelFileKind,
    ChannelInboundMessage,
    ChannelLocation,
)
from src.domains.channels.models import ChannelType
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: The widest radius of uncertainty Telegram reports for a position, in metres.
_ACCURACY_MAX_M = 1500
#: What Telegram makes of a photo: a JPEG, which carries no name.
_PHOTO_NAME = "photo.jpg"
_PHOTO_TYPE = "image/jpeg"


def client_language_of(raw_data: dict[str, Any]) -> str | None:
    """The language a Telegram client declares for its user, when LIA speaks it.

    An update may carry ``from.language_code`` (Telegram marks it optional) —
    the client's interface language, the channel's own Accept-Language, read
    by the same reader: canonicalised, and kept only when this instance speaks
    it. It speaks for a person the bot does not know yet; a known person's
    stored language is passed explicitly and always wins (ADR-323).

    Args:
        raw_data: The update as ``parse_update`` keeps it (the whole payload for
            a message, ``{"callback_query": …}`` for a button press).

    Returns:
        The canonical code, or None when the client declares none LIA speaks.
    """
    for key in ("message", "callback_query"):
        entry = raw_data.get(key)
        sender = entry.get("from") if isinstance(entry, dict) else None
        code = sender.get("language_code") if isinstance(sender, dict) else None
        if isinstance(code, str) and code:
            return language_from_header(code)
    return None


def _number_within(value: object, limit: float) -> float | None:
    """A number as Telegram sends it, or None when it is none within ±``limit``."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and -limit <= number <= limit else None


def _point(raw: object) -> tuple[float, float] | None:
    """The (latitude, longitude) of a Telegram ``Location``, or None when it is no point."""
    if not isinstance(raw, dict):
        return None
    latitude = _number_within(raw.get("latitude"), 90)
    longitude = _number_within(raw.get("longitude"), 180)
    if latitude is None or longitude is None:
        return None
    return latitude, longitude


def _text_field(raw: dict[str, Any], key: str) -> str | None:
    """A text field's words, or None when it holds none."""
    value = raw.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _one_line(raw: dict[str, Any], key: str) -> str | None:
    """A name's words on one line: a line break in it would open markup in the app."""
    words = _text_field(raw, key)
    return " ".join(words.split()) if words is not None else None


def _location_of(message: dict[str, Any]) -> ChannelLocation | None:
    """The point a message shares: a place for a venue, else the person's position.

    Telegram sets ``location`` beside ``venue`` (backward compatibility): a
    venue is read first, and is never taken for where the person is.

    Args:
        message: The Telegram ``Message``.

    Returns:
        The shared point, or None when the message shares none that is valid.
    """
    venue = message.get("venue")
    if isinstance(venue, dict):
        point = _point(venue.get("location") or message.get("location"))
        title = _one_line(venue, "title")
        if point is None or title is None:
            return None
        return ChannelLocation(*point, title=title, address=_one_line(venue, "address"))
    raw = message.get("location")
    point = _point(raw)
    if point is None or not isinstance(raw, dict):
        return None
    accuracy = _number_within(raw.get("horizontal_accuracy"), _ACCURACY_MAX_M)
    return ChannelLocation(
        *point, accuracy_m=accuracy if accuracy is not None and accuracy >= 0 else None
    )


def _declared_size(raw: dict[str, Any]) -> int | None:
    size = raw.get("file_size")
    return size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None


def _files_of(message: dict[str, Any]) -> tuple[ChannelFile, ...]:
    """The photo or the document a message carries (lot 11).

    A photo comes in several sizes: the largest is read. A file with no
    handle is no file.

    Args:
        message: The Telegram ``Message``.

    Returns:
        The file, or nothing.
    """
    sizes = message.get("photo")
    if isinstance(sizes, list):
        usable = [size for size in sizes if isinstance(size, dict) and _text_field(size, "file_id")]
        if not usable:
            return ()
        largest = max(usable, key=_area)
        return (
            ChannelFile(
                largest["file_id"].strip(),
                ChannelFileKind.PHOTO,
                _PHOTO_NAME,
                _PHOTO_TYPE,
                _declared_size(largest),
            ),
        )
    document = message.get("document")
    if not isinstance(document, dict) or (file_id := _text_field(document, "file_id")) is None:
        return ()
    return (
        ChannelFile(
            file_id,
            ChannelFileKind.DOCUMENT,
            _one_line(document, "file_name"),
            _text_field(document, "mime_type"),
            _declared_size(document),
        ),
    )


def _area(size: dict[str, Any]) -> int:
    """A photo size's pixels, for choosing the largest (0 when undeclared)."""
    width, height = size.get("width"), size.get("height")
    if isinstance(width, int) and isinstance(height, int):
        return width * height
    return 0


def _quoted_text_of(message: dict[str, Any]) -> str | None:
    """The words of the message this one replies to: the part selected, else its text.

    Args:
        message: The Telegram ``Message``.

    Returns:
        The quoted words, or None when the message replies to nothing with words.
    """
    quote = message.get("quote")
    if isinstance(quote, dict) and (selected := _text_field(quote, "text")):
        return selected
    replied = message.get("reply_to_message")
    if not isinstance(replied, dict):
        return None
    return _text_field(replied, "text") or _text_field(replied, "caption")


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

        SEC-024 — fail closed when no secret is configured. This used to return
        ``True``, "accept all (dev mode)", which made the endpoint an
        unauthenticated entry point into the message router, the OTP flow and
        pending HITL interruptions. The dev-mode rationale did not hold: the
        route is mounted whenever ``CHANNELS_ENABLED`` is true — including in
        long-polling mode, where no secret is expected at all — so the "dev"
        exception was reachable in production the moment a secret went missing.

        Refusing costs nothing legitimate: in webhook mode the secret is
        mandatory (validated at startup), and in polling mode Telegram never
        calls this endpoint, so the only callers left are unsolicited.

        Args:
            body: Raw request body (unused for Telegram, kept for interface).
            signature: Value of X-Telegram-Bot-Api-Secret-Token header.

        Returns:
            True only if a secret is configured AND the header matches it.
        """
        expected = getattr(settings, "telegram_webhook_secret", None)
        if not expected:
            logger.error(
                "telegram_webhook_rejected_no_secret",
                reason="no TELEGRAM_WEBHOOK_SECRET configured — request refused",
            )
            return False

        if not signature:
            return False

        return hmac.compare_digest(signature, expected)

    async def parse_update(self, payload: dict) -> ChannelInboundMessage | None:
        """
        Parse a Telegram Update payload into a ChannelInboundMessage.

        Handles:
        - Regular text messages
        - Voice messages (audio notes)
        - Shared locations: the person's position, or a place (a venue)
        - Photos and documents, their caption as their words (one album part each)
        - Callback queries (inline keyboard button presses)

        A reply carries the words of the message it answers (``quoted_text``).

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

        quoted_text = _quoted_text_of(message)

        # Voice message
        voice = message.get("voice")
        if voice:
            return ChannelInboundMessage(
                channel_type=ChannelType.TELEGRAM,
                channel_user_id=chat_id,
                voice_file_id=voice.get("file_id"),
                voice_duration_seconds=voice.get("duration"),
                message_id=str(message.get("message_id", "")),
                quoted_text=quoted_text,
                raw_data=payload,
            )

        # A photo or a document, its caption as its words (lot 11)
        files = _files_of(message)
        if files:
            album = message.get("media_group_id")
            return ChannelInboundMessage(
                channel_type=ChannelType.TELEGRAM,
                channel_user_id=chat_id,
                text=_text_field(message, "caption"),
                files=files,
                album_id=album if isinstance(album, str) and album else None,
                message_id=str(message.get("message_id", "")),
                quoted_text=quoted_text,
                raw_data=payload,
            )

        # Shared location (lot 8)
        location = _location_of(message)
        if location is not None:
            return ChannelInboundMessage(
                channel_type=ChannelType.TELEGRAM,
                channel_user_id=chat_id,
                location=location,
                message_id=str(message.get("message_id", "")),
                quoted_text=quoted_text,
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
                quoted_text=quoted_text,
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

        press_id = callback_query.get("id")
        return ChannelInboundMessage(
            channel_type=ChannelType.TELEGRAM,
            channel_user_id=chat_id,
            callback_data=callback_query.get("data"),
            message_id=str(message.get("message_id", "")),
            press_id=press_id if isinstance(press_id, str) and press_id else None,
            raw_data={"callback_query": callback_query},
        )
