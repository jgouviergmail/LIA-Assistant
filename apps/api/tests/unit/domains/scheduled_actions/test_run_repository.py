"""The run repository: insert at the result, read by week, purge by age (ADR-265).

Unit level — the session is a double. What these pin is the CONTRACT the
executor and the week read rely on: the row carries every field the week
colouring needs, an error is bounded like ``last_error`` is, the purge reports
what it removed, and the listing is oldest-first so the reader can fold by
overwriting. The SQL itself is proven against PostgreSQL in
``tests/integration/domains/scheduled_actions/test_runs_pg.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.scheduled_actions.models import ScheduledActionRun, ScheduledRunOutcome
from src.domains.scheduled_actions.run_repository import (
    RUN_ERROR_MAX_LENGTH,
    ScheduledActionRunRepository,
)

pytestmark = pytest.mark.unit

STARTED = datetime(2026, 8, 5, 6, 0, 3, tzinfo=UTC)
ENDED = datetime(2026, 8, 5, 6, 0, 41, tzinfo=UTC)
SLOT = datetime(2026, 8, 5, 6, 0, tzinfo=UTC)


def _db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


class TestRecord:
    async def test_the_row_carries_every_field_the_week_read_needs(self) -> None:
        db = _db()
        action_id, user_id = uuid.uuid4(), uuid.uuid4()

        row = await ScheduledActionRunRepository(db).record(
            scheduled_action_id=action_id,
            user_id=user_id,
            slot_at=SLOT,
            started_at=STARTED,
            ended_at=ENDED,
            outcome=ScheduledRunOutcome.SUCCESS,
            attempts=2,
            manual=False,
        )

        assert isinstance(row, ScheduledActionRun)
        assert (row.scheduled_action_id, row.user_id) == (action_id, user_id)
        assert (row.slot_at, row.started_at, row.ended_at) == (SLOT, STARTED, ENDED)
        assert row.outcome is ScheduledRunOutcome.SUCCESS
        assert (row.attempts, row.manual, row.error) == (2, False, None)
        db.add.assert_called_once_with(row)
        db.flush.assert_awaited_once()

    async def test_a_rehearsal_has_no_slot(self) -> None:
        row = await ScheduledActionRunRepository(_db()).record(
            scheduled_action_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            slot_at=None,
            started_at=STARTED,
            ended_at=ENDED,
            outcome=ScheduledRunOutcome.SUCCESS,
            attempts=1,
            manual=True,
        )
        assert row.slot_at is None
        assert row.manual is True

    async def test_the_error_is_bounded_like_last_error(self) -> None:
        row = await ScheduledActionRunRepository(_db()).record(
            scheduled_action_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            slot_at=SLOT,
            started_at=STARTED,
            ended_at=ENDED,
            outcome=ScheduledRunOutcome.FAILURE,
            attempts=2,
            manual=False,
            error="x" * (RUN_ERROR_MAX_LENGTH + 500),
        )
        assert row.error is not None
        assert len(row.error) == RUN_ERROR_MAX_LENGTH

    async def test_an_empty_error_is_stored_as_absent(self) -> None:
        row = await ScheduledActionRunRepository(_db()).record(
            scheduled_action_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            slot_at=SLOT,
            started_at=STARTED,
            ended_at=ENDED,
            outcome=ScheduledRunOutcome.SKIPPED_CONDITION,
            attempts=0,
            manual=False,
            error="",
        )
        assert row.error is None


class TestPurge:
    async def test_reports_how_many_rows_went(self) -> None:
        db = _db()
        db.execute.return_value = MagicMock(rowcount=7)

        purged = await ScheduledActionRunRepository(db).purge_older_than(STARTED)

        assert purged == 7
        db.execute.assert_awaited_once()
        statement = db.execute.await_args.args[0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert compiled.startswith("DELETE FROM scheduled_action_runs")
        assert "started_at <" in compiled

    async def test_a_driver_without_a_rowcount_reports_zero(self) -> None:
        db = _db()
        db.execute.return_value = MagicMock(rowcount=None)
        assert await ScheduledActionRunRepository(db).purge_older_than(STARTED) == 0


class TestListSince:
    async def test_filters_by_account_and_lower_bound_oldest_first(self) -> None:
        db = _db()
        db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: ["r1", "r2"]))
        user_id = uuid.uuid4()

        rows = await ScheduledActionRunRepository(db).list_since(user_id, STARTED)

        assert rows == ["r1", "r2"]
        statement = db.execute.await_args.args[0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert f"user_id = '{user_id.hex}'" in compiled
        assert "started_at >=" in compiled
        assert "ORDER BY scheduled_action_runs.started_at ASC, scheduled_action_runs.id ASC" in (
            compiled
        )
