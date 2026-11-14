"""The close writes how the run ended and settles what waited, in one transaction (ADR-384)."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE
from src.core.conversation_execution import RunAdmission, RunEnd
from src.core.run_authority import current_run_authority
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus
from src.domains.conversations.waiting_repository import WaitingMessageRepository
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.streaming import release_listener, run_admission

pytestmark = pytest.mark.integration


class Heard:
    """A release listener that remembers what it was told."""

    def __init__(self) -> None:
        self.releases: list[tuple[UUID, RunEnd]] = []
        self.event = asyncio.Event()

    async def __call__(self, owner_id: UUID, end: RunEnd) -> None:
        self.releases.append((owner_id, end))
        self.event.set()


@pytest.fixture
def heard(monkeypatch: pytest.MonkeyPatch) -> Heard:
    listener = Heard()
    monkeypatch.setattr(release_listener, "_listener", listener)
    return listener


async def keep_waiting(engine: AsyncEngine, admission: RunAdmission, text: str) -> WaitingMessage:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        row, _ = await WaitingMessageRepository(db).keep(
            admission.target, text, rendering=None, status=WaitingStatus.WAITING
        )
        await db.commit()
        return row


async def end_of(engine: AsyncEngine, admission: RunAdmission) -> RunEnd | None:
    async with AsyncSession(engine) as db:
        return await db.scalar(
            select(ConversationExecution.end_state).where(
                ConversationExecution.id == admission.activity_id
            )
        )


async def status_of(engine: AsyncEngine, row_id: UUID) -> WaitingStatus | None:
    async with AsyncSession(engine) as db:
        return await db.scalar(select(WaitingMessage.status).where(WaitingMessage.id == row_id))


@pytest.mark.parametrize(
    ("declared", "written", "after"),
    [
        (RunEnd.NORMAL, RunEnd.NORMAL, WaitingStatus.WAITING),
        (RunEnd.INTERRUPTED, RunEnd.INTERRUPTED, WaitingStatus.HELD),
        (None, RunEnd.INTERRUPTED, WaitingStatus.HELD),
    ],
)
async def test_the_close_writes_the_declared_end_and_settles_what_waited(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    heard: Heard,
    declared: RunEnd | None,
    written: RunEnd,
    after: WaitingStatus,
) -> None:
    waiting = await keep_waiting(async_engine, reserved, "and the bakery")
    async with run_admission.owned_execution(reserved):
        authority = current_run_authority()
        assert authority is not None
        authority.end = declared
    assert await end_of(async_engine, reserved) == written
    assert await status_of(async_engine, waiting.id) == after
    async with asyncio.timeout(5):
        await heard.event.wait()
    assert heard.releases == [(reserved.target.owner_id, written)]


async def test_an_unstarted_release_gives_back_its_departure_and_holds_nothing(
    reserved: RunAdmission, async_engine: AsyncEngine, heard: Heard
) -> None:
    claimed = await keep_waiting(async_engine, reserved, "leaving")
    async with AsyncSession(async_engine) as db:
        assert await WaitingMessageRepository(db).claim(
            claimed.id, claimed.version, stream_id=reserved.stream_id
        )
        await db.commit()
    await run_admission.release_unstarted_execution(reserved)
    assert await end_of(async_engine, reserved) == RunEnd.UNSTARTED
    assert await status_of(async_engine, claimed.id) == WaitingStatus.WAITING
    async with asyncio.timeout(5):
        await heard.event.wait()
    assert heard.releases == [(reserved.target.owner_id, RunEnd.UNSTARTED)]


async def test_a_message_kept_while_the_close_waits_for_the_account_is_settled_by_it(
    reserved: RunAdmission, async_engine: AsyncEngine, heard: Heard
) -> None:
    """The close takes the owner lock the keep takes: neither misses the other."""
    async with AsyncSession(async_engine, expire_on_commit=False) as keeper:
        await hold_owner_lock(keeper, CONVERSATION_OWNER_LOCK_SCOPE, reserved.target.owner_id)
        row, _ = await WaitingMessageRepository(keeper).keep(
            reserved.target, "kept during the close", rendering=None, status=WaitingStatus.WAITING
        )
        closing = asyncio.create_task(_close_interrupted(reserved))
        await asyncio.sleep(0.3)
        assert not closing.done(), "the close settled what waited without the owner lock"
        await keeper.commit()
    await asyncio.wait_for(closing, timeout=5)
    assert await status_of(async_engine, row.id) == WaitingStatus.HELD


async def _close_interrupted(admission: RunAdmission) -> None:
    async with run_admission.owned_execution(admission) as authority:
        authority.end = RunEnd.INTERRUPTED


async def test_a_departures_own_unstarted_release_is_not_announced(
    reserved: RunAdmission, async_engine: AsyncEngine, heard: Heard
) -> None:
    """The departure handles its own refusals; a release it made starts no new chain."""
    await run_admission.release_unstarted_execution(reserved, announce=False)
    assert await end_of(async_engine, reserved) == RunEnd.UNSTARTED
    await asyncio.sleep(0.2)
    assert heard.releases == []
