"""The Telegram sender: where a keyboard rides, and how it comes off.

A HITL question travels with its inline keyboard. Split into several messages,
it drew the keyboard under EVERY part, and a part retried after a rate limit
or a parse failure went out WITHOUT it — the question could no longer be
answered by button. Answered, the question lost its whole text to a « label ✓ »
edit; only its keyboard goes now (review 14 of the ADR-323 lot).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest, RetryAfter, TelegramError

from src.core.config import settings
from src.domains.channels.abstractions import ChannelOutboundMessage
from src.infrastructure.channels.telegram.sender import TelegramSender

pytestmark = pytest.mark.unit

_GET_BOT = "src.infrastructure.channels.telegram.sender.get_bot"
_SLEEP = "src.infrastructure.channels.telegram.sender.asyncio.sleep"
_KEYBOARD: dict[str, object] = {
    "inline_keyboard": [[{"text": "Confirm", "callback_data": "hitl:confirm:c:0a1b2c3d"}]]
}


def _bot(*outcomes: object) -> MagicMock:
    """A bot whose ``send_message`` answers each call with the next outcome
    (an exception to raise, or the message id to return)."""
    answers = iter(outcomes)

    async def _send(**_kwargs: object) -> SimpleNamespace:
        outcome = next(answers)
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(message_id=outcome)

    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=_send)
    bot.edit_message_reply_markup = AsyncMock()
    return bot


def _markups(bot: MagicMock) -> list[object]:
    return [call.kwargs.get("reply_markup") for call in bot.send_message.await_args_list]


async def test_a_split_question_carries_its_keyboard_on_its_last_part() -> None:
    bot = _bot(1, 2)
    long_text = "a" * settings.telegram_message_max_length + "\n\nb"

    with patch(_GET_BOT, return_value=bot):
        sent = await TelegramSender().send_message(
            "12345", ChannelOutboundMessage(text=long_text, reply_markup=_KEYBOARD)
        )

    assert sent == "2"
    assert _markups(bot) == [None, _KEYBOARD]


@pytest.mark.parametrize(
    "refusal",
    [RetryAfter(0), BadRequest("Can't parse entities")],
    ids=["rate_limited", "unparsable_html"],
)
async def test_a_retried_question_keeps_its_keyboard(refusal: TelegramError) -> None:
    bot = _bot(refusal, 7)

    with patch(_GET_BOT, return_value=bot), patch(_SLEEP, new=AsyncMock()):
        sent = await TelegramSender().send_message(
            "12345", ChannelOutboundMessage(text="Send it?", reply_markup=_KEYBOARD)
        )

    assert sent == "7"
    assert _markups(bot) == [_KEYBOARD, _KEYBOARD]


async def test_removing_a_keyboard_keeps_the_text() -> None:
    bot = _bot()

    with patch(_GET_BOT, return_value=bot):
        removed = await TelegramSender().remove_keyboard("12345", "77")

    assert removed is True
    bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=12345, message_id=77, reply_markup=None
    )


async def test_a_keyboard_telegram_will_not_remove_is_logged_by_its_type() -> None:
    """Best effort: a keyboard an earlier press already took off is refused —
    logged by the error's TYPE, never its description."""
    from structlog.testing import capture_logs

    bot = _bot()
    bot.edit_message_reply_markup = AsyncMock(
        side_effect=BadRequest("Message is not modified: private detail")
    )

    with patch(_GET_BOT, return_value=bot), capture_logs() as logs:
        removed = await TelegramSender().remove_keyboard("12345", "77")

    assert removed is False
    (refused,) = [e for e in logs if e["event"] == "telegram_keyboard_removal_refused"]
    assert refused["error_type"] == "BadRequest"
    assert "private detail" not in str(refused)


async def test_no_bot_removes_nothing() -> None:
    with patch(_GET_BOT, return_value=None):
        assert await TelegramSender().remove_keyboard("12345", "77") is False
