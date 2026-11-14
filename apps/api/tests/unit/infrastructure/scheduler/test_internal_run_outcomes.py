"""An unserved routine retains its condition facts and never reports successful work."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.users.schemas import UserProfile
from src.infrastructure.scheduler import scheduled_action_executor as executor
from src.infrastructure.scheduler.out_of_turn_run import RunOutcome, RunResult

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("trigger", ["time", "condition"])
@pytest.mark.parametrize(
    ("outcome", "reason"),
    [(RunOutcome.BUSY, "skipped_busy"), (RunOutcome.PENDING_QUESTION, "skipped_hitl")],
)
async def test_an_unserved_tick_neither_consumes_facts_nor_counts_execution(
    trigger: str, outcome: RunOutcome, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    owner = uuid4()
    action = ScheduledAction(
        id=uuid4(),
        user_id=owner,
        title="Test",
        action_prompt="A routine",
        trigger_kind=trigger,
        execution_mode="react",
    )
    user = UserProfile(
        id=owner,
        email="test@example.com",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        created_at=now,
        updated_at=now,
        language="en",
        timezone="UTC",
    )
    db = AsyncMock(spec=AsyncSession)
    repo = AsyncMock(spec=ScheduledActionRepository)
    gate = executor._ConditionGate(None, {"seen": ["fact"]}, {"seen": []})
    rearm = AsyncMock(return_value=True)
    record = AsyncMock()
    mark = AsyncMock()
    monkeypatch.setattr(executor, "stream_instruction", AsyncMock(return_value=RunResult(outcome)))
    monkeypatch.setattr(executor, "_rearm_reserved", rearm)
    monkeypatch.setattr(executor, "record_run", record)
    monkeypatch.setattr(executor, "_mark_routine", mark)
    monkeypatch.setattr(executor, "_settle_superseded", AsyncMock(return_value=False))

    tick = executor._Tick(db=db, repo=repo, action=action, token=None, due_at=now, started_at=now)

    answer = await executor._run_pipeline(tick, user, gate=gate, user_language="en")

    # Nothing to push, and nothing to tell: a tick that stood aside is no failure.
    assert (answer.text, answer.notice) == ("", None)
    mark.assert_not_awaited()
    rearm.assert_awaited_once_with(repo, action, None, now, gate.unserved_state)
    if trigger == "condition":
        record.assert_not_awaited()
    else:
        record.assert_awaited_once()
        assert record.call_args.kwargs["outcome"].value == reason
        assert record.call_args.kwargs["attempts"] == 0
