"""Journal read doors without the vector columns, on real pgvector (latency lot 5).

The journal context of a turn reads its entries by relevance and by recency and
only ever uses their text: the two 1536-dimension vectors each row carries are
parsed by pgvector in Python, float by float, on the event loop. A read door
asks for them to stay in the database. Extraction keeps the default, because
the entries it loads may be merged, and a merge reads the winner's vectors.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals.constants import JOURNAL_EMBEDDING_DIMENSIONS
from src.domains.journals.models import JournalEntry
from src.domains.journals.repository import JournalEntryRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration


def _vector(*weights: float) -> list[float]:
    """A vector whose first components are the given weights."""
    vector = [0.0] * JOURNAL_EMBEDDING_DIMENSIONS
    for index, weight in enumerate(weights):
        vector[index] = weight
    return vector


def _assert_vectors_not_loaded(entry: JournalEntry) -> None:
    """The row carries no vector, and reading one raises instead of reloading it."""
    assert {"embedding", "keyword_embedding"} <= inspect(entry).unloaded
    with pytest.raises(InvalidRequestError):
        _ = entry.embedding


@pytest.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email=f"journal-{uuid4().hex[:6]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Journal Owner",
    )
    async_session.add(user)
    await async_session.flush()
    for title, vector in (
        ("Short answers land better", _vector(1.0, 0.1)),
        ("Mornings are for planning", _vector(0.2, 1.0)),
    ):
        async_session.add(
            JournalEntry(
                user_id=user.id,
                theme="learnings",
                title=title,
                content=title,
                char_count=len(title),
                embedding=vector,
                keyword_embedding=vector,
            )
        )
    await async_session.commit()
    return user


class TestJournalReadDoorsWithoutVectors:
    async def test_a_search_without_vectors_ranks_the_same(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repository = JournalEntryRepository(async_session)
        query = _vector(1.0, 0.0)
        async_session.expunge_all()
        lean = await repository.search_by_relevance(
            user_id=owner.id, query_embedding=query, limit=10, with_vectors=False
        )
        for entry, _score in lean:
            _assert_vectors_not_loaded(entry)
        lean_ranking = [(entry.title, score) for entry, score in lean]

        async_session.expunge_all()
        full = await repository.search_by_relevance(
            user_id=owner.id, query_embedding=query, limit=10
        )

        assert lean_ranking == [(entry.title, score) for entry, score in full]
        assert lean_ranking[0][0] == "Short answers land better"
        # The default carries them: extraction hands its entries to a merge.
        assert all(entry.embedding is not None for entry, _score in full)

    async def test_the_recent_entries_without_vectors(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repository = JournalEntryRepository(async_session)
        async_session.expunge_all()
        recent = await repository.get_recent_for_user(owner.id, limit=5, with_vectors=False)

        assert len(recent) == 2
        for entry in recent:
            _assert_vectors_not_loaded(entry)
        async_session.expunge_all()
        assert all(
            entry.embedding is not None
            for entry in await repository.get_recent_for_user(owner.id, limit=5)
        )
