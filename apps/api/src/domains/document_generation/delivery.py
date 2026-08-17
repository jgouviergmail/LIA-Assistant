"""Delivery adapters: pending documents -> chat metadata dicts (ADR-226).

The streaming layer (``agents/api/service.py``) is a frozen-size, maximum-CC
hotspot: these helpers keep its two document touch points to ONE branchless
call each. Flag check, peek/clear choice, serialization and the empty case all
live here — behind the single ``to_wire_metadata`` serializer, so the archived
card and the live card can never drift.
"""

from __future__ import annotations

from typing import Any

from src.core.config import settings
from src.domains.document_generation.document_store import (
    get_and_clear_pending_documents,
    peek_pending_documents,
    to_wire_metadata,
)

_METADATA_KEY = "generated_documents"


def attach_archived_documents(metadata: dict[str, Any], conversation_id: str) -> None:
    """Copy pending document cards into archived message metadata (peek — the
    done chunk below still needs them).

    No-op when the feature is disabled or nothing is pending.

    Args:
        metadata: The assistant message metadata dict (mutated in place).
        conversation_id: Conversation thread_id.
    """
    if not getattr(settings, "document_generation_enabled", False):
        return
    pending = peek_pending_documents(conversation_id)
    if pending:
        metadata[_METADATA_KEY] = to_wire_metadata(pending)


def attach_done_documents(metadata: dict[str, Any], conversation_id: str) -> None:
    """Move pending document cards into the SSE done-chunk metadata (clears).

    No-op when the feature is disabled or nothing is pending.

    Args:
        metadata: The done-chunk metadata dict (mutated in place).
        conversation_id: Conversation thread_id.
    """
    if not getattr(settings, "document_generation_enabled", False):
        return
    pending = get_and_clear_pending_documents(conversation_id)
    if pending:
        metadata[_METADATA_KEY] = to_wire_metadata(pending)
