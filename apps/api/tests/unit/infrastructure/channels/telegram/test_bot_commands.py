"""The bot's command menu: what Telegram lists when the person types « / » (lot 33).

The menu is bot-GLOBAL state, set by the scheduler leader once — like the
webhook — in each of LIA's languages, and for every other client language in
the instance's own.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import RetryAfter

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_TELEGRAM_COMMANDS, SCHEDULER_JOB_TELEGRAM_WEBHOOK
from src.infrastructure.channels.telegram import bot as telegram_bot
from src.infrastructure.channels.telegram.formatter import get_bot_message
from src.infrastructure.startup import schedulers

pytestmark = pytest.mark.unit


def _menus(bot: MagicMock) -> dict[str | None, list[tuple[str, str]]]:
    menus: dict[str | None, list[tuple[str, str]]] = {}
    for call in bot.set_my_commands.await_args_list:
        commands = call.kwargs["commands"]
        menus[call.kwargs.get("language_code")] = [(c.command, c.description) for c in commands]
    return menus


async def test_the_menu_is_set_in_every_language_and_for_everyone_else() -> None:
    bot = MagicMock(set_my_commands=AsyncMock(return_value=True))

    with patch.object(telegram_bot, "_bot", bot):
        await telegram_bot.ensure_telegram_commands()

    menus = _menus(bot)
    assert set(menus) == {None, "fr", "en", "es", "de", "it", "zh"}
    assert menus["fr"] == [
        ("stop", "Arrêter ma réponse en cours"),
        ("help", "Ce que je sais faire ici"),
    ]
    # LIA's zh-CN is Telegram's zh: a Chinese client reads Chinese.
    assert menus["zh"] == [("stop", "停止当前回答"), ("help", "我在这里能做什么")]
    # Any other client language reads the instance's declared language.
    assert menus[None] == [
        ("stop", get_bot_message("command_stop", settings.default_language)),
        ("help", get_bot_message("command_help", settings.default_language)),
    ]


async def test_a_flood_limit_is_waited_out_once() -> None:
    bot = MagicMock(set_my_commands=AsyncMock(side_effect=[RetryAfter(1), *[True] * 7]))

    with (
        patch.object(telegram_bot, "_bot", bot),
        patch.object(telegram_bot.asyncio, "sleep", AsyncMock()) as sleep,
    ):
        await telegram_bot.ensure_telegram_commands()

    assert bot.set_my_commands.await_count == 8
    sleep.assert_awaited_once()
    assert len(_menus(bot)) == 7


async def test_a_menu_that_cannot_be_set_is_an_error_not_a_crash() -> None:
    bot = MagicMock(set_my_commands=AsyncMock(side_effect=RuntimeError("telegram down")))

    with (
        patch.object(telegram_bot, "_bot", bot),
        patch.object(telegram_bot, "logger") as logger,
    ):
        await telegram_bot.ensure_telegram_commands()

    assert logger.error.call_args.args[0] == "telegram_commands_setup_failed"


async def test_no_bot_sets_no_menu() -> None:
    with patch.object(telegram_bot, "_bot", None), patch.object(telegram_bot, "logger") as logger:
        await telegram_bot.ensure_telegram_commands()

    assert logger.info.call_args.args[0] == "telegram_commands_setup_skipped"


@pytest.mark.parametrize("webhook_url", ["https://e.test/hook", None], ids=["webhook", "polling"])
def test_the_leader_sets_the_menu_in_both_modes(
    webhook_url: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "channels_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "123:abc")
    monkeypatch.setattr(settings, "telegram_webhook_url", webhook_url)
    scheduler = MagicMock()

    schedulers.register_telegram_setup(scheduler)

    jobs = {call.kwargs["id"]: call for call in scheduler.add_job.call_args_list}
    assert jobs[SCHEDULER_JOB_TELEGRAM_COMMANDS].args == (telegram_bot.ensure_telegram_commands,)
    assert jobs[SCHEDULER_JOB_TELEGRAM_COMMANDS].kwargs["trigger"] == "date"
    assert (SCHEDULER_JOB_TELEGRAM_WEBHOOK in jobs) == (webhook_url is not None)


@pytest.mark.parametrize(
    ("enabled", "token"), [(False, "123:abc"), (True, None)], ids=["no_channels", "no_bot"]
)
def test_an_instance_without_a_bot_schedules_nothing(
    enabled: bool, token: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "channels_enabled", enabled)
    monkeypatch.setattr(settings, "telegram_bot_token", token)
    monkeypatch.setattr(settings, "telegram_webhook_url", "https://e.test/hook")
    scheduler = MagicMock()

    schedulers.register_telegram_setup(scheduler)

    scheduler.add_job.assert_not_called()
