"""What the bookmark row promises about its projection (part A, 2026-09-16).

The bookmark is the RECORD and its RAG document is a PROJECTION: the row
points at the document while it exists and keeps only the reason there is
none. Losing the document must never lose the bookmark, so the reference is
``SET NULL`` — and a kept answer's document is a source of its own in the
space, so the space can refuse to move or delete it by hand.
"""

from __future__ import annotations

import pytest

from src.core.constants import BOOKMARKS_SPACE_KIND, MEETINGS_SPACE_KIND
from src.domains.bookmarks.models import BookmarkIndexState, MessageBookmark
from src.domains.rag_spaces.models import RAGDocumentSourceType

pytestmark = pytest.mark.unit


def test_the_document_reference_is_set_null_and_optional() -> None:
    column = MessageBookmark.__table__.c.rag_document_id
    assert column.nullable is True
    (foreign_key,) = column.foreign_keys
    assert foreign_key.ondelete == "SET NULL"
    assert foreign_key.target_fullname == "rag_documents.id"


def test_the_index_state_is_a_closed_lowercase_vocabulary() -> None:
    assert {member.value for member in BookmarkIndexState} == {
        "pending",
        "indexed",
        "error",
        "deferred",
        "disabled",
    }
    assert MessageBookmark.__table__.c.index_state.nullable is True
    assert MessageBookmark.__table__.c.indexed_at.nullable is True


def test_a_kept_answer_is_its_own_document_source() -> None:
    assert RAGDocumentSourceType.BOOKMARK == "bookmark"


def test_the_space_role_is_declared_once_and_distinct_from_the_meetings_one() -> None:
    assert BOOKMARKS_SPACE_KIND == "bookmarks"
    assert BOOKMARKS_SPACE_KIND != MEETINGS_SPACE_KIND
