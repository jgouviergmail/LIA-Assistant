"""A still-current conversation does not authorize a closed invocation's writes."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionPhase, ExecutionRevoked, RunAdmission, RunEnd
from src.core.run_authority import RunAuthority, run_authority_scope
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.instrumented_checkpointer import InstrumentedAsyncPostgresSaver
from src.domains.conversations.runtime_identity import checkpoint_config
from src.domains.conversations.runtime_store import RuntimeAsyncPostgresStore
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration
WriteKind = Literal["checkpoint", "pending", "store"]


@pytest.fixture
async def admission(async_engine: AsyncEngine, committed_user_ids: list[UUID]) -> RunAdmission:
    """Commit a genuine fenced execution, with no mocked ownership boundary."""
    (target,) = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    async with AsyncSession(async_engine) as db:
        result = await ConversationExecutionRepository(db).admit(
            target, run_id=str(uuid4()), stream_id=str(uuid4()), worker_id=uuid4()
        )
        assert isinstance(result, RunAdmission)
        await db.commit()
    return result


@asynccontextmanager
async def native_writer(
    connection: AsyncConnection[DictRow], admission: RunAdmission, kind: WriteKind
) -> AsyncIterator[Callable[[], Awaitable[None]]]:
    """Prepare while authorized; exercise each native write door independently."""
    target = admission.target
    if kind == "store":
        store = RuntimeAsyncPostgresStore(connection)

        async def write_store() -> None:
            await store.aput(
                (str(target.owner_id), str(target.runtime_id), "context", "event"),
                "list",
                {"items": ["private working state"]},
                index=False,
            )

        try:
            yield write_store
        finally:
            await store.aclose()
        return
    saver = InstrumentedAsyncPostgresSaver(connection)
    config = checkpoint_config(target)
    if kind == "checkpoint":

        async def write_checkpoint() -> None:
            await saver.aput(config, empty_checkpoint(), {"source": "input", "step": 0}, {})

        yield write_checkpoint
    else:
        saved = await saver.aput(config, empty_checkpoint(), {"source": "input", "step": 0}, {})

        async def write_pending() -> None:
            await saver.aput_writes(saved, [("result", {"value": 1})], "pending-task")

        yield write_pending


@pytest.mark.parametrize("kind", ["checkpoint", "pending", "store"])
async def test_closed_execution_cannot_write_even_if_the_runtime_is_still_current(
    native_connection: AsyncConnection[DictRow],
    async_engine: AsyncEngine,
    admission: RunAdmission,
    kind: WriteKind,
) -> None:
    with run_authority_scope(RunAuthority(admission)):
        async with native_writer(native_connection, admission, kind) as write:
            await write()
            async with AsyncSession(async_engine) as db:
                assert await ConversationExecutionRepository(db).close_owned(
                    admission, end=RunEnd.NORMAL
                )
                await db.commit()
            with pytest.raises(ExecutionRevoked):
                await write()


@pytest.mark.parametrize("kind", ["checkpoint", "pending", "store"])
async def test_no_invocation_identity_is_not_permission_to_write(
    native_connection: AsyncConnection[DictRow],
    admission: RunAdmission,
    kind: WriteKind,
) -> None:
    with run_authority_scope(RunAuthority(admission)):
        async with native_writer(native_connection, admission, kind) as write:
            with run_authority_scope(None), pytest.raises(ExecutionRevoked):
                await write()


@pytest.mark.parametrize("kind", ["checkpoint", "pending", "store"])
@pytest.mark.parametrize("phase", [ExecutionPhase.DRAINING, ExecutionPhase.RECOVERING])
async def test_nonrunning_execution_keeps_the_slot_but_cannot_write(
    native_connection: AsyncConnection[DictRow],
    async_engine: AsyncEngine,
    admission: RunAdmission,
    kind: WriteKind,
    phase: ExecutionPhase,
) -> None:
    with run_authority_scope(RunAuthority(admission)):
        async with native_writer(native_connection, admission, kind) as write:
            async with AsyncSession(async_engine) as db:
                repository = ConversationExecutionRepository(db)
                changed = (
                    await repository.mark_draining(admission)
                    if phase == ExecutionPhase.DRAINING
                    else await repository.mark_recovering(admission)
                )
                assert changed
                await db.commit()
            with pytest.raises(ExecutionRevoked):
                await write()


@pytest.mark.parametrize("kind", ["checkpoint", "pending", "store"])
async def test_local_revocation_stops_children_before_the_sql_transition(
    native_connection: AsyncConnection[DictRow],
    admission: RunAdmission,
    kind: WriteKind,
) -> None:
    authority = RunAuthority(admission)
    with run_authority_scope(authority):
        async with native_writer(native_connection, admission, kind) as write:
            authority.revoked = True
            with pytest.raises(ExecutionRevoked):
                await write()
