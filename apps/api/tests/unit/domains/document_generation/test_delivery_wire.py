"""Archive and done-chunk carry the identical generated_documents shape (ADR-226).

The archive path serializes via ``peek`` + ``to_wire_metadata`` and the done
chunk via ``get_and_clear`` + ``to_wire_metadata``: one serializer, so a field
added on one path only cannot exist (the GeneratedImage lesson — the
``expires_at`` drift between the two emission sites, chat.ts:28-33).
"""

import pytest

from src.domains.document_generation.document_store import (
    PendingDocument,
    get_and_clear_pending_documents,
    peek_pending_documents,
    store_pending_document,
    to_wire_metadata,
)


@pytest.mark.unit
def test_peek_then_clear_serialize_identically() -> None:
    document = PendingDocument(
        url="/api/v1/attachments/y",
        filename="rapport.pdf",
        doc_type="pdf",
        size_bytes=1234,
        expires_at="2026-08-19T00:00:00+00:00",
    )
    store_pending_document("conv-wire", document)
    archived = to_wire_metadata(peek_pending_documents("conv-wire"))
    live = to_wire_metadata(get_and_clear_pending_documents("conv-wire"))
    assert archived == live
    # And the shape is exactly what the frontend GeneratedDocument type reads.
    assert set(archived[0]) == {"url", "filename", "doc_type", "size_bytes", "expires_at"}
