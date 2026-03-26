"""Module-level store for generated image URLs pending delivery to frontend.

Stores lightweight attachment URLs (NOT base64 data) keyed by conversation_id.
The generate_image tool saves the image via AttachmentService and stores the
URL here. The streaming layer includes them in the done chunk metadata so the
frontend renders them as image cards below the assistant message.

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

import threading
from dataclasses import dataclass

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PendingImage:
    """A generated image pending SSE injection.

    Attributes:
        url: Relative URL to the attachment endpoint (e.g., "/api/v1/attachments/{id}").
        alt_text: Sanitized alt text for the markdown img tag.
    """

    url: str
    alt_text: str


# Module-level store: conversation_id → list of PendingImage
_pending_images: dict[str, list[PendingImage]] = {}
_lock = threading.Lock()


def _sanitize_alt_text(text: str) -> str:
    """Remove markdown-breaking characters from alt text.

    Args:
        text: Raw prompt text to use as alt.

    Returns:
        Sanitized string safe for markdown ![alt](...) syntax, max 100 chars.
    """
    return (
        text.replace("[", "")
        .replace("]", "")
        .replace("(", "")
        .replace(")", "")
        .replace("\n", " ")[:100]
    )


def store_pending_image(conversation_id: str, url: str, alt_text: str) -> None:
    """Store a generated image URL for later SSE injection.

    Called by the generate_image tool after saving the image as an Attachment.

    Args:
        conversation_id: Conversation thread_id (from configurable).
        url: Relative URL (e.g., "/api/v1/attachments/{id}").
        alt_text: Raw prompt text (sanitized internally).
    """
    sanitized_alt = _sanitize_alt_text(alt_text)
    image = PendingImage(url=url, alt_text=sanitized_alt)

    with _lock:
        _pending_images.setdefault(conversation_id, []).append(image)

    logger.info(
        "pending_image_stored",
        conversation_id=conversation_id,
        url=url,
        alt_text=sanitized_alt,
    )


def peek_pending_images(conversation_id: str) -> list[PendingImage]:
    """Read pending images without removing them.

    Used by message archiving to persist image URLs in message metadata
    before the done chunk clears them via get_and_clear_pending_images.

    Args:
        conversation_id: Conversation thread_id.

    Returns:
        List of PendingImage (empty if none pending).
    """
    with _lock:
        return list(_pending_images.get(conversation_id, []))


def get_and_clear_pending_images(conversation_id: str) -> list[PendingImage]:
    """Retrieve and clear all pending image URLs for a conversation.

    Called by the streaming layer after LLM response tokens to inject
    image markdown before the done chunk.

    Args:
        conversation_id: Conversation thread_id.

    Returns:
        List of PendingImage (empty if none pending).
    """
    with _lock:
        images = _pending_images.pop(conversation_id, [])

    if images:
        logger.info(
            "pending_images_retrieved",
            conversation_id=conversation_id,
            count=len(images),
        )

    return images
