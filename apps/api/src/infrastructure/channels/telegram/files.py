"""Downloading a file a person sent the bot: a voice note, a photo, a document.

ONE door for every file the bot reads (lot 11): the size Telegram declares is
checked before anything is downloaded, the size received after, so a file past
its ceiling is never held in memory beyond it.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from telegram import Bot

logger = get_logger(__name__)


async def download_file(bot: Bot, file_id: str, *, max_bytes: int) -> bytes | None:
    """Download one file from Telegram, within ``max_bytes``.

    Args:
        bot: The Telegram bot.
        file_id: Telegram's handle to the file.
        max_bytes: The most a caller accepts.

    Returns:
        The file's bytes, or None when it is larger than accepted or could not
        be downloaded.
    """
    try:
        tg_file = await bot.get_file(file_id)
        if tg_file.file_size and tg_file.file_size > max_bytes:
            logger.warning(
                "telegram_file_too_large",
                file_id=file_id[:12],
                file_size=tg_file.file_size,
                max_size=max_bytes,
            )
            return None

        buffer = BytesIO()
        await tg_file.download_to_memory(buffer)
        content = buffer.getvalue()
        if len(content) > max_bytes:
            logger.warning(
                "telegram_file_download_exceeded_limit",
                file_id=file_id[:12],
                actual_size=len(content),
                max_size=max_bytes,
            )
            return None

        logger.debug("telegram_file_downloaded", file_id=file_id[:12], size_bytes=len(content))
        return content

    except Exception:
        logger.error("telegram_file_download_failed", file_id=file_id[:12], exc_info=True)
        return None
