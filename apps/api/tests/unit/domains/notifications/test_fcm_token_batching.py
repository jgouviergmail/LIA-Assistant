"""The broadcast's token lookup: one query per slice, never one per user (ADR-312).

A broadcast used to read its recipients' tokens one account at a time — N
queries for N accounts. The batched lookup must also stay under asyncpg's
32 767 bind-parameter ceiling, which an instance-wide language group can pass.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.notifications.repository import FCMTokenRepository


def _repository(rows: list[str]) -> tuple[FCMTokenRepository, MagicMock]:
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = rows
    db.scalars = AsyncMock(return_value=result)
    return FCMTokenRepository(db), db


@pytest.mark.unit
class TestActiveTokenStrings:
    async def test_a_large_group_is_read_in_bounded_slices(self) -> None:
        repo, db = _repository(["token"])

        tokens = await repo.get_active_token_strings([uuid4() for _ in range(2500)])

        # 1000 + 1000 + 500 ids: three statements, each far under the ceiling.
        assert db.scalars.await_count == 3
        assert tokens == ["token", "token", "token"]

    async def test_nobody_costs_no_query(self) -> None:
        repo, db = _repository([])

        assert await repo.get_active_token_strings([]) == []
        db.scalars.assert_not_awaited()
