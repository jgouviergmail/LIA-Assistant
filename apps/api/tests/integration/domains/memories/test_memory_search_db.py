"""Narrowing a memory lookup by category, on real pgvector (ADR-313).

The memory search tool may ask for one family of memories (« the rules I gave
you », « the people I know »). The narrowing is a SQL predicate beside the
cosine ranking, so it is proven where the ranking runs: PostgreSQL.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.models import MEMORY_EMBEDDING_DIMENSIONS, Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration


def _vector(*weights: float) -> list[float]:
    """A unit-ish vector whose first components are the given weights."""
    vector = [0.0] * MEMORY_EMBEDDING_DIMENSIONS
    for index, weight in enumerate(weights):
        vector[index] = weight
    return vector


@pytest.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email=f"memory-{uuid4().hex[:6]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Memory Owner",
    )
    async_session.add(user)
    await async_session.flush()
    for content, category, vector in (
        ("Drinks green tea every morning", "preference", _vector(1.0, 0.1)),
        ("Always answer in short bullet points", "procedural", _vector(0.95, 0.2)),
        ("Sister named Claire", "relationship", _vector(0.1, 1.0)),
    ):
        async_session.add(
            Memory(user_id=user.id, content=content, category=category, embedding=vector)
        )
    await async_session.commit()
    return user


class TestCategoryNarrowing:
    async def test_categories_keep_only_the_asked_families(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        results = await MemoryRepository(async_session).search_by_relevance(
            user_id=owner.id,
            query_embedding=_vector(1.0, 0.0),
            limit=10,
            min_score=0.0,
            categories={"procedural"},
        )

        assert [memory.content for memory, _score in results] == [
            "Always answer in short bullet points"
        ]

    async def test_without_categories_every_family_competes_by_relevance(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        results = await MemoryRepository(async_session).search_by_relevance(
            user_id=owner.id,
            query_embedding=_vector(1.0, 0.0),
            limit=2,
            min_score=0.0,
        )

        assert [memory.category for memory, _score in results] == ["preference", "procedural"]


def _assert_vectors_not_loaded(memory: Memory) -> None:
    """The row carries no vector, and reading one raises instead of reloading it."""
    assert {"embedding", "keyword_embedding"} <= inspect(memory).unloaded
    with pytest.raises(InvalidRequestError):
        _ = memory.embedding


class TestReadDoorsWithoutVectors:
    """A read door ranks on the server and parses no vector in Python (latency lot 5).

    pgvector hands each 1536-dimension vector to Python as text parsed float by
    float on the event loop: 84.5 ms for 75 rows on the production host, 8.9 ms
    once the two columns stay in the database.
    """

    async def test_a_search_without_vectors_ranks_the_same(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        repository = MemoryRepository(async_session)
        query = _vector(1.0, 0.0)
        async_session.expunge_all()
        lean = await repository.search_by_relevance(
            user_id=owner.id, query_embedding=query, limit=10, min_score=0.0, with_vectors=False
        )
        for memory, _score in lean:
            _assert_vectors_not_loaded(memory)
        lean_ranking = [(memory.content, score) for memory, score in lean]

        async_session.expunge_all()
        full = await repository.search_by_relevance(
            user_id=owner.id, query_embedding=query, limit=10, min_score=0.0
        )

        assert lean_ranking == [(memory.content, score) for memory, score in full]
        assert all(memory.embedding is not None for memory, _score in full)

    async def test_the_relationship_lookup_without_vectors(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        async_session.expunge_all()
        results = await MemoryRepository(async_session).get_relationships_for_user(
            user_id=owner.id, query_embedding=_vector(0.1, 1.0), min_score=0.0, with_vectors=False
        )

        assert [memory.content for memory, _score in results] == ["Sister named Claire"]
        _assert_vectors_not_loaded(results[0][0])

    async def test_the_recent_fallback_without_vectors(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        async_session.expunge_all()
        recent = await MemoryRepository(async_session).get_recent_for_user(
            owner.id, limit=5, with_vectors=False
        )

        assert len(recent) == 3
        for memory in recent:
            _assert_vectors_not_loaded(memory)

    async def test_an_empty_category_set_narrows_nothing(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """An empty set is « no narrowing », never « no family allowed »."""
        results = await MemoryRepository(async_session).search_by_relevance(
            user_id=owner.id,
            query_embedding=_vector(0.0, 1.0),
            limit=1,
            min_score=0.0,
            categories=set(),
        )

        assert [memory.content for memory, _score in results] == ["Sister named Claire"]
