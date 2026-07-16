"""RAGDocumentStatus.PENDING + terminal-status helper (audit F001, Phase 1 T0).

PENDING is the created-but-unclaimed state of an upload/processing work unit.
It must be distinct from the existing statuses and must NOT be treated as
terminal (a PENDING document is still in progress, not ready and not failed).
"""

from __future__ import annotations

from src.domains.rag_spaces.models import (
    RAGDocumentStatus,
    is_terminal_document_status,
)


def test_pending_status_exists_and_is_distinct() -> None:
    assert RAGDocumentStatus.PENDING == "pending"
    assert RAGDocumentStatus.PENDING not in (
        RAGDocumentStatus.PROCESSING,
        RAGDocumentStatus.READY,
        RAGDocumentStatus.ERROR,
        RAGDocumentStatus.REINDEXING,
    )


def test_terminal_status_helper() -> None:
    assert is_terminal_document_status(RAGDocumentStatus.READY) is True
    assert is_terminal_document_status(RAGDocumentStatus.ERROR) is True
    assert is_terminal_document_status(RAGDocumentStatus.PENDING) is False
    assert is_terminal_document_status(RAGDocumentStatus.PROCESSING) is False
    assert is_terminal_document_status(RAGDocumentStatus.REINDEXING) is False
