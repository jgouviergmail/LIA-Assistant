"""The board reads: one visibility predicate, one filter, exact counts (ADR-276).

These assertions are about the SHAPE of the statements, which is where the
honesty rules live:

- **one visibility predicate**, reused by every read — two would eventually
  disagree about whose board a ticket is on;
- **the page and its counts come from the SAME filtered statement** (ADR-185):
  a column header saying 7 above a column showing 3 is worse than no count;
- **every ordering ends on the primary key**, without which two tickets sharing
  a sort key can repeat or vanish across a page boundary.

Behaviour against a real server is proved in
``tests/integration/domains/workboard``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.domains.workboard.board_queries import BoardFilters, needs_me_stmt
from src.domains.workboard.constants import STATUS_ORDER
from src.domains.workboard.repository import WorkboardRepository

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


def _repo() -> WorkboardRepository:
    return WorkboardRepository(AsyncMock())


def _sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestVisibility:
    """A ticket is on U's board iff U owns it or holds it."""

    def test_the_predicate_names_both_sides(self) -> None:
        sql = _sql(_repo()._board_stmt(USER, BoardFilters()))
        assert "owner_user_id = " in sql
        assert "assignee_user_id = " in sql
        assert " OR " in sql

    def test_every_read_uses_the_same_predicate(self) -> None:
        """Board, counts and detail must not each decide who may look."""
        repo = _repo()
        for statement in (
            repo._board_stmt(USER, BoardFilters()),
            repo._counts_stmt(USER, BoardFilters()),
        ):
            sql = _sql(statement)
            assert f"owner_user_id = '{USER}'" in sql
            assert f"assignee_user_id = '{USER}'" in sql


class TestFilters:
    def test_assignee_me_means_a_human_holder_who_is_me(self) -> None:
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(assignee="me")))
        assert "assignee_kind = 'human'" in sql

    def test_assignee_me_accepts_the_null_that_means_the_owner(self) -> None:
        """NULL is « the owner holds it », so « assigned to me » must match a
        ticket I own and never handed over — the common case of a whole board."""
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(assignee="me")))
        assert "assignee_user_id IS NULL" in sql

    def test_assignee_lia_reads_the_kind_not_the_holder(self) -> None:
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(assignee="lia")))
        assert "assignee_kind = 'lia'" in sql

    def test_assignee_peer_means_somebody_else_holds_it(self) -> None:
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(assignee="peer")))
        assert "assignee_user_id IS NOT NULL" in sql

    def test_assignee_peer_excludes_the_reader_themselves(self) -> None:
        """« Une connexion » is SOMEBODY ELSE, and a peer reads their own board too.

        A peer holds tickets whose ``assignee_user_id`` is their OWN id, so a
        filter reading « held by anybody » handed them their own work under a
        label that says a connection holds it — and « Moi » returned the same
        rows. The two sides of the control must be disjoint.
        """
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(assignee="peer")))
        assert f"assignee_user_id != '{USER}'" in sql

    def test_overdue_reads_open_statuses_only(self) -> None:
        """A ticket finished last month is not « overdue »."""
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(overdue=True)))
        assert "due_at <" in sql
        assert "status NOT IN" in sql

    def test_priorities_filter(self) -> None:
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(priorities=("high", "urgent"))))
        assert "priority IN ('high', 'urgent')" in sql

    def test_statuses_filter(self) -> None:
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(statuses=("todo",))))
        assert "status IN ('todo')" in sql

    def test_closed_tickets_are_hidden_past_the_cutoff_only(self) -> None:
        """An OPEN ticket is never hidden by the closed-tickets filter, however
        old it is — the filter is about what is finished, not what is stale."""
        cutoff = datetime(2026, 8, 1, tzinfo=UTC)
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(include_closed_before=cutoff)))
        assert "status NOT IN ('done')" in sql or "status NOT IN" in sql
        assert "status_changed_at >=" in sql

    def test_text_search_is_case_insensitive(self) -> None:
        """ILIKE, not a Python fold: the board filter is a convenience over a
        title, and folding here would make SQL a second authority on identity
        beside fold_name (ADR-185), which resolves a ticket BY NAME."""
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(query="venue")))
        assert "ILIKE" in sql
        assert "%venue%" in sql

    def test_due_before(self) -> None:
        sql = _sql(
            _repo()._board_stmt(USER, BoardFilters(due_before=datetime(2026, 9, 30, tzinfo=UTC)))
        )
        assert "due_at <=" in sql


