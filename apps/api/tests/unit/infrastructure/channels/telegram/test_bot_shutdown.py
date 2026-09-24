"""Tests for the Telegram bot shutdown path.

Regression: on every dev restart the shutdown logged an ERROR with a traceback
("This Application is not running!") because `Application.stop()` was called
unconditionally — in webhook mode the application is never started.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.channels.telegram import bot as telegram_bot


def _application(running: bool) -> MagicMock:
    app = MagicMock()
    app.running = running
    app.updater = None
    app.stop = AsyncMock()
    app.shutdown = AsyncMock()
    return app


@pytest.mark.unit
class TestShutdownTelegramBot:
    async def test_stop_skipped_when_application_not_running(self) -> None:
        app = _application(running=False)
        bot = MagicMock()
        bot.delete_webhook = AsyncMock()

        with (
            patch.object(telegram_bot, "_application", app),
            patch.object(telegram_bot, "_bot", bot),
            patch.object(telegram_bot, "settings") as mock_settings,
            patch.object(telegram_bot, "logger") as mock_logger,
        ):
            mock_settings.telegram_webhook_url = "https://example.test/hook"
            await telegram_bot.shutdown_telegram_bot()

        app.stop.assert_not_awaited()
        app.shutdown.assert_awaited_once()
        mock_logger.error.assert_not_called()

    async def test_stop_called_when_running(self) -> None:
        app = _application(running=True)
        bot = MagicMock()
        bot.delete_webhook = AsyncMock()

        with (
            patch.object(telegram_bot, "_application", app),
            patch.object(telegram_bot, "_bot", bot),
            patch.object(telegram_bot, "settings") as mock_settings,
            patch.object(telegram_bot, "logger") as mock_logger,
        ):
            mock_settings.telegram_webhook_url = "https://example.test/hook"
            await telegram_bot.shutdown_telegram_bot()

        app.stop.assert_awaited_once()
        app.shutdown.assert_awaited_once()
        mock_logger.error.assert_not_called()


@pytest.mark.unit
class TestTheWebhookIsBotGlobal:
    """ADR-304: one setWebhook for all workers, set by the leader, never deleted by one."""

    async def test_shutdown_leaves_the_webhook_in_place(self) -> None:
        """A stopping worker (one of N, or a deploy's old container) used to
        delete the webhook every other worker was serving on."""
        app = _application(running=False)
        bot = MagicMock()
        bot.delete_webhook = AsyncMock()

        with (
            patch.object(telegram_bot, "_application", app),
            patch.object(telegram_bot, "_bot", bot),
            patch.object(telegram_bot, "settings") as mock_settings,
        ):
            mock_settings.telegram_webhook_url = "https://example.test/hook"
            await telegram_bot.shutdown_telegram_bot()

        bot.delete_webhook.assert_not_awaited()

    async def test_the_leader_job_sets_the_webhook_once_with_its_secret(self) -> None:
        bot = MagicMock()
        bot.set_webhook = AsyncMock()

        with (
            patch.object(telegram_bot, "_bot", bot),
            patch.object(telegram_bot, "settings") as mock_settings,
        ):
            mock_settings.telegram_webhook_url = "https://example.test/hook"
            mock_settings.telegram_webhook_secret = "s" * 32
            await telegram_bot.ensure_telegram_webhook()

        bot.set_webhook.assert_awaited_once_with(
            url="https://example.test/hook",
            secret_token="s" * 32,
            allowed_updates=["message", "callback_query"],
        )

    async def test_a_flood_limit_is_waited_out_once(self) -> None:
        from telegram.error import RetryAfter

        bot = MagicMock()
        bot.set_webhook = AsyncMock(side_effect=[RetryAfter(1), None])

        with (
            patch.object(telegram_bot, "_bot", bot),
            patch.object(telegram_bot, "settings") as mock_settings,
            patch.object(telegram_bot.asyncio, "sleep", AsyncMock()) as sleep,
        ):
            mock_settings.telegram_webhook_url = "https://example.test/hook"
            mock_settings.telegram_webhook_secret = None
            await telegram_bot.ensure_telegram_webhook()

        assert bot.set_webhook.await_count == 2
        sleep.assert_awaited_once()

    async def test_a_webhook_that_cannot_be_set_is_an_error_not_a_crash(self) -> None:
        bot = MagicMock()
        bot.set_webhook = AsyncMock(side_effect=RuntimeError("telegram down"))

        with (
            patch.object(telegram_bot, "_bot", bot),
            patch.object(telegram_bot, "settings") as mock_settings,
            patch.object(telegram_bot, "logger") as mock_logger,
        ):
            mock_settings.telegram_webhook_url = "https://example.test/hook"
            mock_settings.telegram_webhook_secret = None
            await telegram_bot.ensure_telegram_webhook()

        assert mock_logger.error.call_args.args[0] == "telegram_webhook_setup_failed"

    async def test_polling_mode_sets_no_webhook(self) -> None:
        bot = MagicMock()
        bot.set_webhook = AsyncMock()

        with (
            patch.object(telegram_bot, "_bot", bot),
            patch.object(telegram_bot, "settings") as mock_settings,
        ):
            mock_settings.telegram_webhook_url = None
            await telegram_bot.ensure_telegram_webhook()

        bot.set_webhook.assert_not_awaited()

    async def test_a_worker_boot_builds_the_bot_without_setting_the_webhook(self) -> None:
        """N workers setting it together answered « Conflict: terminated by
        other setWebhook » at every deploy (production, 2026-09-22)."""
        application = MagicMock()
        application.bot.set_webhook = AsyncMock()
        application.bot.get_me = AsyncMock(return_value=MagicMock(username="lia_bot", id=1))
        builder = MagicMock()
        builder.token.return_value.build.return_value = application

        with (
            patch.object(telegram_bot, "settings") as mock_settings,
            patch.object(telegram_bot.Application, "builder", return_value=builder),
            # The module globals the boot assigns are restored after the test.
            patch.object(telegram_bot, "_bot", None),
            patch.object(telegram_bot, "_application", None),
            patch.object(telegram_bot, "_bot_username", None),
        ):
            mock_settings.channels_enabled = True
            mock_settings.telegram_bot_token = "123:abc"
            mock_settings.telegram_webhook_url = "https://example.test/hook"
            mock_settings.telegram_webhook_secret = "s" * 32
            bot = await telegram_bot.initialize_telegram_bot()

        assert bot is application.bot
        application.bot.set_webhook.assert_not_awaited()
