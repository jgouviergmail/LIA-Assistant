"""A queued document card is delivered WHOEVER queued it (ADR-318).

The delivery helpers returned early while ``document_generation_enabled`` was
off, because the generator was the only producer. The generated-files lookup
queues document cards too — a file kept from before generation was switched
off — and a card queued behind a closed gate is never shown and never freed.
The serialization itself is pinned by ``test_delivery_wire``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.document_generation.delivery import (
    attach_archived_documents,
    attach_done_documents,
)
from src.domains.document_generation.document_store import (
    PendingDocument,
    get_and_clear_pending_documents,
    store_pending_document,
)

pytestmark = pytest.mark.unit

_KEY = "generated_documents"


@pytest.fixture
def conversation() -> Iterator[str]:
    key = str(uuid.uuid4())
    yield key
    get_and_clear_pending_documents(key)


def _document() -> PendingDocument:
    return PendingDocument(
        url="/api/v1/attachments/report",
        filename="Quarterly report.pdf",
        doc_type="pdf",
        size_bytes=2048,
        expires_at="2026-09-26T08:00:00+00:00",
    )


class TestTheCardIsDelivered:
    def test_whatever_the_generation_flag(self, conversation: str) -> None:
        archived: dict[str, Any] = {}
        done: dict[str, Any] = {}
        with patch("src.core.config.settings.document_generation_enabled", False):
            store_pending_document(conversation, _document())
            attach_archived_documents(archived, conversation)
            attach_done_documents(done, conversation)

        assert [card["filename"] for card in done[_KEY]] == ["Quarterly report.pdf"]
        assert archived[_KEY] == done[_KEY]

    def test_the_done_chunk_frees_the_queue(self, conversation: str) -> None:
        store_pending_document(conversation, _document())
        attach_done_documents({}, conversation)
        again: dict[str, Any] = {}

        attach_done_documents(again, conversation)

        assert again == {}

    def test_nothing_pending_adds_nothing(self, conversation: str) -> None:
        metadata: dict[str, Any] = {}

        attach_archived_documents(metadata, conversation)
        attach_done_documents(metadata, conversation)

        assert metadata == {}
