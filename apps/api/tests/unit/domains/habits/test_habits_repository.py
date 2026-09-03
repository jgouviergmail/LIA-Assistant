"""Unit tests for the habits repository SQL contract (ADR-214).

The SQL itself was validated live against the production schema (read-only,
2026-08-05: the anti-automation filter removed a 66-day scheduled-action
metronome from a real account in 1.3 ms). These tests pin the CONTRACT so a
refactor cannot silently drop a clause:

- the message source excludes automated runs BOTH by metadata marker (new
  rows) and by run→session whitelist (historical rows written before the
  marker existed — kept until 2026-09-30, when the last unmarked row leaves
  the 56-day window);
- the durable run source is ``product_outcomes`` through the ONE human
  predicate shared with the recurrence-ledger seed (2026-09-03: the token
  summaries are deleted by the conversation reset — 5 human rows in 56 days
  for 235 real turns);
- the reset audit trail is a presence source (single caller: the
  authenticated reset endpoint — human by construction);
- the observation bounds span all three sources.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.constants import HUMAN_CHAT_SESSION_UUID_REGEX
from src.domains.habits.human_turns import HUMAN_OUTCOME_PREDICATE_SQL
from src.domains.habits.repository import (
    _ACTIVITY_BOUNDS_SQL,
    _DAY_ACTIVITY_SQL,
    _RESET_ACTIVITY_SQL,
    _RUN_ACTIVITY_SQL,
    HabitsRepository,
)

pytestmark = pytest.mark.unit


def _repo_with_capture() -> tuple[HabitsRepository, MagicMock]:
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    return HabitsRepository(db), db


class TestMessageSourceAntiAutomation:
    """Historical automated rows carry NO metadata marker: on the primary
    production accounts, a daily scheduled action wrote one user-role message
    at a fixed hour for 66 straight days — enough for the detector to claim
    LIA's own scheduler as the user's habit. The run→session whitelist is
    the only filter that reaches those rows."""

    def test_sql_excludes_runs_outside_the_session_whitelist(self) -> None:
        sql = str(_DAY_ACTIVITY_SQL)
        assert "is_automated_source" in sql  # marker filter (new rows)
        assert "NOT EXISTS" in sql  # whitelist filter (historical rows)
        assert "message_token_summary" in sql
        assert ":uuid_regex" in sql

    async def test_fetch_day_activity_binds_the_whitelist_regex(self) -> None:
        repo, db = _repo_with_capture()
        await repo.fetch_day_activity(uuid.uuid4(), "Europe/Paris", datetime.now(UTC))
        params = db.execute.await_args.args[1]
        assert params["uuid_regex"] == HUMAN_CHAT_SESSION_UUID_REGEX


class TestOutcomeSource:
    """The durable human-turn source is product_outcomes (one row per run,
    never deleted by a conversation reset — token summaries ARE)."""

    def test_sql_reads_outcomes_with_the_shared_predicate(self) -> None:
        sql = str(_RUN_ACTIVITY_SQL)
        assert "product_outcomes" in sql
        assert HUMAN_OUTCOME_PREDICATE_SQL in sql
        assert "message_token_summary" not in sql

    async def test_fetch_run_activity_binds_no_session_whitelist(self) -> None:
        repo, db = _repo_with_capture()
        await repo.fetch_run_activity(uuid.uuid4(), "Europe/Paris", datetime.now(UTC))
        params = db.execute.await_args.args[1]
        assert set(params) == {"user_id", "tz", "since"}

    async def test_fetch_run_activity_builds_day_histograms(self) -> None:
        repo, db = _repo_with_capture()
        from datetime import date

        db.execute.return_value.all.return_value = [
            (date(2026, 9, 1), 9, 3),
            (date(2026, 9, 2), 21, 1),
        ]
        days = await repo.fetch_run_activity(uuid.uuid4(), "Europe/Paris", datetime.now(UTC))
        assert days == {date(2026, 9, 1): {9: 3}, date(2026, 9, 2): {21: 1}}


class TestResetPresenceSource:
    """961 resets measured in production; 124 distinct days on the primary
    account vs 4 through summaries. ``reset_conversation`` has exactly one
    caller (the authenticated router endpoint), so every audit row is a
    human action — presence-grade by construction."""

    def test_sql_targets_only_the_reset_action(self) -> None:
        sql = str(_RESET_ACTIVITY_SQL)
        assert "conversation_audit_log" in sql
        assert "action = 'reset'" in sql

    async def test_fetch_reset_activity_builds_day_histograms(self) -> None:
        repo, db = _repo_with_capture()
        from datetime import date

        db.execute.return_value.all.return_value = [
            (date(2026, 8, 1), 21, 3),
            (date(2026, 8, 1), 22, 1),
            (date(2026, 8, 2), 9, 2),
        ]
        days = await repo.fetch_reset_activity(uuid.uuid4(), "Europe/Paris", datetime.now(UTC))
        assert days == {
            date(2026, 8, 1): {21: 3, 22: 1},
            date(2026, 8, 2): {9: 2},
        }


class TestActivityBounds:
    def test_bounds_union_spans_every_durable_human_source(self) -> None:
        """Messages, human runs, resets — and the thumbs (ADR-214 amendment).

        A user who reads without typing produces none of the first three; the
        thumb is their only timestamped human act, and leaving it out made
        "no activity" false for exactly that profile (cold review 2026-09-03).
        """
        sql = str(_ACTIVITY_BOUNDS_SQL)
        assert "conversation_messages" in sql
        assert "product_outcomes" in sql
        assert HUMAN_OUTCOME_PREDICATE_SQL in sql
        assert "message_token_summary" not in sql
        assert "conversation_audit_log" in sql
        assert "heartbeat_notifications" in sql
        assert "interest_notifications" in sql
        assert "feedback_at IS NOT NULL" in sql
        assert sql.count("UNION ALL") == 4

    async def test_fetch_activity_bounds_binds_only_the_user(self) -> None:
        repo, db = _repo_with_capture()
        db.execute.return_value.one_or_none.return_value = None
        await repo.fetch_activity_bounds(uuid.uuid4())
        assert set(db.execute.await_args.args[1]) == {"user_id"}
