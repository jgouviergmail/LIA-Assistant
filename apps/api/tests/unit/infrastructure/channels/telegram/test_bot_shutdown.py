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
