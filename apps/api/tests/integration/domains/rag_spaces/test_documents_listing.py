"""The documents a person may attach to a message, listed across their spaces.

The composer's « + » lists the `ready` documents of EVERY space of the
account — active or not — with an exact total (ADR-185: the page and the
count come from one filtered statement), a name needle whose LIKE wildcards
are escaped, and never a system space's document (it belongs to nobody) nor
one still indexing. Real PostgreSQL: a stubbed session has no ILIKE.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.rag_spaces.models import RAGDocument, RAGDocumentStatus, RAGSpace
from src.domains.rag_spaces.repository import RAGDocumentRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _document(db: AsyncSession, space: RAGSpace, name: str, status: str) -> RAGDocument:
    doc = RAGDocument(
        space_id=space.id,
        user_id=space.user_id,
        filename=f"{name}.bin",
        original_filename=name,
        file_size=10,
        content_type="text/plain",
        status=status,
    )
    db.add(doc)
    await db.flush()
    return doc


async def _seed(db: AsyncSession):
    user = UserFactory.create()
    other = UserFactory.create()
    db.add_all([user, other])
    await db.flush()
    active = RAGSpace(name="Contracts", user_id=user.id, is_active=True)
    paused = RAGSpace(name="Archive", user_id=user.id, is_active=False)
    theirs = RAGSpace(name="Theirs", user_id=other.id, is_active=True)
    system = RAGSpace(name="lia-faq-test", user_id=None, is_system=True, is_active=True)
    db.add_all([active, paused, theirs, system])
    await db.flush()
    await _document(db, active, "lease 2026.pdf", RAGDocumentStatus.READY)
    await _document(db, active, "still indexing.pdf", RAGDocumentStatus.PROCESSING)
    await _document(db, paused, "old lease 2019.pdf", RAGDocumentStatus.READY)
    await _document(db, paused, "notes_100%.txt", RAGDocumentStatus.READY)
    await _document(db, theirs, "lease of theirs.pdf", RAGDocumentStatus.READY)
    await _document(db, system, "faq.md", RAGDocumentStatus.READY)
    await db.commit()
    return user


async def test_lists_ready_documents_of_every_own_space_with_an_exact_total(
    async_session: AsyncSession,
) -> None:
    user = await _seed(async_session)
    repo = RAGDocumentRepository(async_session)
    rows, total = await repo.search_ready_for_user(user.id, needle=None, limit=2, offset=0)
    assert total == 3
    assert len(rows) == 2
    names = {r.original_filename for r in rows}
    assert "still indexing.pdf" not in names
    assert "lease of theirs.pdf" not in names and "faq.md" not in names
    # The page carries the space beside the document.
    assert all(hasattr(r, "space") and r.space.name in {"Contracts", "Archive"} for r in rows)


async def test_the_needle_matches_the_name_and_escapes_the_wildcards(
    async_session: AsyncSession,
) -> None:
    user = await _seed(async_session)
    repo = RAGDocumentRepository(async_session)
    rows, total = await repo.search_ready_for_user(user.id, needle="lease", limit=10, offset=0)
    assert total == 2
    assert {r.original_filename for r in rows} == {"lease 2026.pdf", "old lease 2019.pdf"}
    # `%` is a character of the name here, not a wildcard.
    rows, total = await repo.search_ready_for_user(user.id, needle="100%", limit=10, offset=0)
    assert total == 1 and rows[0].original_filename == "notes_100%.txt"
    rows, total = await repo.search_ready_for_user(user.id, needle="%", limit=10, offset=0)
    assert total == 1


async def test_the_page_is_ordered_newest_first_then_by_id(async_session: AsyncSession) -> None:
    user = await _seed(async_session)
    repo = RAGDocumentRepository(async_session)
    first, _ = await repo.search_ready_for_user(user.id, needle=None, limit=3, offset=0)
    again, _ = await repo.search_ready_for_user(user.id, needle=None, limit=3, offset=0)
    assert [r.id for r in first] == [r.id for r in again]
    stamps = [(r.created_at, str(r.id)) for r in first]
    assert stamps == sorted(stamps, key=lambda s: (s[0], s[1]), reverse=True)
