"""
Telegram bot lifecycle management.

Handles bot initialization, webhook setup (production) or long polling (dev),
and graceful shutdown.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import asyncio

from telegram import Bot, BotCommand
from telegram.ext import Application

from src.core.config import settings
from src.infrastructure.channels.telegram.flood_control import retry_after_seconds
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
        Builds the bot only: the webhook itself is set by the scheduler
        leader (:func:`ensure_telegram_webhook`), once for all workers.

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
        # Production: the webhook is bot-GLOBAL state, so it is set ONCE — by
        # the scheduler leader (``ensure_telegram_webhook``, a one-shot job) —
        # never by every worker at boot: N workers calling setWebhook together
        # answered « Conflict: terminated by other setWebhook » and RetryAfter
        # floods at every deploy (measured in production, 2026-09-22). Every
        # worker still holds the bot: it sends, and the webhook route receives.
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


async def ensure_telegram_webhook() -> None:
    """Set the bot's webhook — run by the scheduler leader alone (ADR-304).

    A one-shot job every newly elected leader runs: the webhook is bot-global,
    so one call serves every worker, a failover re-asserts it, and a rotated
    secret reaches Telegram at the next boot. Telegram replaces a webhook set
    to the same URL, so a re-run is harmless. A flood-limit left by a previous
    deploy is waited out once; a webhook that could not be set is an ERROR —
    Telegram delivers nothing until it is.
    """
    from telegram.error import RetryAfter

    webhook_url = getattr(settings, "telegram_webhook_url", None)
    if _bot is None or not webhook_url:
        logger.info(
            "telegram_webhook_setup_skipped",
            reason="no_bot" if _bot is None else "polling_mode",
        )
        return
    webhook = {
        "url": webhook_url,
        "secret_token": getattr(settings, "telegram_webhook_secret", None),
        "allowed_updates": ["message", "callback_query"],
    }
    try:
        try:
            await _bot.set_webhook(**webhook)
        except RetryAfter as exc:
            await asyncio.sleep(retry_after_seconds(exc) + 0.5)
            await _bot.set_webhook(**webhook)
    except Exception as exc:
        logger.error(
            "telegram_webhook_setup_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return
    logger.info("telegram_webhook_set", webhook_url=webhook_url)


#: LIA's languages as Telegram names them (``setMyCommands`` takes a two-letter
#: ISO 639-1 code): mapped at the provider boundary, every canonical code listed.
_TELEGRAM_LANGUAGE_CODES: dict[str, str] = {
    "fr": "fr",
    "en": "en",
    "es": "es",
    "de": "de",
    "it": "it",
    "zh-CN": "zh",
}


#: What the menu lists, in order — each one a command the bot answers itself
#: (``domains/channels/commands.ChannelCommand``; ``test_commands`` holds them
#: together). ``/start`` is Telegram's own first gesture and needs no line.
MENU_COMMANDS: tuple[str, ...] = ("stop", "help")


def _menu(language: str) -> list[BotCommand]:
    """The command menu, its descriptions in ``language``."""
    from src.infrastructure.channels.telegram.formatter import get_bot_message

    return [
        BotCommand(command, get_bot_message(f"command_{command}", language))
        for command in MENU_COMMANDS
    ]


async def _set_commands(bot: Bot, language: str, language_code: str | None) -> None:
    """Set one language's menu; a flood-limit is waited out once."""
    from telegram.error import RetryAfter

    kwargs = {"commands": _menu(language), "language_code": language_code}
    try:
        await bot.set_my_commands(**kwargs)
    except RetryAfter as exc:
        await asyncio.sleep(retry_after_seconds(exc) + 0.5)
        await bot.set_my_commands(**kwargs)


async def ensure_telegram_commands() -> None:
    """Set the bot's command menu — run by the scheduler leader alone (lot 33).

    Bot-global like the webhook, so one call serves every worker, in webhook
    and polling mode alike: one menu per language LIA speaks, and for every
    other client language the instance's declared one (ADR-323). Re-running it
    replaces the same menus. A menu that could not be set is an ERROR: the
    commands still work, but nobody sees them offered.
    """
    from src.core.i18n import resolve_language

    if _bot is None:
        logger.info("telegram_commands_setup_skipped", reason="no_bot")
        return
    try:
        for language, language_code in _TELEGRAM_LANGUAGE_CODES.items():
            await _set_commands(_bot, language, language_code)
        await _set_commands(_bot, resolve_language(), None)
    except Exception as exc:
        logger.error("telegram_commands_setup_failed", error_type=type(exc).__name__)
        return
    logger.info("telegram_commands_set", languages=len(_TELEGRAM_LANGUAGE_CODES))


async def shutdown_telegram_bot() -> None:
    """
    Gracefully shut down the Telegram bot.

    Stops polling (development), then shuts down the Application. The webhook
    (production) is left in place: it is bot-global, so a worker that stops —
    one of N, or the old container of a deploy — used to delete it for every
    other worker, and Telegram delivered nothing until the next boot set it
    again. While the API is down, Telegram retries its deliveries, and a switch
    back to polling needs no deletion here: python-telegram-bot's polling
    bootstrap removes any webhook itself before its first ``getUpdates``.
    """
    global _bot, _application, _bot_username

    if _bot is None:
        return

    webhook_url = getattr(settings, "telegram_webhook_url", None)

    try:
        if not webhook_url and _application and _application.updater:
            # Development: stop polling
            await _application.updater.stop()
            logger.info("telegram_polling_stopped")

        if _application:
            # `stop()` raises when the application was never started — the
            # webhook path never starts it, so every restart logged an ERROR
            # with a traceback. `shutdown()` is still required either way.
            if _application.running:
                await _application.stop()
            await _application.shutdown()
            logger.info("telegram_application_shutdown")

    except Exception as exc:
        logger.error("telegram_shutdown_error", error=str(exc), exc_info=True)
    finally:
        _bot = None
        _application = None
        _bot_username = None
