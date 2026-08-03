"""What the assistant ACHIEVED for this user, over the billing cycle.

The dashboard led with messages, tokens, Google requests and cost. Those are
administration figures, not a story of value: they say how much was spent, never
what came of it.

Every figure here is an EXACT aggregate over the whole set (ADR-185) — never the
length of a page, never an estimate. And nothing is invented: "time saved" has
no source in this system and is therefore absent, as is "documents actually
used", which no table records durably.

The queries are pinned by their SHAPE rather than by a live database: what must
not drift is the window, the state, and the fact that each figure counts its own
kind — a validated *answer* is not a successful *action*.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.product.repository import ProductRepository

pytestmark = pytest.mark.unit

CYCLE_START = datetime(2026, 8, 1, tzinfo=UTC)


def _repo_returning(*values: int | None) -> tuple[ProductRepository, MagicMock]:
    """A repository whose single aggregate answers with these three counts.

    ONE row, not three reads: the totals must come from one snapshot. Under
    READ COMMITTED, three separate counts can each see a different one, and
    `actions` is a SUBSET of `useful_results` — a row landing between two of
    them would show the reader more actions than results, which is not a
    smaller truth but an impossible one.
    """
    db = MagicMock()
    result = MagicMock()
    result.one.return_value = tuple(values)
    db.execute = AsyncMock(return_value=result)
    return ProductRepository(db), db


def _sql_of(db: MagicMock) -> str:
    return str(db.execute.await_args.args[0])


class TestPersonalResults:
    async def test_reports_each_kind_separately(self) -> None:
        repo, _ = _repo_returning(12, 5, 3)

        results = await repo.personal_results(user_id=uuid4(), since=CYCLE_START)

        assert results == {"useful_results": 12, "actions": 5, "automations": 3}

    async def test_a_quiet_cycle_reports_zero_rather_than_nothing(self) -> None:
        """Zero is a true answer; a missing figure would read as a bug."""
        repo, _ = _repo_returning(0, 0, 0)

        results = await repo.personal_results(user_id=uuid4(), since=CYCLE_START)

        assert results == {"useful_results": 0, "actions": 0, "automations": 0}

    async def test_a_null_count_degrades_to_zero(self) -> None:
        """An aggregate can answer NULL on an empty set in some drivers."""
        repo, _ = _repo_returning(None, None, None)

        results = await repo.personal_results(user_id=uuid4(), since=CYCLE_START)

        assert results == {"useful_results": 0, "actions": 0, "automations": 0}

    async def test_the_three_figures_come_from_ONE_snapshot(self) -> None:
        repo, db = _repo_returning(1, 1, 1)

        await repo.personal_results(user_id=uuid4(), since=CYCLE_START)

        assert db.execute.await_count == 1

    async def test_the_aggregate_is_scoped_to_the_user_and_the_window(self) -> None:
        """A count leaking another account, or the whole history, is a lie."""
        repo, db = _repo_returning(1, 1, 1)

        await repo.personal_results(user_id=uuid4(), since=CYCLE_START)

        sql = _sql_of(db)
        assert "user_id" in sql
        assert "produced_at" in sql
        # An aggregate over the set, never a page whose length is counted.
        assert "count(" in sql.lower()

    async def test_each_kind_is_counted_by_its_own_filter(self) -> None:
        """One pass, three columns — not one column re-read three times."""
        repo, db = _repo_returning(1, 1, 1)

        await repo.personal_results(user_id=uuid4(), since=CYCLE_START)

        sql = _sql_of(db).lower()
        assert sql.count("count(") == 3
        assert "filter" in sql

    async def test_only_validated_outcomes_are_counted(self) -> None:
        """`produced` means presented, not confirmed useful (E3 vs E1/E2)."""
        repo, db = _repo_returning(1, 1, 1)

        await repo.personal_results(user_id=uuid4(), since=CYCLE_START)

        assert "state" in _sql_of(db)
