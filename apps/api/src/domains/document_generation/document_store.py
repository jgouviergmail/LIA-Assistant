"""Module-level store for generated document metadata pending delivery (ADR-226).

Mirror of ``image_generation/image_store.py``: the generate_document tool saves
the file via AttachmentRepository and stores the attachment URL here; the
streaming layer peeks it for message-metadata archiving and clears it into the
SSE done chunk. ``to_wire_metadata`` is the SINGLE serializer for both sites —
the frontend maps both through one ``GeneratedDocument`` type, so a field
present on one path only cannot exist (the GeneratedImage lesson).
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PendingDocument:
    """A generated document pending SSE injection.

    Attributes:
        url: Relative attachment URL (``/api/v1/attachments/{id}``).
        filename: Human-meaningful download filename (sanitized stem + ext).
        doc_type: DocumentType value ("csv", "xlsx", ...).
        size_bytes: Rendered file size.
        expires_at: ISO-8601 UTC purge deadline, ``None`` when unknown —
            the UI then says nothing rather than guess (N2 rule).
    """

    url: str
    filename: str
    doc_type: str
    size_bytes: int
    expires_at: str | None = None


# Module-level store: conversation_id -> list of PendingDocument
_pending_documents: dict[str, list[PendingDocument]] = {}
_lock = threading.Lock()


def store_pending_document(conversation_id: str, document: PendingDocument) -> None:
    """Queue a generated document for delivery to the frontend.

    Args:
        conversation_id: Conversation thread_id (from configurable).
        document: The pending document card payload.
    """
    with _lock:
        _pending_documents.setdefault(conversation_id, []).append(document)
    # Filename is user content: counts and types at INFO, name at DEBUG.
    logger.info(
        "pending_document_stored",
        conversation_id=conversation_id,
        doc_type=document.doc_type,
        size_bytes=document.size_bytes,
    )
    logger.debug("pending_document_filename", filename=document.filename)


def peek_pending_documents(conversation_id: str) -> list[PendingDocument]:
    """Read pending documents without clearing (message-metadata archiving).

    Args:
        conversation_id: Conversation thread_id.

    Returns:
        List of PendingDocument (empty if none pending).
    """
    with _lock:
        return list(_pending_documents.get(conversation_id, []))


def get_and_clear_pending_documents(conversation_id: str) -> list[PendingDocument]:
    """Retrieve and clear pending documents (SSE done chunk).

    Args:
        conversation_id: Conversation thread_id.

    Returns:
        List of PendingDocument (empty if none pending).
    """
    with _lock:
        documents = _pending_documents.pop(conversation_id, [])
    if documents:
        logger.info(
            "pending_documents_retrieved",
            conversation_id=conversation_id,
            count=len(documents),
        )
    return documents


def to_wire_metadata(
    documents: Sequence[PendingDocument],
) -> list[dict[str, str | int | None]]:
    """Serialize for the client — SAME shape on the done chunk and the archive.

    Args:
        documents: Pending documents, as peeked or cleared from the store.

    Returns:
        One JSON-serializable dict per document, in order.
    """
    return [
        {
            "url": document.url,
            "filename": document.filename,
            "doc_type": document.doc_type,
            "size_bytes": document.size_bytes,
            "expires_at": document.expires_at,
        }
        for document in documents
    ]
