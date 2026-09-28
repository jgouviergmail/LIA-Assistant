"""New documents in the listener's spaces: recent ones, in the spaces they made."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.domains.radio.facts import FactKind
from src.domains.radio.readers.spaces import document_drafts, new_documents

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=3)


@dataclass
class Space:
    name: str
    kind: str | None = None


@dataclass
class Document:
    id: UUID
    original_filename: str
    created_at: datetime
    space: Space


def test_only_recent_documents_of_the_spaces_the_person_made() -> None:
    documents = new_documents(
        [
            Document(UUID(int=1), "Lease.pdf", NOW - timedelta(days=1), Space("Home")),
            Document(
                UUID(int=2), "Minutes.md", NOW - timedelta(hours=5), Space("Meetings", "meetings")
            ),
            Document(UUID(int=3), "Old.pdf", NOW - timedelta(days=10), Space("Home")),
        ],
        since=SINCE,
    )
    [draft] = document_drafts(documents, tz=UTC)
    assert draft.text == (
        'New in the knowledge space "Home": "Lease.pdf", added on Friday 2026-09-25, 07:00'
    )
    assert draft.kind is FactKind.SPACE
