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
from src.core.constants import TELEGRAM_PHOTO_UPLOAD_MAX_BYTES
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


async def test_a_long_html_message_is_sent_in_parts_that_each_parse() -> None:
    """Point 8: a part cut inside ``<b>…</b>`` was refused, then sent again as
    raw text — the person read the tags."""
    text = "<b>" + "word " * settings.telegram_message_max_length + "</b>"
    bot = _bot(*range(1, len(text)))  # one answer per part, whatever their number

    with patch(_GET_BOT, return_value=bot):
        await TelegramSender().send_message("12345", ChannelOutboundMessage(text=text))

    parts = [call.kwargs["text"] for call in bot.send_message.await_args_list]
    assert len(parts) > 1
    assert all(part.startswith("<b>") and part.endswith("</b>") for part in parts)
    assert all(call.kwargs["parse_mode"] == "HTML" for call in bot.send_message.await_args_list)


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


@pytest.mark.parametrize(
    ("enabled", "disabled_preview"), [(False, True), (True, False)], ids=["default", "on"]
)
@pytest.mark.parametrize(
    "outcomes",
    [(7,), (RetryAfter(0), 7), (BadRequest("Can't parse entities"), 7)],
    ids=["sent", "retried_after_rate_limit", "resent_as_text"],
)
async def test_every_send_carries_the_instance_s_link_preview_choice(
    enabled: bool, disabled_preview: bool, outcomes: tuple[object, ...]
) -> None:
    """Telegram drew a large preview of the FIRST link of an answer that cites
    ten — every send, the retries included, says what the instance chose
    (``TELEGRAM_LINK_PREVIEW_ENABLED``, off by default)."""
    bot = _bot(*outcomes)

    with (
        patch(_GET_BOT, return_value=bot),
        patch(_SLEEP, new=AsyncMock()),
        patch.object(settings, "telegram_link_preview_enabled", enabled),
    ):
        await TelegramSender().send_message(
            "12345", ChannelOutboundMessage(text="see https://a.example and https://b.example")
        )

    previews = [call.kwargs["link_preview_options"] for call in bot.send_message.await_args_list]
    assert len(previews) == len(outcomes)
    assert all(preview.is_disabled is disabled_preview for preview in previews)


async def test_a_notification_is_sent_drawn() -> None:
    bot = _bot(3)

    with patch(_GET_BOT, return_value=bot):
        sent = await TelegramSender().send_notification("12345", "Routine", "**Fait** : 3 mails")

    assert sent is True
    assert bot.send_message.await_args is not None
    assert bot.send_message.await_args.kwargs["text"] == "<b>Routine</b>\n\n<b>Fait</b> : 3 mails"
    assert bot.send_message.await_args.kwargs["parse_mode"] == "HTML"


async def test_a_notification_carries_its_buttons_under_its_last_part() -> None:
    """A fired reminder's « later » ride on the notification (ADR-268 amendment 2026-11-16)."""
    bot = _bot(3)
    keyboard = {"inline_keyboard": [[{"text": "Dans 10 min", "callback_data": "rmd:short:x"}]]}

    with patch(_GET_BOT, return_value=bot):
        sent = await TelegramSender().send_notification(
            "12345", "Rappel", "Arroser les plantes", language="fr", reply_markup=keyboard
        )

    assert sent is True
    assert bot.send_message.await_args is not None
    assert bot.send_message.await_args.kwargs["reply_markup"] == keyboard


async def test_a_kept_message_is_acknowledged_by_a_reaction() -> None:
    """Words that wait are marked « seen » on the person's own message (lot 34)."""
    from telegram import ReactionTypeEmoji

    bot = _bot()
    bot.set_message_reaction = AsyncMock(return_value=True)

    with patch(_GET_BOT, return_value=bot):
        acknowledged = await TelegramSender().acknowledge("12345", "77")

    assert acknowledged is True
    bot.set_message_reaction.assert_awaited_once_with(
        chat_id=12345, message_id=77, reaction=[ReactionTypeEmoji("👀")]
    )


@pytest.mark.parametrize(
    "refusal", [BadRequest("Reactions are disabled"), TelegramError("down")], ids=str
)
async def test_a_refused_reaction_says_so(refusal: TelegramError) -> None:
    bot = _bot()
    bot.set_message_reaction = AsyncMock(side_effect=refusal)

    with patch(_GET_BOT, return_value=bot):
        assert await TelegramSender().acknowledge("12345", "77") is False


async def test_no_bot_or_no_message_acknowledges_nothing() -> None:
    with patch(_GET_BOT, return_value=None):
        assert await TelegramSender().acknowledge("12345", "77") is False
    bot = _bot()
    bot.set_message_reaction = AsyncMock()
    with patch(_GET_BOT, return_value=bot):
        assert await TelegramSender().acknowledge("12345", "") is False
    bot.set_message_reaction.assert_not_awaited()


async def test_a_press_is_answered_so_its_button_stops_loading() -> None:
    """Telegram draws a progress bar on a pressed button until the bot answers."""
    bot = _bot()
    bot.answer_callback_query = AsyncMock(return_value=True)

    with patch(_GET_BOT, return_value=bot):
        assert await TelegramSender().answer_press("press-1", "Sent.") is True
        assert await TelegramSender().answer_press("press-2") is True

    assert bot.answer_callback_query.await_args_list[0].kwargs == {
        "callback_query_id": "press-1",
        "text": "Sent.",
    }
    assert bot.answer_callback_query.await_args_list[1].kwargs == {
        "callback_query_id": "press-2",
        "text": None,
    }


