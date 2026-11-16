"""A fired reminder's « later » and « stop », as Telegram buttons.

ADR-268 amendment 2026-11-16: a reminder that rings on Telegram offers what the
chat bubble offers — in 10 min, in 1 h, tomorrow morning, and « stop this
reminder » when it has a future. Each button names the OCCURRENCE that rang
(``rmd:{action}:{firing_id}``, 48 bytes of the 64 Telegram allows), never the
reminder: a one-shot one is already deleted when its notification is read.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple
from uuid import UUID

from src.core.i18n_reminder_snooze import snooze_button_label, snooze_delay_label

#: The prefix of every fired-reminder button's callback data.
REMINDER_CALLBACK_PREFIX = "rmd"


class ReminderButton(StrEnum):
    """What a fired-reminder button asks (the three ``SnoozeChoice`` and stop)."""

    SHORT = "short"
    LONG = "long"
    MORNING = "morning"
    STOP = "stop"


class ReminderPress(NamedTuple):
    """What a fired-reminder button carries back.

    Attributes:
        button: The choice pressed.
        firing_id: The occurrence the button was drawn for.
    """

    button: ReminderButton
    firing_id: UUID


def build_reminder_keyboard(
    firing_id: UUID,
    *,
    stoppable: bool,
    short_minutes: int,
    long_minutes: int,
    language: str | None,
) -> dict:
    """The inline keyboard of a fired reminder.

    Args:
        firing_id: The occurrence every button acts on.
        stoppable: Whether the reminder has a future « stop » would remove.
        short_minutes: The short delay.
        long_minutes: The long delay.
        language: The reader's language.

    Returns:
        An InlineKeyboardMarkup dict: the two delays, then the morning, then
        « stop » when it means something.
    """

    def button(kind: ReminderButton, text: str) -> dict[str, str]:
        return {"text": text, "callback_data": f"{REMINDER_CALLBACK_PREFIX}:{kind}:{firing_id}"}

    rows = [
        [
            button(ReminderButton.SHORT, snooze_delay_label(short_minutes, language)),
            button(ReminderButton.LONG, snooze_delay_label(long_minutes, language)),
        ],
        [button(ReminderButton.MORNING, snooze_button_label("morning", language))],
    ]
    if stoppable:
        rows.append([button(ReminderButton.STOP, snooze_button_label("stop", language))])
    return {"inline_keyboard": rows}


def parse_reminder_callback_data(callback_data: str | None) -> ReminderPress | None:
    """Read a fired-reminder button press, or None when it is not one.

    Args:
        callback_data: What the client sent back — anything at all.

    Returns:
        The press, or None for any other data (an action no keyboard draws, an
        id that is no UUID).
    """
    parts = (callback_data or "").split(":")
    if len(parts) != 3 or parts[0] != REMINDER_CALLBACK_PREFIX:
        return None
    try:
        return ReminderPress(ReminderButton(parts[1]), UUID(parts[2]))
    except ValueError:
        return None
