"""SQL predicate guards for the activity read-model statement builders.

The builders are pure; compiling them to PostgreSQL SQL lets the WHERE
contracts be asserted without a database (same doctrine as the ADR-232
``select(User)`` WHERE asserts). These guards pin the claims the timeline
makes: manual journal entries never surface, only ended loops count as
closed, and every rows statement is user-scoped, windowed and capped.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from src.domains.activity.repository import (
    _count_from,
    habit_rows_stmt,
    heartbeat_rows_stmt,
    interest_rows_stmt,
    journal_rows_stmt,
    open_loop_rows_stmt,
    open_loops_closed_count_stmt,
    open_loops_created_count_stmt,
    scheduled_action_rows_stmt,
)

USER_ID = uuid4()
SINCE = datetime(2026, 7, 20, tzinfo=UTC)


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


@pytest.mark.unit
class TestRowStatements:
    @pytest.mark.parametrize(
        "builder",
        [
            heartbeat_rows_stmt,
            interest_rows_stmt,
            journal_rows_stmt,
            habit_rows_stmt,
            open_loop_rows_stmt,
            scheduled_action_rows_stmt,
        ],
    )
    def test_every_rows_statement_is_user_scoped_and_capped(self, builder):
        sql = _sql(builder(USER_ID, SINCE, 50))

        assert "user_id" in sql
        assert "limit" in sql
        assert "order by" in sql and "desc" in sql

    def test_journal_statement_excludes_manual_and_archived(self):
        sql = _sql(journal_rows_stmt(USER_ID, SINCE, 50))

        assert "source in (" in sql
        assert "status =" in sql

    def test_open_loop_statement_matches_created_or_ended_in_window(self):
        sql = _sql(open_loop_rows_stmt(USER_ID, SINCE, 50))

        assert " or " in sql
        assert "status in" in sql or "status in (" in sql.replace("_", "")

    def test_scheduled_actions_require_a_past_execution(self):
        sql = _sql(scheduled_action_rows_stmt(USER_ID, SINCE, 50))

        assert "last_executed_at is not null" in sql
        assert "last_executed_at >=" in sql


@pytest.mark.unit
class TestCountStatements:
    def test_count_from_strips_order_and_limit_but_keeps_where(self):
        counted = _count_from(journal_rows_stmt(USER_ID, SINCE, 50))
        sql = _sql(counted)

        assert "count" in sql
        assert "user_id" in sql
        assert "limit" not in sql
        assert "order by" not in sql

    def test_loop_counts_split_created_and_ended(self):
        created_sql = _sql(open_loops_created_count_stmt(USER_ID, SINCE))
        closed_sql = _sql(open_loops_closed_count_stmt(USER_ID, SINCE))

        assert "created_at >=" in created_sql
        assert "status" not in created_sql
        assert "status in" in closed_sql
        assert "updated_at >=" in closed_sql
