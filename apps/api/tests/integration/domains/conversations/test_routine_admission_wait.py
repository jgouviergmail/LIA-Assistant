"""A routine waits for durable account occupancy, including another discussion."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import RunAdmission
from src.core.run_authority import RunAuthority, current_run_authority, run_authority_scope
from src.domains.agents.application import routine_execution
from src.domains.agents.application import routine_execution_policy as policy
from src.domains.agents.application.routine_schemas import RoutineSnapshot

pytestmark = pytest.mark.integration


async def test_missing_redis_lock_is_not_permission_to_start_a_reserved_routine(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db
            await db.commit()

    monkeypatch.setattr(policy, "get_db_context", session)
    allowed = await policy.wait_for_routine_turn(
        reserved.target.owner_id, datetime.now(UTC) + timedelta(milliseconds=100)
    )
    assert allowed is False


async def test_a_deferred_routine_never_borrows_the_confirming_graphs_authority(
    reserved: RunAdmission, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = asyncio.Event()
    seen: list[RunAuthority | None] = []
    reservation = policy.RoutineExecutionReservation(
        reserved.target.owner_id,
        RoutineSnapshot(id=uuid4(), title="Run", enabled=True, configuration_digest="a" * 64),
        uuid4(),
        datetime.now(UTC) + timedelta(minutes=1),
    )

    async def observe(actual: policy.RoutineExecutionReservation) -> None:
        assert actual == reservation
        seen.append(current_run_authority())
        done.set()

    monkeypatch.setattr(routine_execution, "_run_reserved", observe)
    with run_authority_scope(RunAuthority(reserved)):
        routine_execution._start_reserved_run(reservation)
    async with asyncio.timeout(2):
        await done.wait()
    assert seen == [None]
