"""Every memory retrieval path serves the ACTIVE set only (Lot 2-B1).

An invalidated fact must never surface in search, listings, counts or
consolidation pairing — otherwise the supersession trail would reintroduce
the very staleness it exists to remove. The oracle captures the statements
each repository method executes and asserts the compiled SQL carries the
``invalidated_at IS NULL`` predicate (ADR-232 WHERE-assert doctrine).
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from src.domains.memories.repository import MemoryRepository

USER_ID = uuid4()


def _capturing_repo() -> tuple[MemoryRepository, list]:
    captured: list = []

    async def _execute(stmt, *args, **kwargs):
        captured.append(stmt)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one.return_value = 0
        result.scalar.return_value = 0
        result.all.return_value = []
        result.first.return_value = None
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    return MemoryRepository(db), captured


def _compiled(captured: list) -> str:
    return " || ".join(str(stmt.compile(dialect=postgresql.dialect())).lower() for stmt in captured)


@pytest.mark.unit
class TestActiveSetFilters:
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda r: r.get_all_for_user(USER_ID), id="get_all_for_user"),
            pytest.param(
                lambda r: r.get_recent_for_user(USER_ID, limit=5), id="get_recent_for_user"
            ),
            pytest.param(lambda r: r.get_by_category(USER_ID, "identity"), id="get_by_category"),
            pytest.param(lambda r: r.get_count_for_user(USER_ID), id="get_count_for_user"),
            pytest.param(lambda r: r.get_count_by_category(USER_ID), id="get_count_by_category"),
            pytest.param(
                lambda r: r.list_mentioning_name(USER_ID, "camille", 10),
                id="list_mentioning_name",
            ),
            pytest.param(
                lambda r: r.find_consolidation_pairs(USER_ID, similarity_threshold=0.9, limit=10),
                id="find_consolidation_pairs",
            ),
        ],
    )
    async def test_reads_filter_the_active_set(self, call):
        repo, captured = _capturing_repo()

        await call(repo)

        assert captured, "no statement executed"
        assert "invalidated_at is null" in _compiled(captured)

    async def test_search_by_relevance_filters_the_active_set(self):
        repo, captured = _capturing_repo()

        await repo.search_by_relevance(user_id=USER_ID, query_embedding=[0.0] * 1536, limit=5)

        assert captured, "no statement executed"
        assert "invalidated_at is null" in _compiled(captured)
