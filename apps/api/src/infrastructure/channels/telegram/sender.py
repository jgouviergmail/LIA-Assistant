"""
Telegram sender implementing BaseChannelSender.

Handles sending messages, typing indicators, message editing,
and notifications via the Telegram Bot API.

Includes error handling for Telegram-specific exceptions
(rate limiting, bot blocked, chat not found, etc.).

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import asyncio
from typing import Any

from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError

from src.core.constants import CHANNEL_TYPE_TELEGRAM, TELEGRAM_TYPING_ACTION
from src.domains.channels.abstractions import BaseChannelSender, ChannelOutboundMessage
from src.infrastructure.channels.telegram.bot import get_bot
from src.infrastructure.channels.telegram.formatter import (
    format_notification,
    split_message,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_messages_sent_total,
    channel_send_errors_total,
)

logger = get_logger(__name__)


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

        Automatically splits long messages. Returns the message_id
        of the last sent chunk.

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
        chunks = split_message(message.text)
        last_message_id: str | None = None
        # Heuristic: HTML parse_mode indicates proactive/notification messages
        # TODO: Add explicit message_type field to ChannelOutboundMessage for accuracy
        msg_type = "notification" if message.parse_mode == "HTML" else "text"

        for chunk in chunks:
            try:
                sent = await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=message.parse_mode,
                    reply_markup=message.reply_markup,
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
                asyncio.create_task(_auto_disable_binding(channel_user_id))
                return None
            except RetryAfter as e:
                logger.warning(
                    "telegram_rate_limit",
                    chat_id=channel_user_id,
                    retry_after=e.retry_after,
                )
                channel_send_errors_total.labels(
                    channel_type=CHANNEL_TYPE_TELEGRAM,
                    error_type="rate_limit",
                ).inc()
                await asyncio.sleep(e.retry_after)
                # Retry once
                try:
                    sent = await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode=message.parse_mode,
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
    ) -> bool:
        """
        Send a proactive notification to a Telegram chat.

        Args:
            channel_user_id: Telegram chat_id.
            title: Notification title (formatted as bold).
            body: Notification body.
            data: Optional metadata (currently unused for Telegram).

        Returns:
            True if sent successfully.
        """
        formatted = format_notification(title, body)
        message = ChannelOutboundMessage(text=formatted, parse_mode="HTML")
        result = await self.send_message(channel_user_id, message)
        return result is not None

    async def edit_message(
        self,
        channel_user_id: str,
        message_id: str,
        new_text: str,
        parse_mode: str = "HTML",
    ) -> bool:
        """
        Edit an existing Telegram message.

        Used to remove HITL inline keyboard buttons after user decision.

        Args:
            channel_user_id: Telegram chat_id.
            message_id: Telegram message_id to edit.
            new_text: New message text.
            parse_mode: Text formatting mode.

        Returns:
            True if edited successfully.
        """
        bot = get_bot()
        if not bot:
            return False

        try:
            await bot.edit_message_text(
                chat_id=int(channel_user_id),
                message_id=int(message_id),
                text=new_text,
                parse_mode=parse_mode,
            )
            return True
        except BadRequest as e:
            # "Message is not modified" is harmless
            if "not modified" in str(e).lower():
                return True
            logger.warning(
                "telegram_edit_bad_request",
                chat_id=channel_user_id,
                message_id=message_id,
                error=str(e),
            )
            return False
        except TelegramError as e:
            logger.error(
                "telegram_edit_error",
                chat_id=channel_user_id,
                message_id=message_id,
                error=str(e),
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
