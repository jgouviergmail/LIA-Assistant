"""Queued authorization uses live rows and cannot release a newer reservation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.routine_execution_policy import (
    RoutineExecutionReservation,
    authorize_reserved_routine,
)
from src.domains.agents.application.routine_operations import routine_snapshot
from src.domains.scheduled_actions.schemas import ConditionConfig, ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention", ["none", "changed", "off", "expired", "inactive", "new_token", "ledger"]
)
async def test_queued_worker_reads_current_authority_and_cancels_only_its_own_reservation(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    source = ScheduledActionService(async_session)
    row = await source.create(
        test_user.id,
        ScheduledActionCreate(
            title="Run",
            action_prompt="Read tasks",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue"),
        ),
        "Europe/Paris",
    )
    expected, actor_id, row_id = routine_snapshot(row), test_user.id, row.id
    await source.reserve_manual_execution(row_id, actor_id)
    token = row.execution_token
    assert token is not None
    expires = datetime.now(UTC) + timedelta(minutes=1)
    if intervention == "changed":
        row.action_prompt = "New instruction"
    elif intervention == "off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif intervention == "expired":
        expires = datetime.now(UTC) - timedelta(seconds=1)
    elif intervention == "inactive":
        test_user.is_active = False
    elif intervention == "new_token":
        row.execution_token = uuid4()
    elif intervention == "ledger":
        row.condition_state = {"seen": ["private-fact"]}
    await async_session.commit()
    reservation = RoutineExecutionReservation(actor_id, expected, token, expires)
    allowed = await authorize_reserved_routine(reservation, async_session, row)
    assert allowed is (intervention in {"none", "ledger"})
    stored = await ScheduledActionService(async_session).get_with_ownership_check(row_id, actor_id)
    assert (stored.status == "executing") is (allowed or intervention == "new_token")
    if intervention == "changed":
        assert stored.action_prompt == "New instruction"
    if intervention == "new_token":
        assert stored.execution_token is not None and stored.execution_token != token
