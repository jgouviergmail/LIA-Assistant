"""A fired reminder's buttons, pressed on Telegram (ADR-268 amendment 2026-11-16).

The notification of a reminder that rings on Telegram carries the chat bubble's
answers: in 10 min, in 1 h, tomorrow morning, and « stop this reminder » when it
has a future. A press names the OCCURRENCE that rang and is served by the same
service as the web's buttons (``ReminderFiringService``), for the account the
chat is linked to, in that account's zone and language.

Refused like any press — an unknown chat, a deactivated account, a channel
switched off — and answered where Telegram shows a press's answer, above the
chat. A press that settled the occurrence takes its buttons off; one refused
because the series already rings again before that instant leaves them, since a
shorter delay still works.
"""

from __future__ import annotations

import structlog

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.exceptions import ResourceNotFoundError
from src.core.i18n_dates import format_short_stamp
from src.core.i18n_reminder_snooze import snooze_press_answer
from src.core.time_utils import now_utc
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.preferences import resolve_channel_preferences
from src.domains.channels.waiting import answer_press
from src.domains.reminders.firing_service import ReminderFiringService, SnoozeResult
from src.domains.reminders.firings import FiringSurface, SnoozeChoice, SnoozeOutcome
from src.infrastructure.channels.telegram.formatter import get_bot_message
from src.infrastructure.channels.telegram.reminder_keyboard import ReminderButton, ReminderPress
from src.infrastructure.channels.telegram.sender import TelegramSender
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def handle_reminder_press(
    message: ChannelInboundMessage, press: ReminderPress, *, sender: TelegramSender
) -> None:
    """Postpone the occurrence a button names, or stop its reminder.

    The service's transaction is closed before Telegram is answered (ADR-304).

    Args:
        message: The press.
        press: The button and the occurrence it was drawn for.
        sender: The bot's sender.
    """
    from src.domains.channels.message_router import (
        Recipient,
        answer_refusal,
        read_binding_and_person,
        refusal_for,
    )
    from src.infrastructure.cache.redis import get_redis_session

    channel_type = message.channel_type.value
    try:
        found = await read_binding_and_person(channel_type, message.channel_user_id)
    except Exception:
        logger.error("channel_reminder_press_lookup_failed", exc_info=True)
        await answer_press(sender, message, get_bot_message("error"))
        return
    if found is None:
        await answer_press(sender, message, get_bot_message("unbound"))
        return
    binding, person = found
    language = resolve_channel_preferences(person).language
    refusal = refusal_for(binding, person)
    if refusal is not None:
        await answer_press(sender, message, None)
        where = Recipient(channel_type, message.channel_user_id, binding.user_id, language)
        await answer_refusal(await get_redis_session(), sender, where, refusal)
        return
    zone = person.timezone or DEFAULT_USER_DISPLAY_TIMEZONE
    try:
        async with get_db_context() as db:
            service = ReminderFiringService(db)
            if press.button is ReminderButton.STOP:
                stopped = await service.stop(
                    press.firing_id,
                    binding.user_id,
                    now=now_utc(),
                    surface=FiringSurface.TELEGRAM,
                )
                outcome, text = stopped.value, snooze_press_answer(stopped.value, language)
            else:
                result = await service.snooze(
                    press.firing_id,
                    binding.user_id,
                    SnoozeChoice(press.button.value),
                    zone=zone,
                    now=now_utc(),
                    surface=FiringSurface.TELEGRAM,
                )
                outcome, text = result.outcome.value, _snooze_answer(result, zone, language)
    except ResourceNotFoundError:
        outcome, text = "gone", snooze_press_answer("gone", language)
    except Exception:
        logger.error("channel_reminder_press_failed", user_id=str(binding.user_id), exc_info=True)
        await answer_press(sender, message, get_bot_message("error", language))
        return
    if outcome != SnoozeOutcome.COLLIDES.value and message.message_id:
        await sender.remove_keyboard(message.channel_user_id, message.message_id)
    await answer_press(sender, message, text)
    logger.info(
        "channel_reminder_press",
        user_id=str(binding.user_id),
        button=press.button.value,
        outcome=outcome,
    )


def _snooze_answer(result: SnoozeResult, zone: str, language: str) -> str:
    """The sentence of a snooze verdict, its instant on the person's wall."""
    moment = result.snoozed_until or result.next_occurrence_at
    when = format_short_stamp(moment, zone, language) if moment is not None else ""
    return snooze_press_answer(result.outcome.value, language, when=when)
