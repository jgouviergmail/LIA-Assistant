"""A queued run cannot consume a newer reservation or its originating chat turn."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.routine_execution_policy import (
    RoutineExecutionReservation,
    authorize_reserved_routine,
    wait_for_routine_turn,
)
from src.domains.agents.application.routine_schemas import RoutineSnapshot
from src.domains.scheduled_actions.models import ScheduledAction

pytestmark = pytest.mark.unit


async def test_queued_run_waits_for_the_confirming_chat_to_release_its_lock() -> None:
    redis = AsyncMock()
    redis.exists.side_effect = [True, True, False]
    with patch(
        "src.domains.agents.application.routine_execution_policy.asyncio.sleep", AsyncMock()
    ) as sleep:
        result = await wait_for_routine_turn(
            redis, str(uuid4()), datetime.now(UTC) + timedelta(minutes=1)
        )
    assert result and redis.exists.await_count == 3 and sleep.await_count == 2


async def test_an_expired_queued_run_never_touches_the_chat_or_starts_a_worker() -> None:
    redis = AsyncMock()
    assert not await wait_for_routine_turn(
        redis, str(uuid4()), datetime.now(UTC) - timedelta(seconds=1)
    )
    redis.exists.assert_not_awaited()


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
