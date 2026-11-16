"""
Telegram sender implementing BaseChannelSender.

Handles sending messages, typing indicators, keyboard removal,
and notifications via the Telegram Bot API.

Includes error handling for Telegram-specific exceptions
(rate limiting, bot blocked, chat not found, etc.).

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from telegram import LinkPreviewOptions, ReactionTypeEmoji
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError

from src.core.config import settings
from src.core.constants import (
    CHANNEL_TYPE_TELEGRAM,
    TELEGRAM_PHOTO_UPLOAD_MAX_BYTES,
    TELEGRAM_TYPING_ACTION,
)
from src.domains.channels.abstractions import BaseChannelSender, ChannelOutboundMessage
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.channels.telegram.bot import get_bot
from src.infrastructure.channels.telegram.flood_control import retry_after_seconds
from src.infrastructure.channels.telegram.formatter import (
    format_notification,
    split_message,
)
from src.infrastructure.channels.telegram.html_split import split_html_message
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_messages_sent_total,
    channel_send_errors_total,
)

logger = get_logger(__name__)

#: The reaction that says « received, I answer once I'm done » (lot 34): one of
#: the emoji Telegram lets a bot react with.
_WAITING_REACTION = "👀"
#: The pictures Telegram draws as a photo; anything else leaves as a document (lot 11).
_PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
#: The name an answer heard is uploaded under: an MP3 plays as a voice message (lot 25).
_VOICE_FILENAME = "lia.mp3"


async def _auto_disable_binding(channel_user_id: str) -> None:
    """Auto-disable binding when the bot is blocked by the user (Forbidden)."""
    try:
        from src.domains.channels.repository import UserChannelBindingRepository
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            repo = UserChannelBindingRepository(db)
            binding = await repo.get_by_channel_id(CHANNEL_TYPE_TELEGRAM, channel_user_id)
            if binding and binding.is_active:
                binding.is_active = False
                await db.commit()
                logger.info(
                    "telegram_binding_auto_disabled",
                    chat_id=channel_user_id,
                )
    except Exception:
        logger.error(
            "telegram_binding_auto_disable_failed",
            chat_id=channel_user_id,
            exc_info=True,
        )


async def _past_the_rate_limit(send: Callable[[], Awaitable[object]]) -> None:
    """Send once; a rate limit is waited out and the send tried once more."""
    try:
        await send()
    except RetryAfter as e:
        channel_send_errors_total.labels(
            channel_type=CHANNEL_TYPE_TELEGRAM, error_type="rate_limit"
        ).inc()
        await asyncio.sleep(retry_after_seconds(e))
        await send()


def _media_refused(channel_user_id: str, error: TelegramError) -> bool:
    """Count and log a file or a voice Telegram did not take: it is reported unsent.

    A bot the person blocked switches their binding off, as for a message.
    """
    if isinstance(error, Forbidden):
        error_type = "forbidden"
        safe_fire_and_forget(
            _auto_disable_binding(channel_user_id), name="telegram_auto_disable_binding"
        )
    else:
        error_type = "bad_request" if isinstance(error, BadRequest) else "network"
    logger.warning(
        "telegram_send_media_failed",
        chat_id=channel_user_id,
        error_type=error_type,
        error_class=type(error).__name__,
    )
    channel_send_errors_total.labels(
        channel_type=CHANNEL_TYPE_TELEGRAM, error_type=error_type
    ).inc()
    return False


class TelegramSender(BaseChannelSender):
    """
    Concrete sender for the Telegram channel.

    Uses the global bot singleton (initialized at startup).
    Handles message splitting, Telegram HTML formatting,
    and platform-specific error recovery.
    """

    async def send_message(
        self,
        channel_user_id: str,
        message: ChannelOutboundMessage,
    ) -> str | None:
        """
        Send a message to a Telegram chat.

        Automatically splits long messages — an HTML one on tag boundaries,
        each part closing what it opened (point 8). A keyboard rides on the
        LAST part, where the question ends, and on its retries: a part without
        it would leave the question unanswerable by button. Returns the
        message_id of the last sent chunk.

        Args:
            channel_user_id: Telegram chat_id.
            message: Outbound message to send.

        Returns:
            Message ID of the last sent chunk, or None on failure.
        """
        bot = get_bot()
        if not bot:
            logger.error("telegram_send_no_bot")
            return None

        chat_id = int(channel_user_id)
        chunks = (
            split_html_message(message.text)
            if message.parse_mode == "HTML"
            else split_message(message.text)
        )
        last_message_id: str | None = None
        # Heuristic: HTML parse_mode indicates proactive/notification messages
        # TODO: Add explicit message_type field to ChannelOutboundMessage for accuracy
        msg_type = "notification" if message.parse_mode == "HTML" else "text"
        # Every send, the retries included, carries the instance's choice: an
        # answer citing ten sources drew a large preview of the first alone.
        previews = LinkPreviewOptions(is_disabled=not settings.telegram_link_preview_enabled)

        for index, chunk in enumerate(chunks):
            markup = message.reply_markup if index == len(chunks) - 1 else None
            try:
                sent = await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=message.parse_mode,
                    reply_markup=markup,
                    link_preview_options=previews,
                )
                last_message_id = str(sent.message_id)
                channel_messages_sent_total.labels(
                    channel_type=CHANNEL_TYPE_TELEGRAM,
                    message_type=msg_type,
                ).inc()
            except Forbidden:
                logger.warning("telegram_bot_blocked", chat_id=channel_user_id)
                channel_send_errors_total.labels(
                    channel_type=CHANNEL_TYPE_TELEGRAM,
                    error_type="forbidden",
                ).inc()
                safe_fire_and_forget(
                    _auto_disable_binding(channel_user_id),
                    name="telegram_auto_disable_binding",
                )
                return None
            except RetryAfter as e:
                delay_seconds = retry_after_seconds(e)
                logger.warning(
                    "telegram_rate_limit",
                    chat_id=channel_user_id,
                    retry_after=delay_seconds,
                )
                channel_send_errors_total.labels(
                    channel_type=CHANNEL_TYPE_TELEGRAM,
                    error_type="rate_limit",
                ).inc()
                await asyncio.sleep(delay_seconds)
                # Retry once
                try:
                    sent = await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode=message.parse_mode,
                        reply_markup=markup,
                        link_preview_options=previews,
                    )
                    last_message_id = str(sent.message_id)
                    channel_messages_sent_total.labels(
                        channel_type=CHANNEL_TYPE_TELEGRAM,
                        message_type=msg_type,
                    ).inc()
                except TelegramError:
                    logger.error("telegram_send_retry_failed", chat_id=channel_user_id)
                    return None
            except BadRequest as e:
                logger.error(
                    "telegram_send_bad_request",
                    chat_id=channel_user_id,
                    error=str(e),
                )
                channel_send_errors_total.labels(
                    channel_type=CHANNEL_TYPE_TELEGRAM,
                    error_type="bad_request",
                ).inc()
                # Try sending without parse_mode (raw text fallback)
                try:
                    sent = await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        reply_markup=markup,
                        link_preview_options=previews,
                    )
                    last_message_id = str(sent.message_id)
                    channel_messages_sent_total.labels(
                        channel_type=CHANNEL_TYPE_TELEGRAM,
                        message_type=msg_type,
                    ).inc()
                except TelegramError:
                    return None
            except (NetworkError, TelegramError) as e:
                logger.error(
                    "telegram_send_error",
                    chat_id=channel_user_id,
                    error=str(e),
                )
                channel_send_errors_total.labels(
                    channel_type=CHANNEL_TYPE_TELEGRAM,
                    error_type="network",
                ).inc()
                return None

        return last_message_id

    async def send_file(
        self, channel_user_id: str, content: bytes, *, filename: str, mime_type: str
    ) -> bool:
        """Send a file LIA made: a picture as a photo, anything else as a document (lot 11).

        A photo Telegram refuses to draw (its dimensions) leaves as a document;
        a rate limit is waited out once.

        Args:
            channel_user_id: Telegram chat_id.
            content: The file's bytes (within Telegram's document ceiling).
            filename: The name it is shown and saved under.
            mime_type: What the file is.

        Returns:
            True if sent, False when Telegram refused it.
        """
        bot = get_bot()
        if not bot:
            logger.error("telegram_send_no_bot")
            return False
        chat_id = int(channel_user_id)
        as_photo = mime_type in _PHOTO_TYPES and len(content) <= TELEGRAM_PHOTO_UPLOAD_MAX_BYTES

        async def photo() -> object:
            return await bot.send_photo(chat_id=chat_id, photo=content, filename=filename)

        async def document() -> object:
            return await bot.send_document(chat_id=chat_id, document=content, filename=filename)

        try:
            try:
                await _past_the_rate_limit(photo if as_photo else document)
            except BadRequest:
                if not as_photo:
                    raise
                as_photo = False
                await _past_the_rate_limit(document)
        except TelegramError as error:
            return _media_refused(channel_user_id, error)
        channel_messages_sent_total.labels(
            channel_type=CHANNEL_TYPE_TELEGRAM, message_type="photo" if as_photo else "document"
        ).inc()
        return True

    async def send_voice(self, channel_user_id: str, audio: bytes) -> bool:
        """Send an answer heard: MP3 bytes, played as a voice message (lot 25).

        Telegram plays an MP3 as a voice message (Bot API 7.3): nothing is
        converted on the way. A rate limit is waited out once.

        Args:
            channel_user_id: Telegram chat_id.
            audio: The MP3 bytes.

        Returns:
            True if sent, False when Telegram refused it.
        """
        bot = get_bot()
        if not bot:
            logger.error("telegram_send_no_bot")
            return False

        async def voice() -> object:
            return await bot.send_voice(
                chat_id=int(channel_user_id), voice=audio, filename=_VOICE_FILENAME
            )

        try:
            await _past_the_rate_limit(voice)
        except TelegramError as error:
            return _media_refused(channel_user_id, error)
        channel_messages_sent_total.labels(
            channel_type=CHANNEL_TYPE_TELEGRAM, message_type="voice"
        ).inc()
        return True

    async def send_typing_indicator(self, channel_user_id: str) -> None:
        """Send a typing indicator to show the bot is processing."""
        bot = get_bot()
        if not bot:
            return

        try:
            await bot.send_chat_action(
                chat_id=int(channel_user_id),
                action=TELEGRAM_TYPING_ACTION,
            )
        except TelegramError as e:
            logger.debug("telegram_typing_error", error=str(e))

    async def send_notification(
        self,
        channel_user_id: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        *,
        language: str | None = None,
        reply_markup: dict | None = None,
    ) -> bool:
        """
        Send a proactive notification to a Telegram chat.

        Args:
            channel_user_id: Telegram chat_id.
            title: Notification title (formatted as bold).
            body: Notification body, as the chat shows it (drawn here).
            data: Optional metadata (currently unused for Telegram).
            language: The reader's language (default: the declared language).
            reply_markup: An inline keyboard, drawn under the last chunk.

        Returns:
            True if sent successfully.
        """
        formatted = format_notification(title, body, language)
        message = ChannelOutboundMessage(
            text=formatted, parse_mode="HTML", reply_markup=reply_markup
        )
        result = await self.send_message(channel_user_id, message)
        return result is not None

    async def acknowledge(self, channel_user_id: str, message_id: str) -> bool:
        """
        Mark the person's message « seen » with a reaction (lot 34).

        Words written while LIA works wait their turn: the reaction says they
        were received without a message of its own per word sent. Best effort —
        a chat where reactions are off answers False, and the caller says it in
        words instead.

        Args:
            channel_user_id: Telegram chat_id.
            message_id: Telegram message_id of the person's message.

        Returns:
            True when the reaction is on the message.
        """
        bot = get_bot()
        if not bot or not message_id:
            return False
        try:
            await bot.set_message_reaction(
                chat_id=int(channel_user_id),
                message_id=int(message_id),
                reaction=[ReactionTypeEmoji(_WAITING_REACTION)],
            )
            return True
        except TelegramError as e:
            logger.warning(
                "telegram_reaction_refused",
                chat_id=channel_user_id,
                error_type=type(e).__name__,
            )
            return False

    async def answer_press(self, press_id: str, text: str | None = None) -> bool:
        """
        Answer a button press: its button stops loading, ``text`` shows briefly.

        Telegram draws a progress bar on a pressed button until the bot answers
        the press (``answerCallbackQuery``). Best effort: a press answered late
        is refused by Telegram and changes nothing the press did.

        Args:
            press_id: The press's id (``callback_query.id``).
            text: A short notice shown above the chat, or None.

        Returns:
            True when Telegram took the answer.
        """
        bot = get_bot()
        if not bot:
            return False
        try:
            await bot.answer_callback_query(callback_query_id=press_id, text=text)
            return True
        except TelegramError as e:
            logger.info("telegram_press_answer_refused", error_type=type(e).__name__)
            return False

    async def remove_keyboard(self, channel_user_id: str, message_id: str) -> bool:
        """
        Take the inline keyboard off a message, its text kept.

        Used once a HITL question is answered by button, or when its button
        answers nothing any more: the question stays readable, and the same
        question cannot be pressed twice. Best effort — a keyboard already
        gone, or a message Telegram no longer edits, changes nothing the
        answer depends on.

        Args:
            channel_user_id: Telegram chat_id.
            message_id: Telegram message_id of the question.

        Returns:
            True if the keyboard is off, False when Telegram refused.
        """
        bot = get_bot()
        if not bot:
            return False

        try:
            await bot.edit_message_reply_markup(
                chat_id=int(channel_user_id),
                message_id=int(message_id),
                reply_markup=None,
            )
            return True
        except TelegramError as e:
            # Its type, never its description (ADR-303): the one expected here
            # is a keyboard already removed by an earlier press.
            logger.warning(
                "telegram_keyboard_removal_refused",
                chat_id=channel_user_id,
                message_id=message_id,
                error_type=type(e).__name__,
            )
            return False

    async def send_text(
        self,
        channel_user_id: str,
        text: str,
        parse_mode: str = "HTML",
    ) -> str | None:
        """
        Convenience method to send a plain text message.

        Args:
            channel_user_id: Telegram chat_id.
            text: Text to send.
            parse_mode: Formatting mode (default: HTML).

        Returns:
            Message ID or None.
        """
        message = ChannelOutboundMessage(text=text, parse_mode=parse_mode)
        return await self.send_message(channel_user_id, message)
