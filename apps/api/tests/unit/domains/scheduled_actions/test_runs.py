"""``record_run``: one row per executor exit, inside a savepoint (ADR-265)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.scheduled_actions.models import ScheduledRunOutcome
from src.domains.scheduled_actions.runs import record_run

pytestmark = pytest.mark.unit

# Monday 3 August 2026, 08:00 Paris = 06:00Z.
DUE = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)
STARTED = datetime(2026, 8, 3, 6, 0, 5, tzinfo=UTC)
ENDED = datetime(2026, 8, 3, 6, 0, 40, tzinfo=UTC)


class _Savepoint:
    """``async with db.begin_nested()`` double that records entry and exit."""

    def __init__(self) -> None:
        self.entered = False
        self.exited_with: object = None

    async def __aenter__(self) -> _Savepoint:
        self.entered = True
        return self

    async def __aexit__(self, exc_type: object, *_: object) -> bool:
        self.exited_with = exc_type
        return False


def _action(**over: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "days_of_week": [1, 2, 3, 4, 5],
        "trigger_hour": 8,
        "trigger_minute": 0,
        "user_timezone": "Europe/Paris",
    }
    base.update(over)
    return SimpleNamespace(**base)


def _db() -> tuple[MagicMock, _Savepoint]:
    savepoint = _Savepoint()
    db = MagicMock()
    db.begin_nested = MagicMock(return_value=savepoint)
    return db, savepoint


async def _record(db: MagicMock, action: SimpleNamespace, **over: Any) -> Any:
    kwargs: dict[str, Any] = {
        "due_at": DUE,
        "started_at": STARTED,
        "outcome": ScheduledRunOutcome.SUCCESS,
        "attempts": 1,
    }
    kwargs.update(over)
    with (
        patch("src.domains.scheduled_actions.runs.now_utc", return_value=ENDED),
        patch("src.domains.scheduled_actions.runs.ScheduledActionRunRepository") as repo_cls,
    ):
        repo_cls.return_value.record = AsyncMock(return_value="row")
        result = await record_run(db, action, **kwargs)
    return result, repo_cls.return_value.record


class TestTheRow:
    async def test_a_due_run_serves_its_due_instant_inside_a_savepoint(self) -> None:
        db, savepoint = _db()
        action = _action()

        result, record = await _record(db, action)

        assert result == "row"
        assert savepoint.entered and savepoint.exited_with is None
        record.assert_awaited_once_with(
            scheduled_action_id=action.id,
            user_id=action.user_id,
            slot_at=DUE,
            started_at=STARTED,
            ended_at=ENDED,
            outcome=ScheduledRunOutcome.SUCCESS,
            attempts=1,
            manual=False,
            error=None,
        )

    async def test_a_manual_run_after_the_slot_serves_the_day_slot(self) -> None:
        db, _ = _db()
        # Nothing due until tomorrow; started at 12:00 local, after 08:00.
        _, record = await _record(
            db,
            _action(),
            due_at=datetime(2026, 8, 4, 6, 0, tzinfo=UTC),
            started_at=datetime(2026, 8, 3, 10, 0, tzinfo=UTC),
        )
        kwargs = record.await_args.kwargs
        assert kwargs["manual"] is True
        assert kwargs["slot_at"] == DUE

    async def test_a_rehearsal_before_the_slot_serves_nothing(self) -> None:
        db, _ = _db()
        _, record = await _record(
            db,
            _action(),
            due_at=DUE,
            started_at=datetime(2026, 8, 3, 5, 0, tzinfo=UTC),  # 07:00 local
        )
        kwargs = record.await_args.kwargs
        assert kwargs["manual"] is True
        assert kwargs["slot_at"] is None

    async def test_a_failure_carries_its_attempts_and_error(self) -> None:
        db, _ = _db()
        _, record = await _record(
            db,
            _action(),
            outcome=ScheduledRunOutcome.FAILURE,
            attempts=2,
            error="TimeoutError: boom",
        )
        kwargs = record.await_args.kwargs
        assert kwargs["outcome"] is ScheduledRunOutcome.FAILURE
        assert (kwargs["attempts"], kwargs["error"]) == (2, "TimeoutError: boom")


class TestTheHistoryNeverGatesTheRoutine:
    async def test_a_failed_write_is_logged_and_confined_to_the_savepoint(self) -> None:
        db, savepoint = _db()
        action = _action()
        with (
            patch("src.domains.scheduled_actions.runs.now_utc", return_value=ENDED),
            patch("src.domains.scheduled_actions.runs.ScheduledActionRunRepository") as repo_cls,
            patch("src.domains.scheduled_actions.runs.logger") as log,
        ):
            repo_cls.return_value.record = AsyncMock(side_effect=RuntimeError("disk full"))
            result = await record_run(
                db,
                action,
                due_at=DUE,
                started_at=STARTED,
                outcome=ScheduledRunOutcome.SUCCESS,
                attempts=1,
            )

        assert result is None
        # The exception crossed the savepoint boundary (so it rolled back) and
        # stopped there.
        assert savepoint.exited_with is RuntimeError
        log.warning.assert_called_once()
        assert log.warning.call_args.args[0] == "scheduled_action_run_record_failed"
        assert log.warning.call_args.kwargs["outcome"] == "success"
