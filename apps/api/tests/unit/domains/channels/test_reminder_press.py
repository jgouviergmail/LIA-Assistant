"""A fired reminder's button, pressed on Telegram (ADR-268 amendment 2026-11-16).

The service is proved on PostgreSQL; this pins the channel's half: the press acts
for the LINKED account, in its zone and language, a refused account acts on
nothing, the answer says what happened (its instant on the person's wall), and
the buttons come off once the occurrence is settled — but stay when a shorter
delay can still work.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ResourceNotFoundError
from src.core.i18n_dates import format_short_stamp
from src.core.i18n_reminder_snooze import snooze_press_answer
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.models import ChannelType
from src.domains.channels.reminder_press import handle_reminder_press
from src.domains.reminders.firing_service import SnoozeResult
from src.domains.reminders.firings import FiringSurface, SnoozeChoice, SnoozeOutcome, StopOutcome
from src.infrastructure.channels.telegram.reminder_keyboard import ReminderButton, ReminderPress

pytestmark = pytest.mark.unit

MODULE = "src.domains.channels.reminder_press"
ZONE = "Asia/Tokyo"
BACK = datetime(2026, 11, 17, 0, 0, tzinfo=UTC)  # 09:00 in Tokyo


def _press(button: ReminderButton) -> tuple[ChannelInboundMessage, ReminderPress]:
    firing_id = uuid4()
    message = ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="4242",
        callback_data=f"rmd:{button}:{firing_id}",
        message_id="77",
        press_id="press-1",
    )
    return message, ReminderPress(button, firing_id)


class _Harness:
    def __init__(self, *, active: bool = True) -> None:
        self.binding = SimpleNamespace(user_id=uuid4(), is_active=True)
        self.person = SimpleNamespace(
            id=self.binding.user_id,
            is_active=active,
            language="fr",
            timezone=ZONE,
            journals_enabled=True,
            psyche_enabled=True,
        )
        self.sender = MagicMock()
        self.sender.answer_press = AsyncMock(return_value=True)
        self.sender.remove_keyboard = AsyncMock(return_value=True)
        self.sender.send_message = AsyncMock()
        self.service = MagicMock()
        self.service.snooze = AsyncMock()
        self.service.stop = AsyncMock()
        self.refused = AsyncMock()

    def _db_context(self) -> Any:
        @asynccontextmanager
        async def _session() -> AsyncIterator[MagicMock]:
            yield MagicMock()

        return _session

    async def run(self, message: ChannelInboundMessage, press: ReminderPress) -> None:
        with (
            patch(
                "src.domains.channels.message_router.read_binding_and_person",
                AsyncMock(return_value=(self.binding, self.person)),
            ),
            patch("src.domains.channels.message_router.answer_refusal", self.refused),
            patch("src.infrastructure.cache.redis.get_redis_session", AsyncMock(return_value=None)),
            patch(f"{MODULE}.get_db_context", self._db_context()),
            patch(f"{MODULE}.ReminderFiringService", return_value=self.service),
        ):
            await handle_reminder_press(message, press, sender=self.sender)

    def answer(self) -> str | None:
        args, _ = self.sender.answer_press.await_args
        return args[1]


async def test_a_delay_postpones_for_the_linked_account_in_its_zone() -> None:
    harness = _Harness()
    harness.service.snooze.return_value = SnoozeResult(SnoozeOutcome.SNOOZED, snoozed_until=BACK)
    message, press = _press(ReminderButton.MORNING)

    await harness.run(message, press)

    args, kwargs = harness.service.snooze.await_args
    assert args == (press.firing_id, harness.binding.user_id, SnoozeChoice.MORNING)
    assert kwargs["zone"] == ZONE
    assert kwargs["surface"] is FiringSurface.TELEGRAM
    harness.sender.remove_keyboard.assert_awaited_once_with("4242", "77")
    assert harness.answer() == snooze_press_answer(
        "snoozed", "fr", when=format_short_stamp(BACK, ZONE, "fr")
    )
    assert "09:00" in (harness.answer() or "")


async def test_a_press_the_series_already_covers_keeps_the_buttons() -> None:
    harness = _Harness()
    harness.service.snooze.return_value = SnoozeResult(
        SnoozeOutcome.COLLIDES, next_occurrence_at=BACK
    )
    message, press = _press(ReminderButton.LONG)

    await harness.run(message, press)

    harness.sender.remove_keyboard.assert_not_awaited()
    assert harness.answer() == snooze_press_answer(
        "collides", "fr", when=format_short_stamp(BACK, ZONE, "fr")
    )


async def test_stop_stops_the_series_and_takes_the_buttons_off() -> None:
    harness = _Harness()
    harness.service.stop.return_value = StopOutcome.STOPPED
    message, press = _press(ReminderButton.STOP)

    await harness.run(message, press)

    args, kwargs = harness.service.stop.await_args
    assert args == (press.firing_id, harness.binding.user_id)
    assert kwargs["surface"] is FiringSurface.TELEGRAM
    harness.service.snooze.assert_not_awaited()
    harness.sender.remove_keyboard.assert_awaited_once()
    assert harness.answer() == snooze_press_answer("stopped", "fr")


async def test_a_purged_occurrence_is_said_gone() -> None:
    harness = _Harness()
    harness.service.snooze.side_effect = ResourceNotFoundError("reminder_firing", "x")
    message, press = _press(ReminderButton.SHORT)

    await harness.run(message, press)

    harness.sender.remove_keyboard.assert_awaited_once()
    assert harness.answer() == snooze_press_answer("gone", "fr")


async def test_a_deactivated_account_acts_on_nothing() -> None:
    harness = _Harness(active=False)
    message, press = _press(ReminderButton.SHORT)

    await harness.run(message, press)

    harness.service.snooze.assert_not_awaited()
    harness.sender.remove_keyboard.assert_not_awaited()
    harness.refused.assert_awaited_once()
    assert harness.refused.await_args.args[3] == "account_inactive"


async def test_a_failure_is_said_and_leaves_the_buttons() -> None:
    harness = _Harness()
    harness.service.snooze.side_effect = RuntimeError("database unreachable")
    message, press = _press(ReminderButton.SHORT)

    await harness.run(message, press)

    harness.sender.remove_keyboard.assert_not_awaited()
    answer = harness.answer()
    assert answer and "database" not in answer
