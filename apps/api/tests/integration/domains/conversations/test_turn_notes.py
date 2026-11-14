"""A waiting message joins the answer being written, on real PostgreSQL (ADR-385)."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.constants import WAITING_MESSAGE_SEPARATOR
from src.core.conversation_execution import RunAdmission, RunEnd
from src.core.conversation_target import ConversationRef
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus
from src.domains.conversations.waiting_repository import WaitingMessageRepository
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration


@pytest.fixture
async def two_discussions(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> tuple[ConversationRef, ConversationRef]:
    """Two discussions of one account."""
    [first] = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    second = replace(first, id=uuid4(), runtime_id=uuid4())
    async with AsyncSession(async_engine) as db:
        db.add(
            Conversation(
                id=second.id,
                user_id=second.owner_id,
                kind=second.kind,
                title="Second",
                revision=second.revision,
                runtime_id=second.runtime_id,
            )
        )
        await db.commit()
    return first, second


async def admit(engine: AsyncEngine, target: ConversationRef) -> RunAdmission:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        admission = await ConversationExecutionRepository(db).admit(
            target, run_id=str(uuid4()), stream_id=str(uuid4()), worker_id=uuid4()
        )
        assert isinstance(admission, RunAdmission)
        await db.commit()
        return admission


async def keep(engine: AsyncEngine, target: ConversationRef, text: str) -> WaitingMessage:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        row, _ = await WaitingMessageRepository(db).keep(
            target, text, rendering=None, status=WaitingStatus.WAITING
        )
        await db.commit()
        return row


async def only_row(engine: AsyncEngine, owner_id: UUID) -> WaitingMessage | None:
    async with AsyncSession(engine) as db:
        return await db.scalar(select(WaitingMessage).where(WaitingMessage.user_id == owner_id))


async def accepts_notes(engine: AsyncEngine, admission: RunAdmission) -> bool:
    async with AsyncSession(engine) as db:
        row = await db.get(ConversationExecution, admission.activity_id)
        assert row is not None
        return row.accepts_notes


async def open_notes(engine: AsyncEngine, admission: RunAdmission) -> bool:
    async with AsyncSession(engine) as db:
        opened = await ConversationExecutionRepository(db).open_notes(admission)
        await db.commit()
        return opened


async def join(
    engine: AsyncEngine, target: ConversationRef, version: int, stream_id: str
) -> WaitingMessage | None:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        joined = await WaitingMessageRepository(db).join(
            target.owner_id, target.id, version=version, stream_id=stream_id
        )
        await db.commit()
        return joined


# --- The invocation's notes -----------------------------------------------------------


async def test_a_running_invocation_opens_and_closes_its_notes_once(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    admission = await admit(async_engine, two_discussions[0])
    assert not await accepts_notes(async_engine, admission)
    assert await open_notes(async_engine, admission)
    assert not await open_notes(async_engine, admission)
    assert await accepts_notes(async_engine, admission)
    async with AsyncSession(async_engine) as db:
        repository = ConversationExecutionRepository(db)
        assert await repository.close_notes(admission)
        assert not await repository.close_notes(admission)
        await db.commit()
    assert not await accepts_notes(async_engine, admission)


async def test_a_stale_identity_opens_nothing(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    admission = await admit(async_engine, two_discussions[0])
    stale = replace(admission, owner_token=uuid4())
    assert not await open_notes(async_engine, stale)
    assert not await accepts_notes(async_engine, admission)


@pytest.mark.parametrize("transition", ["mark_draining", "mark_recovering", "close_owned"])
async def test_every_transition_away_from_running_withdraws_the_notes(
    async_engine: AsyncEngine,
    two_discussions: tuple[ConversationRef, ConversationRef],
    transition: str,
) -> None:
    admission = await admit(async_engine, two_discussions[0])
    assert await open_notes(async_engine, admission)
    async with AsyncSession(async_engine) as db:
        repository = ConversationExecutionRepository(db)
        if transition == "close_owned":
            assert await repository.close_owned(admission, end=RunEnd.NORMAL)
        else:
            assert await getattr(repository, transition)(admission)
        await db.commit()
    assert not await accepts_notes(async_engine, admission)


async def test_only_a_running_invocation_takes_notes_in_sql(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    admission = await admit(async_engine, two_discussions[0])
    async with AsyncSession(async_engine) as db:
        assert await ConversationExecutionRepository(db).mark_draining(admission)
        await db.commit()
    async with AsyncSession(async_engine) as db:
        row = await db.get(ConversationExecution, admission.activity_id)
        assert row is not None
        row.accepts_notes = True
        with pytest.raises(IntegrityError):
            await db.flush()


async def test_the_note_stream_is_the_running_answer_of_this_discussion_only(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    first, second = two_discussions
    admission = await admit(async_engine, first)
    async with AsyncSession(async_engine) as db:
        repository = ConversationExecutionRepository(db)
        # Notes not open yet: nothing to join.
        assert await repository.note_stream(first.owner_id, first) is None
    assert await open_notes(async_engine, admission)
    async with AsyncSession(async_engine) as db:
        repository = ConversationExecutionRepository(db)
        assert await repository.note_stream(first.owner_id, first) == admission.stream_id
        assert await repository.note_stream(first.owner_id, second) is None
        older = replace(first, revision=first.revision + 1)
        assert await repository.note_stream(first.owner_id, older) is None
        assert await repository.note_stream(uuid4(), first) is None


# --- The waiting message --------------------------------------------------------------


async def test_a_message_joins_with_the_version_the_person_saw(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    first = two_discussions[0]
    row = await keep(async_engine, first, "only the ones open on Sunday")
    assert await join(async_engine, first, row.version + 1, "run") is None
    joined = await join(async_engine, first, row.version, "run")
    assert joined is not None
    assert joined.status == WaitingStatus.JOINING and joined.stream_id == "run"
    assert joined.content == "only the ones open on Sunday"
    # Joining twice is not joining another run.
    assert await join(async_engine, first, joined.version, "other") is None


async def test_a_held_message_may_join_too(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    first = two_discussions[0]
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        row, _ = await WaitingMessageRepository(db).keep(
            first, "held words", rendering=None, status=WaitingStatus.HELD
        )
        await db.commit()
    joined = await join(async_engine, first, row.version, "run")
    assert joined is not None and joined.status == WaitingStatus.JOINING


async def test_a_departing_message_never_joins(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    first = two_discussions[0]
    row = await keep(async_engine, first, "leaving")
    async with AsyncSession(async_engine) as db:
        assert await WaitingMessageRepository(db).claim(row.id, row.version, stream_id="sending")
        await db.commit()
    assert await join(async_engine, first, row.version, "run") is None
    stays = await only_row(async_engine, first.owner_id)
    assert stays is not None and stays.status == WaitingStatus.DEPARTING


async def test_a_joining_message_still_takes_words_an_edit_and_a_withdrawal(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    first = two_discussions[0]
    row = await keep(async_engine, first, "only Sunday")
    joined = await join(async_engine, first, row.version, "run")
    assert joined is not None
    added = await keep(async_engine, first, "and near the station")
    assert added.status == WaitingStatus.JOINING and added.stream_id == "run"
    assert added.content == f"only Sunday{WAITING_MESSAGE_SEPARATOR}and near the station"
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        repository = WaitingMessageRepository(db)
        edited = await repository.replace_text(
            first.owner_id, first.id, "only Saturday", version=added.version
        )
        assert edited is not None and edited.status == WaitingStatus.JOINING
        assert await repository.withdraw(first.owner_id, first.id)
        await db.commit()
    assert await only_row(async_engine, first.owner_id) is None


async def test_a_joining_message_never_departs_and_is_never_sent_now(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    first = two_discussions[0]
    row = await keep(async_engine, first, "a note")
    joined = await join(async_engine, first, row.version, "run")
    assert joined is not None
    async with AsyncSession(async_engine) as db:
        repository = WaitingMessageRepository(db)
        assert not await repository.claim(row.id, joined.version, stream_id="departure")
        assert await repository.request_send(first.owner_id, first.id) is None
        for end in RunEnd:
            assert await repository.departure_candidates(first.owner_id, end) == []


async def test_a_joining_message_holds_its_stream_in_sql(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    first = two_discussions[0]
    async with AsyncSession(async_engine) as db:
        db.add(
            WaitingMessage(
                user_id=first.owner_id,
                conversation_id=first.id,
                conversation_revision=first.revision,
                content="a note",
                status=WaitingStatus.JOINING,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()


async def test_the_loop_takes_only_its_own_notes_and_only_once(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    first, second = two_discussions
    mine = await keep(async_engine, first, "mine")
    other = await keep(async_engine, second, "another run's")
    assert await join(async_engine, first, mine.version, "run") is not None
    assert await join(async_engine, second, other.version, "other") is not None
    async with AsyncSession(async_engine) as db:
        repository = WaitingMessageRepository(db)
        [taken] = await repository.take_joining(first.owner_id, "run")
        assert taken.content == "mine" and taken.conversation_id == first.id
        assert await repository.take_joining(first.owner_id, "run") == []
        assert await repository.take_joining(uuid4(), "other") == []
        await db.commit()
    left = await only_row(async_engine, first.owner_id)
    assert left is not None and left.content == "another run's"
    assert left.status == WaitingStatus.JOINING


@pytest.mark.parametrize(
    ("end", "status"),
    [
        (RunEnd.NORMAL, WaitingStatus.WAITING),
        (RunEnd.INTERRUPTED, WaitingStatus.HELD),
        (RunEnd.UNSTARTED, WaitingStatus.WAITING),
    ],
)
async def test_a_note_nobody_read_goes_back_at_the_release(
    async_engine: AsyncEngine,
    two_discussions: tuple[ConversationRef, ConversationRef],
    end: RunEnd,
    status: WaitingStatus,
) -> None:
    first = two_discussions[0]
    row = await keep(async_engine, first, "too late for this answer")
    assert await join(async_engine, first, row.version, "run") is not None
    async with AsyncSession(async_engine) as db:
        settled = await WaitingMessageRepository(db).settle_release(first.owner_id, "run", end)
        await db.commit()
    assert settled.returned == 1
    assert settled.held == (1 if status == WaitingStatus.HELD else 0)
    back = await only_row(async_engine, first.owner_id)
    assert back is not None
    assert back.status == status and back.stream_id is None
    assert back.content == "too late for this answer"


async def test_another_runs_release_leaves_a_joining_message_alone(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ConversationRef]
) -> None:
    first = two_discussions[0]
    row = await keep(async_engine, first, "for the run that reads it")
    assert await join(async_engine, first, row.version, "run") is not None
    async with AsyncSession(async_engine) as db:
        settled = await WaitingMessageRepository(db).settle_release(
            first.owner_id, "another", RunEnd.INTERRUPTED
        )
        await db.commit()
    assert settled.returned == 0 and settled.held == 0
    stays = await only_row(async_engine, first.owner_id)
    assert stays is not None and stays.status == WaitingStatus.JOINING
