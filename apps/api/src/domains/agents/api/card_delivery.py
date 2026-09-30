"""The chat cards an answer carries, delivered through ONE door (ADR-226, ADR-279, ADR-327).

The streaming layer (``agents/api/service.py``) is a frozen-size,
maximum-complexity hotspot. Each card family used to cost it an import and a
call at two sites — the archived row and the done chunk — and a third family
would have cost two more. These two functions are the only touch points: a
new family joins them here and the hotspot does not move.

Every family keeps its own serializer (``to_wire_metadata``, ``to_card``), so
the archived card and the live card can never drift.
"""

from __future__ import annotations

from typing import Any

from src.domains.document_generation.delivery import (
    attach_archived_documents,
    attach_done_documents,
)
from src.domains.image_generation.delivery import attach_archived_images, attach_done_images
from src.domains.skills.proposals import attach_archived_proposals, attach_done_proposals


def attach_archived_cards(metadata: dict[str, Any], conversation_id: str) -> None:
    """Copy every queued card into the archived message (peek: the done chunk needs them).

    Args:
        metadata: The assistant message metadata (mutated in place).
        conversation_id: The conversation's thread id.
    """
    attach_archived_images(metadata, conversation_id)
    attach_archived_documents(metadata, conversation_id)
    attach_archived_proposals(metadata, conversation_id)


def attach_done_cards(metadata: dict[str, Any], conversation_id: str) -> None:
    """Move every queued card into the done chunk (take: the queues are freed).

    Args:
        metadata: The done-chunk metadata (mutated in place).
        conversation_id: The conversation's thread id.
    """
    attach_done_images(metadata, conversation_id)
    attach_done_documents(metadata, conversation_id)
    attach_done_proposals(metadata, conversation_id)
