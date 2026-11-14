"""A message written while LIA works waits its turn, on real PostgreSQL (ADR-384)."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.constants import CHAT_MESSAGE_MAX_LENGTH, WAITING_MESSAGE_SEPARATOR
from src.core.conversation_execution import RunAdmission, RunEnd
from src.core.conversation_target import ConversationRef
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus
from src.domains.conversations.waiting_repository import (
    WaitingMessageDeparting,
    WaitingMessageRepository,
    WaitingMessageTooLong,
)
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration


@pytest.fixture
async def two_discussions(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> tuple[ConversationRef, ConversationRef, ConversationRef]:
    """Two discussions of one account, and a stranger's."""
    first, foreign = await persist_runtime_targets(async_engine, committed_user_ids, count=2)
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
    return first, second, foreign


async def keep(
    engine: AsyncEngine, target: ConversationRef, text: str, *, held: bool = False
) -> tuple[WaitingMessage, bool]:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        kept = await WaitingMessageRepository(db).keep(
            target,
            text,
            rendering=None,
            status=WaitingStatus.HELD if held else WaitingStatus.WAITING,
        )
        await db.commit()
        return kept


async def rows(engine: AsyncEngine, owner_id: UUID) -> list[WaitingMessage]:
    async with AsyncSession(engine) as db:
        result = await db.scalars(
            select(WaitingMessage)
            .where(WaitingMessage.user_id == owner_id)
            .order_by(WaitingMessage.created_at)
        )
        return list(result)


async def admit(engine: AsyncEngine, target: ConversationRef) -> RunAdmission:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        admission = await ConversationExecutionRepository(db).admit(
            target, run_id=str(uuid4()), stream_id=str(uuid4()), worker_id=uuid4()
        )
        assert isinstance(admission, RunAdmission)
        await db.commit()
        return admission


async def test_later_words_are_added_to_the_one_waiting_message(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ...]
) -> None:
    first = two_discussions[0]
    created, appended = await keep(async_engine, first, "Add the dentist")
    assert not appended and created.version == 1
    added, appended = await keep(async_engine, first, "and the bakery")
    assert appended and added.id == created.id and added.version == 2
    [row] = await rows(async_engine, first.owner_id)
    assert row.content == f"Add the dentist{WAITING_MESSAGE_SEPARATOR}and the bakery"
    assert row.status == WaitingStatus.WAITING
    assert row.conversation_revision == first.revision


async def test_a_message_too_long_once_added_is_refused_and_the_kept_text_stays(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ...]
) -> None:
    first = two_discussions[0]
    await keep(async_engine, first, "x" * (CHAT_MESSAGE_MAX_LENGTH - 1))
    with pytest.raises(WaitingMessageTooLong):
        await keep(async_engine, first, "y")
    [row] = await rows(async_engine, first.owner_id)
    assert row.content == "x" * (CHAT_MESSAGE_MAX_LENGTH - 1) and row.version == 1


async def test_each_discussion_keeps_its_own_and_a_departing_one_takes_no_more_words(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ...]
) -> None:
    first, second, _ = two_discussions
    one, _ = await keep(async_engine, first, "one")
    await keep(async_engine, second, "two")
    async with AsyncSession(async_engine) as db:
        assert await WaitingMessageRepository(db).claim(one.id, one.version, stream_id="s-1")
        await db.commit()
    with pytest.raises(WaitingMessageDeparting):
        await keep(async_engine, first, "three")
    statuses = sorted((row.content, row.status) for row in await rows(async_engine, first.owner_id))
    assert statuses == [("one", WaitingStatus.DEPARTING), ("two", WaitingStatus.WAITING)]


