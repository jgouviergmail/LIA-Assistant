"""A fired reminder's buttons name the occurrence they act on (ADR-268 amendment 2026-11-16)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.core.i18n_reminder_snooze import snooze_button_label, snooze_delay_label
from src.infrastructure.channels.telegram.hitl_keyboard import (
    TELEGRAM_CALLBACK_DATA_MAX_BYTES,
    parse_hitl_callback_data,
)
from src.infrastructure.channels.telegram.reminder_keyboard import (
    ReminderButton,
    ReminderPress,
    build_reminder_keyboard,
    parse_reminder_callback_data,
)
from src.infrastructure.channels.telegram.waiting_keyboard import parse_waiting_callback_data

pytestmark = pytest.mark.unit

#: A fixed id: parameters drawn at collection differ between xdist workers.
_SOME_ID = "4f1c2b9e-8d7a-4c3b-9e2f-1a2b3c4d5e6f"


def _buttons(keyboard: dict) -> list[dict[str, str]]:
    return [button for row in keyboard["inline_keyboard"] for button in row]


def test_each_button_reads_back_as_its_choice_on_its_occurrence() -> None:
    firing_id = uuid4()

    buttons = _buttons(
        build_reminder_keyboard(
            firing_id, stoppable=True, short_minutes=10, long_minutes=60, language="fr"
        )
    )

    presses = [parse_reminder_callback_data(button["callback_data"]) for button in buttons]
    assert presses == [ReminderPress(kind, firing_id) for kind in ReminderButton]
    assert all(
        len(button["callback_data"].encode()) <= TELEGRAM_CALLBACK_DATA_MAX_BYTES
        for button in buttons
    )


def test_a_reminder_with_no_future_offers_nothing_to_stop() -> None:
    buttons = _buttons(
        build_reminder_keyboard(
            uuid4(), stoppable=False, short_minutes=10, long_minutes=60, language="fr"
        )
    )

    kinds = [parse_reminder_callback_data(button["callback_data"]) for button in buttons]
    assert [press.button for press in kinds if press is not None] == [
        ReminderButton.SHORT,
        ReminderButton.LONG,
        ReminderButton.MORNING,
    ]


@pytest.mark.parametrize("language", ["fr", "zh-CN"])
def test_the_buttons_speak_the_readers_language_and_the_configured_delays(
    language: str,
) -> None:
    buttons = _buttons(
        build_reminder_keyboard(
            uuid4(), stoppable=True, short_minutes=15, long_minutes=120, language=language
        )
    )

    assert [button["text"] for button in buttons] == [
        snooze_delay_label(15, language),
        snooze_delay_label(120, language),
        snooze_button_label("morning", language),
        snooze_button_label("stop", language),
    ]


def test_a_whole_hour_is_said_in_hours_and_the_rest_in_minutes() -> None:
    assert snooze_delay_label(10, "fr") == "Dans 10 min"
    assert snooze_delay_label(60, "fr") == "Dans 1 h"
    assert snooze_delay_label(90, "fr") == "Dans 90 min"
    assert snooze_delay_label(120, "zh-CN") == "2 小时后"


@pytest.mark.parametrize(
    "data",
    [
        None,
        "",
        "rmd:short",
        f"rmd:later:{_SOME_ID}",
        "rmd:short:not-a-uuid",
        f"rmd:short:{_SOME_ID}:extra",
        f"wait:send:{_SOME_ID}",
        "hitl:confirm:c:0a1b2c3d",
    ],
)
def test_anything_else_is_no_press(data: str | None) -> None:
    assert parse_reminder_callback_data(data) is None


def test_no_other_keyboard_reads_a_reminder_press() -> None:
    """The dispatch tries the waiting parser first, then this one, then HITL."""
    data = f"rmd:morning:{_SOME_ID}"

    assert parse_waiting_callback_data(data) is None
    assert parse_hitl_callback_data(data) is None
    assert parse_reminder_callback_data(data) == ReminderPress(
        ReminderButton.MORNING, UUID(_SOME_ID)
    )
