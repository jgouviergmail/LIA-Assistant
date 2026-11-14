"""A queued run cannot consume a newer reservation or its originating chat turn."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionKind, ExecutionPhase, RunBusy
from src.core.conversation_target import ConversationKind, ConversationRef
from src.domains.agents.application.routine_execution_policy import (
    RoutineExecutionReservation,
    authorize_reserved_routine,
    wait_for_routine_turn,
)
from src.domains.agents.application.routine_schemas import RoutineSnapshot
from src.domains.scheduled_actions.models import ScheduledAction

pytestmark = pytest.mark.unit


async def test_queued_run_waits_for_the_confirming_chat_to_release_its_lock() -> None:
    opened: list[bool] = []
    owner = uuid4()
    occupied = RunBusy(
        ConversationRef(owner, uuid4(), ConversationKind.SECONDARY, 0, uuid4()),
        ExecutionKind.GRAPH,
        ExecutionPhase.RUNNING,
        "run",
        None,
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        opened.append(True)
        try:
            yield AsyncMock(spec=AsyncSession)
        finally:
            opened.pop()

    async def sleep_without_session(_: float) -> None:
        assert not opened

    with (
        patch("src.domains.agents.application.routine_execution_policy.get_db_context", session),
        patch(
            "src.domains.agents.application.routine_execution_policy.asyncio.sleep",
            AsyncMock(side_effect=sleep_without_session),
        ) as sleep,
        patch(
            "src.domains.conversations.execution_repository.ConversationExecutionRepository.active_for_owner",
            AsyncMock(side_effect=[occupied, occupied, None]),
        ) as occupancy,
    ):
        result = await wait_for_routine_turn(owner, datetime.now(UTC) + timedelta(minutes=1))
    assert result and occupancy.await_count == 3 and sleep.await_count == 2
    assert all(call.args == (owner,) for call in occupancy.await_args_list)


async def test_an_expired_queued_run_never_touches_the_chat_or_starts_a_worker() -> None:
    with patch(
        "src.domains.agents.application.routine_execution_policy.get_db_context"
    ) as sessions:
        assert not await wait_for_routine_turn(uuid4(), datetime.now(UTC) - timedelta(seconds=1))
    sessions.assert_not_called()


async def test_expiry_during_the_final_authority_read_refuses_inference() -> None:
    now = datetime.now(UTC)
    expected = RoutineSnapshot(id=uuid4(), title="Run", enabled=True, configuration_digest="a" * 64)
    reservation = RoutineExecutionReservation(
        uuid4(), expected, uuid4(), now + timedelta(minutes=1)
    )
    action = ScheduledAction(
        id=expected.id,
        user_id=reservation.actor_id,
        status="executing",
        execution_token=reservation.token,
    )
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=action))
    release = AsyncMock(return_value=True)
    with (
        patch("src.domains.agents.application.routine_execution_policy.datetime") as clock,
        patch("src.domains.agents.application.routine_execution_policy.load_actor", AsyncMock()),
        patch(
            "src.domains.agents.application.routine_execution_policy.require_application_tools",
            AsyncMock(),
        ),
        patch(
            "src.domains.agents.application.routine_execution_policy.routine_snapshot",
            Mock(return_value=expected),
        ),
        patch(
            "src.domains.agents.application.routine_execution_policy.ScheduledActionRepository"
        ) as source,
    ):
        source.return_value.release_manual_execution = release
        clock.now.side_effect = [now, now + timedelta(minutes=2)]
        assert not await authorize_reserved_routine(reservation, db, action)
    release.assert_awaited_once_with(expected.id, reservation.actor_id, reservation.token)
