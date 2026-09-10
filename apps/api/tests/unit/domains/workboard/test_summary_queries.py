"""The board at a glance (ADR-276, lot 18): sums over what is OWNED, counts over what is SEEN.

The shape of the statements is where the honesty lives: the spend is summed
over the tickets the account owns — a run is billed to the owner — while the
counts run over the visible board through the repository's ONE predicate. And
the figures the function composes are read back exactly as the rows give them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.domains.workboard.board_queries import BoardFilters
from src.domains.workboard.repository import WorkboardRepository
from src.domains.workboard.summary_queries import (
    count_over,
    owned_totals_stmt,
    read_board_summary,
)

pytestmark = pytest.mark.unit

USER = uuid.uuid4()
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestTheStatements:
    def test_the_spend_is_summed_over_what_the_account_owns_never_holds(self) -> None:
        sql = _sql(owned_totals_stmt(USER))

        assert f"owner_user_id = '{USER}'" in sql
        assert "assignee_user_id" not in sql
        for column in (
            "run_count",
            "total_tokens_in",
            "total_tokens_out",
            "total_tokens_cache",
            "total_google_requests",
            "total_cost_eur",
        ):
            assert f"sum(workboard_tickets.{column})" in sql, column
        # Zero-filled: an empty board reads as zeros, never as NULLs.
        assert sql.count("coalesce(") == 6

    def test_a_count_runs_over_the_same_filtered_set(self) -> None:
        repo = WorkboardRepository(AsyncMock())
        sql = _sql(count_over(repo.filtered_stmt(USER, BoardFilters(overdue=True))))

        assert "count(*)" in sql
        assert "due_at <" in sql
        assert f"owner_user_id = '{USER}'" in sql
        assert f"assignee_user_id = '{USER}'" in sql


class TestReadBoardSummary:
    async def test_it_composes_the_figures_as_the_rows_give_them(self) -> None:
        # The four scalar reads, in the order the function issues them, then
        # the one owned-totals row.
        scalars = iter([3, 2, 1])
        totals_row = (7, 12, 1000, 250, 400, 5, Decimal("0.4200"))

        async def execute(_stmt: object) -> MagicMock:
            result = MagicMock()
            try:
                result.scalar.return_value = next(scalars)
            except StopIteration:
                result.one.return_value = totals_row
            return result

        db = AsyncMock()
        db.execute = execute
        repo = MagicMock(spec=WorkboardRepository)
        repo.db = db
        repo.counts_by_status = AsyncMock(return_value={"todo": 4, "done": 1})
        repo.filtered_stmt = MagicMock(
            side_effect=lambda _user, _filters: WorkboardRepository(AsyncMock()).filtered_stmt(
                USER, _filters
            )
        )

        figures = await read_board_summary(repo, USER, NOW)

        assert figures.counts_by_status == {"todo": 4, "done": 1}
        assert (figures.overdue, figures.held_by_lia, figures.needs_me) == (3, 2, 1)
        assert figures.owned == 7
        assert figures.runs_total == 12
        assert (figures.tokens_in, figures.tokens_out, figures.tokens_cache) == (1000, 250, 400)
        assert figures.google_requests == 5
        assert figures.cost_eur == Decimal("0.4200")

    async def test_an_empty_board_reads_as_zeros(self) -> None:
        async def execute(_stmt: object) -> MagicMock:
            result = MagicMock()
            result.scalar.return_value = 0
            result.one.return_value = (0, 0, 0, 0, 0, 0, 0)
            return result

        db = AsyncMock()
        db.execute = execute
        repo = MagicMock(spec=WorkboardRepository)
        repo.db = db
        repo.counts_by_status = AsyncMock(return_value={"todo": 0})
        repo.filtered_stmt = MagicMock(
            side_effect=lambda _user, _filters: WorkboardRepository(AsyncMock()).filtered_stmt(
                USER, _filters
            )
        )

        figures = await read_board_summary(repo, USER, NOW)

        assert figures.owned == 0 and figures.runs_total == 0
        assert figures.cost_eur == Decimal(0)