async def test_the_place_is_unique_per_discussion_in_sql(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ...]
) -> None:
    first = two_discussions[0]
    await keep(async_engine, first, "one")
    async with AsyncSession(async_engine) as db:
        db.add(
            WaitingMessage(
                user_id=first.owner_id,
                conversation_id=first.id,
                conversation_revision=first.revision,
                content="two",
                status=WaitingStatus.HELD,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()


async def test_a_claim_needs_the_version_the_person_last_saw(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ...]
) -> None:
    first = two_discussions[0]
    row, _ = await keep(async_engine, first, "one")
    await keep(async_engine, first, "two")
    async with AsyncSession(async_engine) as db:
        assert not await WaitingMessageRepository(db).claim(row.id, row.version, stream_id="s")
        assert await WaitingMessageRepository(db).claim(row.id, row.version + 1, stream_id="s")
        assert not await WaitingMessageRepository(db).claim(row.id, row.version + 1, stream_id="t")
        await db.commit()


async def test_an_edit_needs_the_version_and_a_departing_message_is_frozen(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ...]
) -> None:
    first = two_discussions[0]
    row, _ = await keep(async_engine, first, "one")
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        repo = WaitingMessageRepository(db)
        assert (
            await repo.replace_text(first.owner_id, first.id, "uno", version=row.version + 1)
            is None
        )
        edited = await repo.replace_text(first.owner_id, first.id, "uno", version=row.version)
        assert edited is not None and edited.content == "uno" and edited.version == 2
        assert await repo.claim(row.id, 2, stream_id="s")
        assert await repo.replace_text(first.owner_id, first.id, "dos", version=2) is None
        assert not await repo.withdraw(first.owner_id, first.id)
        await db.commit()


async def test_the_archive_consumes_only_its_own_departure(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ...]
) -> None:
    first, second, foreign = two_discussions
    one, _ = await keep(async_engine, first, "one")
    two, _ = await keep(async_engine, second, "two")
    stranger, _ = await keep(async_engine, foreign, "three")
    async with AsyncSession(async_engine) as db:
        repo = WaitingMessageRepository(db)
        assert await repo.claim(one.id, one.version, stream_id="mine")
        assert await repo.claim(two.id, two.version, stream_id="other")
        assert await repo.claim(stranger.id, stranger.version, stream_id="mine")
        await db.commit()
    async with AsyncSession(async_engine) as db:
        assert await WaitingMessageRepository(db).consume(first.owner_id, "mine") == one.id
        assert await WaitingMessageRepository(db).consume(first.owner_id, "mine") is None
        await db.commit()
    assert [row.content for row in await rows(async_engine, first.owner_id)] == ["two"]
    assert [row.content for row in await rows(async_engine, foreign.owner_id)] == ["three"]


@pytest.mark.parametrize(
    ("end", "departed", "waiting", "asked"),
    [
        (RunEnd.NORMAL, WaitingStatus.HELD, WaitingStatus.WAITING, WaitingStatus.WAITING),
        (RunEnd.INTERRUPTED, WaitingStatus.HELD, WaitingStatus.HELD, WaitingStatus.WAITING),
        (RunEnd.UNSTARTED, WaitingStatus.WAITING, WaitingStatus.WAITING, WaitingStatus.WAITING),
    ],
)
async def test_a_release_settles_what_waited_by_how_the_run_ended(
    async_engine: AsyncEngine,
    two_discussions: tuple[ConversationRef, ...],
    end: RunEnd,
    departed: WaitingStatus,
    waiting: WaitingStatus,
    asked: WaitingStatus,
) -> None:
    first, second, foreign = two_discussions
    leaving, _ = await keep(async_engine, first, "leaving")
    await keep(async_engine, second, "waiting")
    third = replace(first, id=uuid4(), runtime_id=uuid4())
    async with AsyncSession(async_engine) as db:
        db.add(
            Conversation(
                id=third.id,
                user_id=third.owner_id,
                kind=third.kind,
                title="Third",
                revision=third.revision,
                runtime_id=third.runtime_id,
            )
        )
        await db.commit()
    await keep(async_engine, third, "asked")
    stranger, _ = await keep(async_engine, foreign, "stranger")
    async with AsyncSession(async_engine) as db:
        repo = WaitingMessageRepository(db)
        assert await repo.claim(leaving.id, leaving.version, stream_id="run")
        assert await repo.request_send(first.owner_id, third.id) is not None
        await db.commit()
    async with AsyncSession(async_engine) as db:
        await WaitingMessageRepository(db).settle_release(first.owner_id, "run", end)
        await db.commit()
    by_text = {row.content: row for row in await rows(async_engine, first.owner_id)}
    assert by_text["leaving"].status == departed
    assert (by_text["leaving"].stream_id is None) == (departed != WaitingStatus.DEPARTING)
    assert by_text["waiting"].status == waiting
    assert by_text["asked"].status == asked
    [untouched] = await rows(async_engine, foreign.owner_id)
    assert untouched.status == WaitingStatus.WAITING and untouched.id == stranger.id


