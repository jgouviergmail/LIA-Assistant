"""Pending document store: thread-safe FIFO per conversation, one wire shape (ADR-226)."""

import pytest

from src.domains.document_generation.document_store import (
    PendingDocument,
    get_and_clear_pending_documents,
    peek_pending_documents,
    store_pending_document,
    to_wire_metadata,
)


def _doc(name: str = "a.csv") -> PendingDocument:
    return PendingDocument(
        url="/api/v1/attachments/x",
        filename=name,
        doc_type="csv",
        size_bytes=42,
        expires_at="2026-08-19T00:00:00+00:00",
    )


@pytest.mark.unit
class TestDocumentStore:
    """Peek/clear semantics mirror image_store; conversations stay isolated."""

    def test_peek_does_not_clear_and_clear_clears(self) -> None:
        store_pending_document("conv1", _doc())
        store_pending_document("conv1", _doc("b.pdf"))
        assert [d.filename for d in peek_pending_documents("conv1")] == ["a.csv", "b.pdf"]
        cleared = get_and_clear_pending_documents("conv1")
        assert len(cleared) == 2
        assert peek_pending_documents("conv1") == []
        assert get_and_clear_pending_documents("conv1") == []

    def test_wire_metadata_shape(self) -> None:
        wire = to_wire_metadata([_doc()])
        assert wire == [
            {
                "url": "/api/v1/attachments/x",
                "filename": "a.csv",
                "doc_type": "csv",
                "size_bytes": 42,
                "expires_at": "2026-08-19T00:00:00+00:00",
            }
        ]

    def test_unknown_expiry_serializes_as_none(self) -> None:
        doc = PendingDocument(url="/u", filename="f.txt", doc_type="txt", size_bytes=1)
        assert to_wire_metadata([doc])[0]["expires_at"] is None

    def test_conversations_are_isolated(self) -> None:
        store_pending_document("conv-a", _doc())
        assert peek_pending_documents("conv-b") == []
        get_and_clear_pending_documents("conv-a")
