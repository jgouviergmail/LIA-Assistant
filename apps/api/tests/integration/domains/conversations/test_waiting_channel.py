"""Words written on a channel while LIA works wait their turn too (Telegram lot 34, ADR-384).

On real PostgreSQL: the keep reads the account's occupancy under the owner lock
the close takes, the words are kept for Main with the channel they were written
on, and the two answers of a held message — send it now, withdraw it — act on
THE message the person was shown, never on one that replaced it.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.constants import CHAT_MESSAGE_MAX_LENGTH
from src.core.conversation_execution import RunAdmission
from src.core.conversation_target import ConversationKind
from src.domains.agents.api import waiting_channel, waiting_requests
from src.domains.agents.api.waiting_channel import act_on_waiting, keep_from_channel
from src.domains.agents.api.waiting_departure import Departure, DepartureResult
from src.domains.conversations.models import Conversation
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus
from src.domains.conversations.waiting_repository import WaitingMessageRepository
from src.infrastructure.channels.assistant_gateway import (
    ChannelKeep,
    WaitingAction,
    WaitingActionOutcome,
)
from src.infrastructure.database import session
from src.infrastructure.streaming.run_admission import release_unstarted_execution

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def production_sessions(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )


class Departures:
    """The departure, recorded: its own SQL and Redis contracts are proven elsewhere."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.sent: list[UUID] = []

        async def depart(_owner: UUID, candidate: object) -> DepartureResult:
            self.sent.append(candidate.id)  # type: ignore[attr-defined]
            return DepartureResult(Departure.SENT)

        monkeypatch.setattr(waiting_channel, "depart", depart)
        monkeypatch.setattr(waiting_requests, "depart", depart)


@pytest.fixture
def departures(monkeypatch: pytest.MonkeyPatch) -> Departures:
    return Departures(monkeypatch)


async def main_of(engine: AsyncEngine, owner_id: UUID) -> UUID:
    async with AsyncSession(engine) as db:
        main = await db.scalar(
            select(Conversation.id).where(
                Conversation.user_id == owner_id, Conversation.kind == ConversationKind.MAIN
            )
        )
    assert main is not None
    return main


async def waiting(engine: AsyncEngine, owner_id: UUID) -> list[WaitingMessage]:
    async with AsyncSession(engine) as db:
        return list(
            await db.scalars(select(WaitingMessage).where(WaitingMessage.user_id == owner_id))
        )


async def test_words_written_on_a_channel_while_lia_works_wait_to_be_answered_there(
    reserved: RunAdmission, async_engine: AsyncEngine, departures: Departures
) -> None:
    owner = reserved.target.owner_id

    first = await keep_from_channel(owner, "Add the dentist", "telegram")
    second = await keep_from_channel(owner, "and the bakery", "telegram")

    assert (first, second) == (ChannelKeep.KEPT, ChannelKeep.KEPT)
    [row] = await waiting(async_engine, owner)
    # A channel speaks in Main, whichever discussion the busy run works in.
    assert row.conversation_id == await main_of(async_engine, owner)
    assert row.conversation_id != reserved.target.id
    assert row.content == "Add the dentist\n\nand the bakery"
    assert row.status == WaitingStatus.WAITING
    assert row.reply_channel == "telegram"
    assert departures.sent == []


async def test_words_that_would_make_it_too_long_are_refused(
    reserved: RunAdmission, async_engine: AsyncEngine, departures: Departures
) -> None:
    owner = reserved.target.owner_id
    await keep_from_channel(owner, "x" * (CHAT_MESSAGE_MAX_LENGTH - 1), "telegram")

    assert await keep_from_channel(owner, "yz", "telegram") is ChannelKeep.TOO_LONG
    [row] = await waiting(async_engine, owner)
    assert len(row.content) == CHAT_MESSAGE_MAX_LENGTH - 1


async def test_a_message_being_sent_takes_no_more_words(
    reserved: RunAdmission, async_engine: AsyncEngine, departures: Departures
) -> None:
    owner = reserved.target.owner_id
    await keep_from_channel(owner, "leaving", "telegram")
    [row] = await waiting(async_engine, owner)
    async with AsyncSession(async_engine) as db:
        assert await WaitingMessageRepository(db).claim(row.id, row.version, stream_id="s")
        await db.commit()

    assert await keep_from_channel(owner, "late", "telegram") is ChannelKeep.DEPARTING


async def test_on_a_free_account_the_words_leave_at_once(
    reserved: RunAdmission, async_engine: AsyncEngine, departures: Departures
) -> None:
    """The run that refused the message ended meanwhile: nothing to wait for."""
    owner = reserved.target.owner_id
    await release_unstarted_execution(reserved, announce=False)

    assert await keep_from_channel(owner, "now", "telegram") is ChannelKeep.DEPARTED
    [row] = await waiting(async_engine, owner)
    assert departures.sent == [row.id]


async def _held(engine: AsyncEngine, owner: UUID) -> WaitingMessage:
    await keep_from_channel(owner, "held words", "telegram")
    [row] = await waiting(engine, owner)
    async with AsyncSession(engine) as db:
        row.status = WaitingStatus.HELD
        await db.merge(row)
        await db.commit()
    return row


async def test_withdrawing_removes_the_message_shown(
    reserved: RunAdmission, async_engine: AsyncEngine, departures: Departures
) -> None:
    owner = reserved.target.owner_id
    row = await _held(async_engine, owner)

    outcome = await act_on_waiting(owner, row.id, WaitingAction.WITHDRAW)

    assert outcome is WaitingActionOutcome.WITHDRAWN
    assert await waiting(async_engine, owner) == []


async def test_a_button_for_a_message_since_replaced_acts_on_nothing(
    reserved: RunAdmission, async_engine: AsyncEngine, departures: Departures
) -> None:
    owner = reserved.target.owner_id
    row = await _held(async_engine, owner)

    for action in WaitingAction:
        assert await act_on_waiting(owner, uuid4(), action) is WaitingActionOutcome.GONE
    [still] = await waiting(async_engine, owner)
    assert still.id == row.id and departures.sent == []


async def test_sending_while_lia_works_sends_it_first_at_the_release(
    reserved: RunAdmission, async_engine: AsyncEngine, departures: Departures
) -> None:
    owner = reserved.target.owner_id
    row = await _held(async_engine, owner)

    outcome = await act_on_waiting(owner, row.id, WaitingAction.SEND)

    assert outcome is WaitingActionOutcome.QUEUED
    [marked] = await waiting(async_engine, owner)
    assert marked.send_requested_at is not None and departures.sent == []


async def test_sending_on_a_free_account_sends_it_now(
    reserved: RunAdmission, async_engine: AsyncEngine, departures: Departures
) -> None:
    owner = reserved.target.owner_id
    row = await _held(async_engine, owner)
    await release_unstarted_execution(reserved, announce=False)

    assert await act_on_waiting(owner, row.id, WaitingAction.SEND) is WaitingActionOutcome.SENT
    assert departures.sent == [row.id]


async def test_a_question_waiting_there_is_answered_first(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    departures: Departures,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = reserved.target.owner_id
    row = await _held(async_engine, owner)

    async def asked(_runtime_id: str) -> str:
        return "run-that-asked"

    monkeypatch.setattr(waiting_requests, "pending_run_id", asked)

    assert await act_on_waiting(owner, row.id, WaitingAction.SEND) is (
        WaitingActionOutcome.QUESTION
    )
    [still] = await waiting(async_engine, owner)
    assert still.send_requested_at is None and departures.sent == []