class TestOrdering:
    @pytest.mark.parametrize("sort", ["position", "priority", "due", "updated", "created"])
    def test_every_order_ends_on_the_primary_key(self, sort: str) -> None:
        """Without a total order, a page boundary repeats or loses a row."""
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(sort=sort)))  # type: ignore[arg-type]
        order_by = sql.split("ORDER BY", 1)[1]
        assert order_by.strip().endswith("workboard_tickets.id ASC")

    def test_priority_sort_puts_urgent_first(self) -> None:
        """A textual sort would read « high, low, medium, urgent »."""
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(sort="priority")))
        assert "CASE" in sql
        assert sql.index("'urgent'") < sql.index("'low'")

    def test_due_sort_never_floats_undated_tickets_to_the_top(self) -> None:
        sql = _sql(_repo()._board_stmt(USER, BoardFilters(sort="due")))
        assert "NULLS LAST" in sql.upper()


class TestCounts:
    def test_counts_share_the_page_filter(self) -> None:
        filters = BoardFilters(priorities=("high",), assignee="lia")
        page = _sql(_repo()._board_stmt(USER, filters))
        counts = _sql(_repo()._counts_stmt(USER, filters))
        for fragment in ("priority IN ('high')", "assignee_kind = 'lia'"):
            assert fragment in page
            assert fragment in counts

    def test_counts_group_by_status(self) -> None:
        assert "GROUP BY" in _sql(_repo()._counts_stmt(USER, BoardFilters()))

    def test_counts_do_not_carry_the_page_ordering(self) -> None:
        """An aggregate does not need an ORDER BY, and PostgreSQL refuses one
        over a column that is neither grouped nor aggregated."""
        assert "ORDER BY" not in _sql(_repo()._counts_stmt(USER, BoardFilters()))

    async def test_every_column_is_present_even_when_empty(self) -> None:
        """A missing key would read as « no column » rather than « nothing in
        it » on the board, and the header would render blank."""
        repo = _repo()
        result = MagicMock()
        result.all.return_value = [("todo", 3)]
        repo.db.execute = AsyncMock(return_value=result)
        counts = await repo.counts_by_status(USER, BoardFilters())
        assert set(counts) == set(STATUS_ORDER)
        assert counts["todo"] == 3
        assert counts["done"] == 0


class TestPaging:
    async def test_the_total_is_an_aggregate_not_the_page_length(self) -> None:
        repo = _repo()
        rows = MagicMock()
        rows.scalars.return_value.all.return_value = ["a", "b"]
        total = MagicMock()
        total.scalar.return_value = 42
        repo.db.execute = AsyncMock(side_effect=[rows, total])
        page, count = await repo.list_board(USER, BoardFilters(), limit=2, offset=0)
        assert len(page) == 2
        assert count == 42

    async def test_the_total_statement_drops_the_ordering(self) -> None:
        """COUNT over a subquery keeps its ORDER BY otherwise — wasted sort work
        on every board read."""
        repo = _repo()
        rows = MagicMock()
        rows.scalars.return_value.all.return_value = []
        total = MagicMock()
        total.scalar.return_value = 0
        repo.db.execute = AsyncMock(side_effect=[rows, total])
        await repo.list_board(USER, BoardFilters(), limit=10, offset=0)
        count_sql = _sql(repo.db.execute.await_args_list[1].args[0])
        assert "ORDER BY" not in count_sql


