"""Tests for the Telegram flood-control delay reader.

Regression: every read of ``RetryAfter.retry_after`` emitted a
``PTBDeprecationWarning`` (python-telegram-bot 22.2 deprecated the numeric
form). The package opts in to the ``timedelta`` form once and one reader
accepts both shapes, so a flood limit is waited out without a warning.
"""

import warnings
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import RetryAfter
from telegram.warnings import PTBDeprecationWarning

from src.core.constants import CHANNEL_TYPE_TELEGRAM
from src.domains.channels.abstractions import ChannelOutboundMessage
from src.infrastructure.channels.telegram import sender as telegram_sender
from src.infrastructure.channels.telegram.flood_control import retry_after_seconds


@pytest.mark.unit
class TestRetryAfterSeconds:
    def test_the_delay_is_read_in_seconds_without_a_deprecation(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            delay = retry_after_seconds(RetryAfter(3))

        assert delay == 3.0
        assert not [w for w in caught if issubclass(w.category, PTBDeprecationWarning)]

    def test_a_timedelta_delay_is_converted(self) -> None:
        exc = MagicMock(spec=RetryAfter)
        exc.retry_after = timedelta(seconds=1, milliseconds=500)

        assert retry_after_seconds(exc) == 1.5

    def test_a_numeric_delay_is_still_accepted(self) -> None:
        # An operator may force PTB_TIMEDELTA=false; the number must still work.
        exc = MagicMock(spec=RetryAfter)
        exc.retry_after = 7

        assert retry_after_seconds(exc) == 7.0


@pytest.mark.unit
class TestSenderWaitsOutAFloodLimit:
    async def test_the_sender_sleeps_the_delay_then_retries_once(self) -> None:
        sent = MagicMock()
        sent.message_id = 42
        bot = MagicMock()
        bot.send_message = AsyncMock(side_effect=[RetryAfter(2), sent])
        message = ChannelOutboundMessage(text="hello")

        with (
            patch.object(telegram_sender, "get_bot", return_value=bot),
            patch.object(telegram_sender.asyncio, "sleep", AsyncMock()) as sleep,
            patch.object(telegram_sender, "channel_send_errors_total") as errors,
        ):
            message_id = await telegram_sender.TelegramSender().send_message("123", message)

        assert message_id == "42"
        assert bot.send_message.await_count == 2
        sleep.assert_awaited_once_with(2.0)
        errors.labels.assert_called_once_with(
            channel_type=CHANNEL_TYPE_TELEGRAM, error_type="rate_limit"
        )