@pytest.mark.parametrize(
    ("end", "expected"),
    [
        (RunEnd.NORMAL, ["asked-held", "asked", "older", "newer"]),
        (RunEnd.INTERRUPTED, ["asked-held", "asked"]),
        (RunEnd.UNSTARTED, ["asked-held", "asked"]),
    ],
)
async def test_what_may_leave_after_a_release_comes_in_a_declared_order(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    end: RunEnd,
    expected: list[str],
) -> None:
    targets = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    owner = targets[0].owner_id
    discussions = [targets[0]]
    async with AsyncSession(async_engine) as db:
        for title in ("b", "c", "d", "e"):
            extra = replace(targets[0], id=uuid4(), runtime_id=uuid4())
            discussions.append(extra)
            db.add(
                Conversation(
                    id=extra.id,
                    user_id=owner,
                    kind=extra.kind,
                    title=title,
                    revision=extra.revision,
                    runtime_id=extra.runtime_id,
                )
            )
        await db.commit()
    await keep(async_engine, discussions[0], "older")
    await keep(async_engine, discussions[1], "newer")
    await keep(async_engine, discussions[2], "held", held=True)
    await keep(async_engine, discussions[3], "asked-held", held=True)
    await keep(async_engine, discussions[4], "asked")
    async with AsyncSession(async_engine) as db:
        repo = WaitingMessageRepository(db)
        assert await repo.request_send(owner, discussions[3].id) is not None
        assert await repo.request_send(owner, discussions[4].id) is not None
        await db.commit()
    async with AsyncSession(async_engine) as db:
        candidates = await WaitingMessageRepository(db).departure_candidates(owner, end)
    assert [row.content for row in candidates] == expected


async def test_a_close_writes_how_the_run_ended(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ...]
) -> None:
    admission = await admit(async_engine, two_discussions[0])
    async with AsyncSession(async_engine) as db:
        assert await ConversationExecutionRepository(db).close_owned(admission, end=RunEnd.NORMAL)
        await db.commit()
    async with AsyncSession(async_engine) as db:
        repo = ConversationExecutionRepository(db)
        assert await repo.ended_as(admission.target.owner_id, admission.stream_id) == RunEnd.NORMAL
        assert await repo.ended_as(admission.target.owner_id, "unknown") is None
        row = await db.get(ConversationExecution, admission.activity_id)
        assert row is not None and row.end_state == RunEnd.NORMAL


async def test_a_running_execution_has_no_end_yet(
    async_engine: AsyncEngine, two_discussions: tuple[ConversationRef, ...]
) -> None:
    admission = await admit(async_engine, two_discussions[0])
    async with AsyncSession(async_engine) as db:
        assert (
            await ConversationExecutionRepository(db).ended_as(
                admission.target.owner_id, admission.stream_id
            )
            is None
        )
        row = await db.get(ConversationExecution, admission.activity_id)
        assert row is not None
        row.end_state = RunEnd.NORMAL
        with pytest.raises(IntegrityError):
            await db.flush()


@pytest.mark.parametrize(
    ("end", "status", "still_asked"),
    [
        (RunEnd.NORMAL, WaitingStatus.HELD, False),
        (RunEnd.INTERRUPTED, WaitingStatus.HELD, False),
        (RunEnd.UNSTARTED, WaitingStatus.WAITING, True),
    ],
)
async def test_a_send_now_that_left_and_failed_is_not_asked_again(
    async_engine: AsyncEngine,
    two_discussions: tuple[ConversationRef, ...],
    end: RunEnd,
    status: WaitingStatus,
    still_asked: bool,
) -> None:
    """A run that took the message and did not archive it honoured « send now » once."""
    first = two_discussions[0]
    row, _ = await keep(async_engine, first, "send it")
    async with AsyncSession(async_engine) as db:
        repo = WaitingMessageRepository(db)
        assert await repo.request_send(first.owner_id, first.id) is not None
        assert await repo.claim(row.id, row.version, stream_id="run")
        await db.commit()
    async with AsyncSession(async_engine) as db:
        await WaitingMessageRepository(db).settle_release(first.owner_id, "run", end)
        await db.commit()
    [settled] = await rows(async_engine, first.owner_id)
    assert settled.status == status
    assert (settled.send_requested_at is not None) is still_asked
