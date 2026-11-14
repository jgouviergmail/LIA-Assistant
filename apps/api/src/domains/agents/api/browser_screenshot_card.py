"""The turn's last browser screenshot, published as a durable file for its card.

The browser tools keep the latest capture of a turn in memory. Before the
answer is archived, the streaming layer turns it into a file the card can name
after a reload. It goes through the SAME publication as every generated file
(``publish_generated_files``): the row is committed before any byte is written,
the write runs off the event loop and is joined, and a turn whose authority was
revoked publishes nothing.
"""

from __future__ import annotations

import uuid

import structlog

from src.core.config import settings
from src.core.conversation_execution import ExecutionRevoked
from src.domains.agents.tools.browser_screenshot_store import get_and_clear_last_screenshot
from src.domains.attachments.file_contracts import UploadMetadata
from src.domains.attachments.generated_publication import publish_generated_files
from src.domains.attachments.models import AttachmentContentType, AttachmentOrigin
from src.domains.attachments.urls import attachment_url
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

_JPEG_MIME_TYPE = "image/jpeg"
_JPEG_SUFFIX = ".jpg"
# Read by the browser's image element only; the card's visible label is the
# frontend's own translation.
_CARD_ALT = "Browser screenshot"


async def publish_browser_screenshot_card(
    *, user_id: uuid.UUID, conversation_id: uuid.UUID, runtime_id: str, run_id: str
) -> dict[str, str] | None:
    """Publish the turn's last browser screenshot and describe its card.

    Args:
        user_id: The account the turn runs for; it owns the file.
        conversation_id: The discussion the turn belongs to.
        runtime_id: The runtime the browser tools queued the capture under.
        run_id: The turn, for the log line.

    Returns:
        The card (``url``, ``alt``), or ``None`` when the feature is off, the
        turn captured nothing, or the save failed: a lost screenshot costs the
        card, never the answer.

    Raises:
        ExecutionRevoked: The turn lost its authority; nothing was published.
    """
    if not settings.browser_progressive_screenshots:
        return None
    jpeg = get_and_clear_last_screenshot(runtime_id)
    if not jpeg:
        return None
    try:
        async with get_db_context() as db:
            attachment = (
                await publish_generated_files(
                    db,
                    owner_id=user_id,
                    files=[
                        (
                            UploadMetadata(
                                filename=f"browser_{uuid.uuid4()}{_JPEG_SUFFIX}",
                                mime_type=_JPEG_MIME_TYPE,
                                content_type=AttachmentContentType.IMAGE,
                                suffix=_JPEG_SUFFIX,
                                origin=AttachmentOrigin.BROWSER_SCREENSHOT,
                                conversation_id=conversation_id,
                            ),
                            jpeg,
                        )
                    ],
                )
            )[0]
            attachment_id = str(attachment.id)
    except ExecutionRevoked:
        raise
    except Exception as error:  # noqa: BLE001 — the card is optional, the answer is not
        logger.warning(
            "browser_screenshot_card_save_failed",
            run_id=run_id,
            error_type=type(error).__name__,
        )
        return None
    logger.debug("browser_screenshot_card_saved", run_id=run_id, attachment_id=attachment_id)
    return {"url": attachment_url(attachment_id), "alt": _CARD_ALT}
