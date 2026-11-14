"""Module-level store for the last browser screenshot pending card delivery.

Stores the last JPEG bytes keyed by conversation_id. The browser tools update
this store on every action via _emit_progressive_screenshot. The streaming layer
saves the last screenshot as an Attachment and includes the URL in done metadata
so the frontend renders it as a card below the assistant message.

The shared pending-card store keeps one payload and registers its run's cleanup.

Phase: evolution — Browser Progressive Screenshots
Created: 2026-03-26
"""

from __future__ import annotations

from src.domains.shared.pending_cards import PendingCards
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Module-level store: conversation_id → last JPEG bytes
_last_screenshot: PendingCards[bytes] = PendingCards("browser_screenshot")


def store_last_browser_screenshot(conversation_id: str, jpeg_bytes: bytes) -> None:
    """Store (or replace) the last browser screenshot for a conversation.

    Called by _emit_progressive_screenshot on every browser action.
    Only the LAST screenshot is kept (replaced on each call).

    Args:
        conversation_id: Conversation thread_id (from configurable).
        jpeg_bytes: Full-resolution JPEG bytes (1280x720, quality 80).
    """
    _last_screenshot.replace(conversation_id, jpeg_bytes)


def get_and_clear_last_screenshot(conversation_id: str) -> bytes | None:
    """Retrieve and clear the last browser screenshot for a conversation.

    Called by the streaming layer before the done chunk to save as Attachment.

    Args:
        conversation_id: Conversation thread_id.

    Returns:
        JPEG bytes of the last screenshot, or None if no screenshot was taken.
    """
    queued = _last_screenshot.take(conversation_id)
    data = queued[-1] if queued else None

    if data:
        logger.debug(
            "browser_last_screenshot_retrieved",
            conversation_id=conversation_id,
            size_kb=len(data) // 1024,
        )

    return data
