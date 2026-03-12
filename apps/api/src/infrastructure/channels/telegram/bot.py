"""
Telegram bot lifecycle management.

Handles bot initialization, webhook setup (production) or long polling (dev),
and graceful shutdown.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

from telegram import Bot
from telegram.ext import Application

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Module-level singletons
_bot: Bot | None = None
_application: Application | None = None
_bot_username: str | None = None


def get_bot() -> Bot | None:
    """Get the initialized Telegram Bot instance (or None if not initialized)."""
    return _bot


def get_bot_username() -> str | None:
    """Get the bot @username discovered via getMe at startup."""
    return _bot_username


def get_application() -> Application | None:
    """Get the initialized Telegram Application instance (or None)."""
    return _application


async def initialize_telegram_bot() -> Bot | None:
    """
    Initialize the Telegram bot and configure webhook or polling.

    Production (TELEGRAM_WEBHOOK_URL set):
        Sets the webhook URL with secret token for signature verification.

    Development (no TELEGRAM_WEBHOOK_URL):
        Starts long polling via python-telegram-bot's Application updater,
        integrated into the FastAPI event loop.

    Returns:
        Bot instance if initialized, None if channels/telegram not configured.
    """
    global _bot, _application, _bot_username

    if not getattr(settings, "channels_enabled", False):
        logger.debug("telegram_bot_skipped_channels_disabled")
        return None

    token = getattr(settings, "telegram_bot_token", None)
    if not token:
        logger.warning("telegram_bot_skipped_no_token")
        return None

    webhook_url = getattr(settings, "telegram_webhook_url", None)
    webhook_secret = getattr(settings, "telegram_webhook_secret", None)

    # Build the Application (required for long polling, useful for webhook too)
    _application = Application.builder().token(token).build()
    _bot = _application.bot

    if webhook_url:
        # Production: set webhook with secret token
        await _bot.set_webhook(
            url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
        logger.info(
            "telegram_bot_initialized_webhook",
            webhook_url=webhook_url,
            has_secret=webhook_secret is not None,
        )
    else:
        # Development: long polling
        # Register handlers that bridge updates to our processing pipeline.
        # In webhook mode, FastAPI receives the HTTP POST directly; in polling
        # mode, python-telegram-bot receives updates and dispatches to handlers.
        from telegram import Update
        from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

        async def _polling_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """Bridge long polling updates to the channel processing pipeline."""
            if update:
                from src.domains.channels.router import process_telegram_update

                await process_telegram_update(update.to_dict())

        _application.add_handler(MessageHandler(filters.ALL, _polling_handler))
        _application.add_handler(CallbackQueryHandler(_polling_handler))

        await _application.initialize()
        await _application.start()
        await _application.updater.start_polling(
            allowed_updates=["message", "callback_query"],
        )
        logger.info("telegram_bot_initialized_polling")

    bot_info = await _bot.get_me()
    _bot_username = bot_info.username
    logger.info(
        "telegram_bot_ready",
        bot_username=_bot_username,
        bot_id=bot_info.id,
    )

    return _bot


async def shutdown_telegram_bot() -> None:
    """
    Gracefully shut down the Telegram bot.

    Deletes webhook (production) or stops polling (development),
    then shuts down the Application.
    """
    global _bot, _application, _bot_username

    if _bot is None:
        return

    webhook_url = getattr(settings, "telegram_webhook_url", None)

    try:
        if webhook_url:
            # Production: delete webhook
            await _bot.delete_webhook()
            logger.info("telegram_webhook_deleted")
        elif _application and _application.updater:
            # Development: stop polling
            await _application.updater.stop()
            logger.info("telegram_polling_stopped")

        if _application:
            await _application.stop()
            await _application.shutdown()
            logger.info("telegram_application_shutdown")

    except Exception as exc:
        logger.error("telegram_shutdown_error", error=str(exc), exc_info=True)
    finally:
        _bot = None
        _application = None
        _bot_username = None