class TestRenumber:
    async def test_one_statement_writes_the_whole_column(self) -> None:
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=3))
        ids = [uuid.uuid4() for _ in range(3)]
        assert await repo.renumber_column(USER, "todo", ids) == 3
        repo.db.execute.assert_awaited_once()
        sql = _sql(repo.db.execute.await_args.args[0])
        assert "UPDATE workboard_tickets" in sql
        assert "CASE" in sql

    async def test_an_empty_column_writes_nothing(self) -> None:
        repo = _repo()
        repo.db.execute = AsyncMock()
        assert await repo.renumber_column(USER, "todo", []) == 0
        repo.db.execute.assert_not_awaited()

    async def test_it_only_touches_the_owner_board_and_the_named_column(self) -> None:
        repo = _repo()
        repo.db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        await repo.renumber_column(USER, "todo", [uuid.uuid4()])
        sql = _sql(repo.db.execute.await_args.args[0])
        assert f"owner_user_id = '{USER}'" in sql
        assert "status = 'todo'" in sql


class TestTitleResolution:
    """Folding decides; SQL must not pre-filter it away.

    The behaviour lives in ``tests/integration`` — a stub cannot fold. What is
    falsifiable HERE is the defect that made the integration test red first: an
    ``ILIKE`` on the raw needle looks like a harmless narrowing and is STRICTER
    than the folding it feeds, so « reserver la salle » silently found nothing
    while the board held « Réserver la salle ».
    """

    async def test_the_candidate_read_never_narrows_by_title(self) -> None:
        repo = _repo()
        rows = MagicMock()
        rows.all.return_value = []
        repo.db.execute = AsyncMock(return_value=rows)

        await repo.find_by_title(USER, "reserver la salle")

        sql = _sql(repo.db.execute.await_args.args[0])
        assert "ILIKE" not in sql.upper(), "a stricter pre-filter discards what folding catches"
        assert "LIKE" not in sql.upper()
        assert f"owner_user_id = '{USER}'" in sql, "the read stays scoped to the reader's board"

    async def test_it_reads_two_light_columns_not_whole_rows(self) -> None:
        """The scan is bounded by the per-account ticket cap, so it must carry
        the two columns folding needs and not the thirty a ticket has."""
        repo = _repo()
        rows = MagicMock()
        rows.all.return_value = []
        repo.db.execute = AsyncMock(return_value=rows)

        await repo.find_by_title(USER, "anything")

        selected = _sql(repo.db.execute.await_args.args[0]).split("FROM", 1)[0]
        assert "workboard_tickets.id" in selected
        assert "workboard_tickets.title" in selected
        assert "workboard_tickets.description" not in selected

    async def test_an_empty_needle_asks_the_database_nothing(self) -> None:
        """« Every title folds to the empty string » would match a whole board."""
        repo = _repo()
        repo.db.execute = AsyncMock()
        assert await repo.find_by_title(USER, "   ") == []
        repo.db.execute.assert_not_awaited()


class TestNeedsMe:
    def test_it_asks_for_what_waits_on_me_or_is_late_on_my_board(self) -> None:
        sql = _sql(needs_me_stmt(USER, datetime(2026, 9, 9, tzinfo=UTC)))
        # A question and an action to confirm (lot 7) both wait on the person.
        assert "status IN ('waiting', 'confirming')" in sql
        assert "due_at <" in sql
        assert "status NOT IN" in sql

    def test_waiting_counts_only_when_it_waits_on_ME(self) -> None:
        """A ticket a peer must answer is not mine to act on."""
        sql = _sql(needs_me_stmt(USER, datetime(2026, 9, 9, tzinfo=UTC)))
        waiting_clause = sql[sql.index("'waiting'") :]
        assert "assignee_user_id" in waiting_clause or "owner_user_id" in waiting_clause
