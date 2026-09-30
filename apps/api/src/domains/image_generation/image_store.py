"""Module-level store for generated image URLs pending delivery to frontend.

Stores lightweight attachment URLs (NOT base64 data) keyed by conversation_id.
The generate_image tool saves the image via AttachmentService and stores the
URL here. The streaming layer includes them in the done chunk metadata so the
frontend renders them as image cards below the assistant message.

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.domains.shared.pending_cards import PendingCards
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: The message-metadata key the chat reads image cards from — on the done chunk,
#: on the archived row, and on a shared image's notification (ADR-316).
GENERATED_IMAGES_METADATA_KEY = "generated_images"


@dataclass
class PendingImage:
    """A generated image pending SSE injection.

    Attributes:
        url: Relative URL to the attachment endpoint (e.g., "/api/v1/attachments/{id}").
        alt_text: Sanitized alt text for the markdown img tag.
        expires_at: ISO-8601 UTC instant after which the cleanup scheduler
            deletes the attachment (``attachments_ttl_hours``, purged every 6 h).
            Surfaced to the frontend so the user can save the image BEFORE it
            disappears — it used to vanish silently. ``None`` when the caller
            does not know the deadline; the UI then says nothing rather than
            guess a duration.
        kept: The person kept the file from the gallery (ADR-319): it has no
            deadline, and the card says so. The history read path restates
            the same flag from the file's row, so the card reads the same
            live and after a reload.
    """

    url: str
    alt_text: str
    expires_at: str | None = None
    kept: bool = False


# Module-level store: conversation_id → list of PendingImage
_pending_images: PendingCards[PendingImage] = PendingCards(GENERATED_IMAGES_METADATA_KEY)


def sanitize_alt_text(text: str) -> str:
    """Remove markdown-breaking characters from a generated image's label.

    Public since ADR-279: the gallery's title and the chat card's alt text
    are the same string, and a second sanitiser is how they come to differ.

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


def store_pending_image(
    conversation_id: str,
    url: str,
    alt_text: str,
    expires_at: str | None = None,
    kept: bool = False,
) -> None:
    """Store a generated image URL for later SSE injection.

    Called by the generate_image tool after saving the image as an Attachment.

    Args:
        conversation_id: Conversation thread_id (from configurable).
        url: Relative URL (e.g., "/api/v1/attachments/{id}").
        alt_text: Raw prompt text (sanitized internally).
        expires_at: ISO-8601 UTC deadline after which the attachment is purged.
        kept: The person kept the file (ADR-319) — it then has no deadline.
    """
    sanitized_alt = sanitize_alt_text(alt_text)
    image = PendingImage(url=url, alt_text=sanitized_alt, expires_at=expires_at, kept=kept)

    _pending_images.add(conversation_id, image)

    logger.info(
        "pending_image_stored",
        conversation_id=conversation_id,
        url=url,
        alt_length=len(sanitized_alt),
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
    return _pending_images.peek(conversation_id)


def get_and_clear_pending_images(conversation_id: str) -> list[PendingImage]:
    """Retrieve and clear all pending image URLs for a conversation.

    Called by the streaming layer after LLM response tokens to inject
    image markdown before the done chunk.

    Args:
        conversation_id: Conversation thread_id.

    Returns:
        List of PendingImage (empty if none pending).
    """
    images = _pending_images.take(conversation_id)

    if images:
        logger.info(
            "pending_images_retrieved",
            conversation_id=conversation_id,
            count=len(images),
        )

    return images


def to_wire_metadata(images: Sequence[PendingImage]) -> list[dict[str, str | bool | None]]:
    """Serialize pending images for the client.

    The SSE ``done`` chunk and the archived ``message_metadata`` row must carry
    the SAME shape: the frontend maps both through one ``GeneratedImage`` type,
    and a field present on one path only produces a card that behaves
    differently live and after a reload. Building it here — next to the
    dataclass — is what keeps the two emission sites from drifting; they used to
    each spell the dict out by hand.

    Args:
        images: Pending images, as peeked or cleared from the store.

    Returns:
        One JSON-serializable dict per image, in order.
    """
    return [
        {
            "url": image.url,
            "alt": image.alt_text,
            "expires_at": image.expires_at,
            "kept": image.kept,
        }
        for image in images
    ]