async def test_a_press_telegram_will_not_answer_is_no_failure_of_the_turn() -> None:
    bot = _bot()
    bot.answer_callback_query = AsyncMock(side_effect=BadRequest("Query is too old"))

    with patch(_GET_BOT, return_value=bot):
        assert await TelegramSender().answer_press("press-1") is False


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


# --- A file LIA made, sent as itself (lot 11) -----------------------------------


def _file_bot(*photo_outcomes: BaseException) -> MagicMock:
    """A bot whose ``send_photo`` raises each outcome in turn, then succeeds."""
    failures = iter(photo_outcomes)

    async def photo(**_kwargs: object) -> SimpleNamespace:
        failure = next(failures, None)
        if failure is not None:
            raise failure
        return SimpleNamespace(message_id=7)

    bot = MagicMock()
    bot.send_photo = AsyncMock(side_effect=photo)
    bot.send_document = AsyncMock(return_value=SimpleNamespace(message_id=8))
    return bot


@pytest.mark.parametrize(
    ("mime_type", "size", "as_photo"),
    [
        ("image/png", 10, True),
        ("image/jpeg", 10, True),
        ("image/webp", 10, True),
        ("image/svg+xml", 10, False),
        ("application/pdf", 10, False),
        ("image/png", TELEGRAM_PHOTO_UPLOAD_MAX_BYTES + 1, False),
    ],
    ids=["png", "jpeg", "webp", "svg", "pdf", "photo_past_its_ceiling"],
)
async def test_a_picture_is_sent_as_a_photo_anything_else_as_a_document(
    mime_type: str, size: int, as_photo: bool
) -> None:
    bot = _file_bot()
    content = b"x" * size

    with patch(_GET_BOT, return_value=bot):
        sent = await TelegramSender().send_file(
            "12345", content, filename="made.bin", mime_type=mime_type
        )

    assert sent is True
    used, unused = (
        (bot.send_photo, bot.send_document) if as_photo else (bot.send_document, bot.send_photo)
    )
    used.assert_awaited_once()
    unused.assert_not_awaited()
    kwargs = used.await_args.kwargs
    assert kwargs["chat_id"] == 12345 and kwargs["filename"] == "made.bin"
    assert kwargs["photo" if as_photo else "document"] == content


async def test_a_photo_telegram_refuses_leaves_as_a_document() -> None:
    """A picture Telegram will not draw (its dimensions) still reaches the person."""
    bot = _file_bot(BadRequest("PHOTO_INVALID_DIMENSIONS"))

    with patch(_GET_BOT, return_value=bot):
        sent = await TelegramSender().send_file(
            "12345", b"png", filename="wide.png", mime_type="image/png"
        )

    assert sent is True
    bot.send_document.assert_awaited_once()


async def test_a_file_held_back_by_the_rate_limit_is_sent_once_it_passes() -> None:
    bot = _file_bot(RetryAfter(3))

    with patch(_GET_BOT, return_value=bot), patch(_SLEEP, AsyncMock()) as slept:
        sent = await TelegramSender().send_file(
            "12345", b"png", filename="a.png", mime_type="image/png"
        )

    assert sent is True and bot.send_photo.await_count == 2
    slept.assert_awaited_once()


async def test_a_file_telegram_refuses_is_reported_unsent() -> None:
    bot = _file_bot()
    bot.send_document = AsyncMock(side_effect=TelegramError("too big"))

    with patch(_GET_BOT, return_value=bot):
        sent = await TelegramSender().send_file(
            "12345", b"%PDF", filename="r.pdf", mime_type="application/pdf"
        )

    assert sent is False


async def test_no_bot_sends_no_file() -> None:
    with patch(_GET_BOT, return_value=None):
        assert (
            await TelegramSender().send_file("1", b"x", filename="a", mime_type="text/plain")
            is False
        )


# --- An answer heard (lot 25) ------------------------------------------------------


async def test_an_answer_heard_leaves_as_a_voice_message() -> None:
    """An MP3 plays as a voice message (Bot API 7.3): no conversion on the way."""
    bot = MagicMock(send_voice=AsyncMock(return_value=SimpleNamespace(message_id=9)))

    with patch(_GET_BOT, return_value=bot):
        sent = await TelegramSender().send_voice("12345", b"ID3mp3")

    assert sent is True
    kwargs = bot.send_voice.await_args.kwargs
    assert (kwargs["chat_id"], kwargs["voice"]) == (12345, b"ID3mp3")
    assert kwargs["filename"].endswith(".mp3")


async def test_a_voice_held_back_by_the_rate_limit_is_sent_once_it_passes() -> None:
    sent_once = SimpleNamespace(message_id=9)
    bot = MagicMock(send_voice=AsyncMock(side_effect=[RetryAfter(2), sent_once]))

    with patch(_GET_BOT, return_value=bot), patch(_SLEEP, AsyncMock()) as slept:
        assert await TelegramSender().send_voice("12345", b"mp3") is True

    slept.assert_awaited_once()
    assert bot.send_voice.await_count == 2


async def test_a_voice_telegram_refuses_is_reported_unsent() -> None:
    bot = MagicMock(send_voice=AsyncMock(side_effect=BadRequest("VOICE_MESSAGES_FORBIDDEN")))

    with patch(_GET_BOT, return_value=bot):
        assert await TelegramSender().send_voice("12345", b"mp3") is False


async def test_no_bot_sends_no_voice() -> None:
    with patch(_GET_BOT, return_value=None):
        assert await TelegramSender().send_voice("1", b"mp3") is False
