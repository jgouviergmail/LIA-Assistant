"""Actual source results override forecasts, including a committed partial failure."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.application import draft_execution
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.habit_action_schemas import (
    HabitStatusChange,
    HabitStatusPatch,
    HabitStatusValues,
    habit_after,
)
from src.domains.agents.application.habit_spec import HABIT_STATUS_OPERATION
from src.domains.habits.management_commands import ManagedHabit
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("partial", [False, True])
async def test_actual_source_values_survive_success_and_post_commit_failure(
    monkeypatch: pytest.MonkeyPatch, partial: bool
) -> None:
    source = ManagedHabit(
        id=uuid4(),
        kind="recurring_request",
        key="email",
        payload={},
        status="active",
        positive_signals=0,
        negative_signals=0,
        last_observed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    change = HabitStatusChange(status="blocked")
    draft = build_action_content(
        uuid4(),
        HABIT_STATUS_OPERATION,
        HabitStatusPatch(habit=HabitStatusValues(expected=source, status=change)),
        {"habit": source.model_dump(mode="json")},
        habit_after(source, change),
    )
    actual = {"stored_records_erased": True, "advisory_cleanup_confirmed": not partial}

    @asynccontextmanager
    async def db() -> AsyncIterator[object]:
        yield object()

    async def execute(db, actor, draft, receipt):
        receipt.committed = True
        receipt.values = actual
        if partial:
            raise CommandRejected("ADVISORY_CLEANUP_FAILED")

    monkeypatch.setattr(draft_execution, "get_db_context", db)
    monkeypatch.setattr(draft_execution, "require_application_tools", AsyncMock())
    monkeypatch.setattr(draft_execution, "execute_habit_action", execute)
    receipt = PreferenceWriteReceipt()
    result = await draft_execution._execute_outcome(draft, draft.actor_id, receipt)
    assert result.committed and result.success is (not partial)
    assert result.values == actual
    assert result.error_code == ("POST_COMMIT_FAILURE" if partial else None)
