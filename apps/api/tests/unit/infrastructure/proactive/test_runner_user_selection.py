"""Proactive user selection prefilter + fairness (lot 5, D-05 requalified).

The historical query was ``select(User).limit(batch_size)`` with no flag
filter and no ordering: disabled users consumed batch slots (323
feature_disabled checks/7d measured in prod), and past ``batch_size``
verified users the heap order silently starved whoever sorted last —
forever, on every tick.

Fixes pinned here:
- the checker's ``enabled_field`` is pushed into SQL (boolean — safe,
  unlike a timezone computation whose single corrupt row would kill the
  whole batch: that prefilter was evaluated and deliberately rejected);
- ``ORDER BY random()`` makes slot allocation fair across ticks.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from src.infrastructure.proactive.runner import build_candidate_users_query


def _sql(enabled_field: str | None = "heartbeat_enabled", batch_size: int = 50) -> str:
    query = build_candidate_users_query(enabled_field=enabled_field, batch_size=batch_size)
    return str(query.compile(dialect=postgresql.dialect()))


class TestCandidateUsersQuery:
    def test_enabled_flag_is_pushed_into_sql(self) -> None:
        assert "users.heartbeat_enabled IS true" in _sql()

    def test_interest_flag_variant(self) -> None:
        assert "users.interests_enabled IS true" in _sql("interests_enabled")

    def test_no_flag_keeps_historical_shape(self) -> None:
        """A checker-less runner (defensive path) filters nothing extra.

        The projection lists every User column, so the assertion targets the
        WHERE clause predicates, not the raw SQL text."""
        sql = _sql(enabled_field=None)
        assert "heartbeat_enabled IS true" not in sql
        assert "interests_enabled IS true" not in sql

    def test_baseline_account_filters_preserved(self) -> None:
        sql = _sql()
        assert "users.is_verified" in sql
        assert "users.is_active" in sql
        assert "users.deleted_at IS NULL" in sql

    def test_batch_is_fair_across_ticks(self) -> None:
        """random() ordering: no user is permanently starved by heap order."""
        assert "ORDER BY random()" in _sql()

    def test_batch_size_still_bounds_the_scan(self) -> None:
        assert "LIMIT" in _sql(batch_size=7)

    def test_unknown_enabled_field_is_refused(self) -> None:
        """A typo must fail loudly, never silently select everyone."""
        import pytest

        with pytest.raises(ValueError, match="unknown enabled_field"):
            build_candidate_users_query(enabled_field="no_such_flag", batch_size=10)


class TestExplicitUsers:
    """ADR-261: the wake sweep targets explicit users; the random slot
    allocation stays for the population batch."""

    def test_user_ids_restrict_the_candidates(self) -> None:
        import uuid

        from src.infrastructure.proactive.runner import build_candidate_users_query

        uid = uuid.uuid4()
        query = build_candidate_users_query(
            enabled_field="heartbeat_enabled", batch_size=1, user_ids=[uid]
        )
        sql = str(query.compile(dialect=postgresql.dialect()))
        assert "users.id IN" in sql
        assert "heartbeat_enabled" in sql

    def test_without_user_ids_no_in_clause(self) -> None:
        assert "users.id IN" not in _sql("heartbeat_enabled", 5)
