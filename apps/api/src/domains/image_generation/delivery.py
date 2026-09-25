"""Delivery adapters: pending image cards -> chat metadata dicts.

The mirror of ``document_generation/delivery.py``. The streaming layer
(``agents/api/service.py``) is a frozen-size, maximum-CC hotspot: these helpers
keep its two image touch points to ONE branchless call each, behind the single
``to_wire_metadata`` serializer, so the archived card and the live card cannot
drift.

A queued card is delivered WHOEVER queued it. Until ADR-318 both touch points
sat behind ``image_generation_enabled`` because the image tool was the only
producer; the generated-files lookup queues images too — a browser screenshot,
a file kept from before generation was switched off — and a card queued behind
a closed gate is never shown and never freed.
"""

from __future__ import annotations

from typing import Any

from src.domains.image_generation.image_store import (
    GENERATED_IMAGES_METADATA_KEY,
    get_and_clear_pending_images,
    peek_pending_images,
    to_wire_metadata,
)

__all__ = ["attach_archived_images", "attach_done_images"]


def attach_archived_images(metadata: dict[str, Any], conversation_id: str) -> None:
    """Copy pending image cards into archived message metadata (peek — the done
    chunk below still needs them), so they survive a page reload.

    No-op when nothing is pending.

    Args:
        metadata: The assistant message metadata dict (mutated in place).
        conversation_id: Conversation thread_id.
    """
    pending = peek_pending_images(conversation_id)
    if pending:
        metadata[GENERATED_IMAGES_METADATA_KEY] = to_wire_metadata(pending)


def attach_done_images(metadata: dict[str, Any], conversation_id: str) -> None:
    """Move pending image cards into the SSE done-chunk metadata (clears).

    No-op when nothing is pending.

    Args:
        metadata: The done-chunk metadata dict (mutated in place).
        conversation_id: Conversation thread_id.
    """
    pending = get_and_clear_pending_images(conversation_id)
    if pending:
        metadata[GENERATED_IMAGES_METADATA_KEY] = to_wire_metadata(pending)
