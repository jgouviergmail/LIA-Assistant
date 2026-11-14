"""A waiting message enters its discussion exactly once, and leaves with it (ADR-384)."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.conversation_execution import RunAdmission
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import RunAuthority, run_authority_scope
from src.domains.agents.api.archive_first import archive_user_message_first
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.service import ConversationService
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus
from src.domains.conversations.waiting_repository import WaitingMessageRepository
from src.infrastructure.database import session
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


async def keep(engine: AsyncEngine, target: ConversationRef, text: str) -> WaitingMessage:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        row, _ = await WaitingMessageRepository(db).keep(
            target, text, rendering=None, status=WaitingStatus.WAITING
        )
        await db.commit()
        return row


async def waiting_ids(engine: AsyncEngine, owner_id: UUID) -> set[UUID]:
    async with AsyncSession(engine) as db:
        return set(
            await db.scalars(select(WaitingMessage.id).where(WaitingMessage.user_id == owner_id))
        )


async def test_the_archive_of_the_persons_message_consumes_its_departure_once(
    reserved: RunAdmission, async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    row = await keep(async_engine, reserved.target, "Add the bakery")
    async with AsyncSession(async_engine) as db:
        assert await WaitingMessageRepository(db).claim(
            row.id, row.version, stream_id=reserved.stream_id
        )
        await db.commit()
    with run_authority_scope(RunAuthority(reserved)):
        archived = await archive_user_message_first(
            conv_service=ConversationService(),
            conversation_id=reserved.target.id,
            user_message="Add the bakery",
            run_id=reserved.run_id,
            is_hitl_resumption=False,
            attachment_meta={},
            stt_kwargs={},
        )
    assert archived is not None
    assert await waiting_ids(async_engine, reserved.target.owner_id) == set()
    async with AsyncSession(async_engine) as db:
        contents = list(
            await db.scalars(
                select(ConversationMessage.content).where(
                    ConversationMessage.conversation_id == reserved.target.id,
                    ConversationMessage.role == "user",
                )
            )
        )
    assert contents == ["Add the bakery"]


async def test_an_archive_without_a_departure_leaves_what_waits(
    reserved: RunAdmission, async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    row = await keep(async_engine, reserved.target, "Written while LIA works")
    with run_authority_scope(RunAuthority(reserved)):
        await archive_user_message_first(
            conv_service=ConversationService(),
            conversation_id=reserved.target.id,
            user_message="The current question",
            run_id=reserved.run_id,
            is_hitl_resumption=False,
            attachment_meta={},
            stt_kwargs={},
        )
    assert await waiting_ids(async_engine, reserved.target.owner_id) == {row.id}


@pytest.mark.parametrize("action", ["reset", "delete"])
async def test_a_discussion_reset_or_deleted_takes_its_waiting_message_with_it(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], action: str
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    annex = ConversationRef(owner, uuid4(), ConversationKind.SECONDARY, 2, uuid4())
    other = ConversationRef(owner, uuid4(), ConversationKind.SECONDARY, 0, uuid4())
    async with AsyncSession(async_engine) as db:
        for target in (annex, other):
            db.add(
                Conversation(
                    id=target.id,
                    user_id=owner,
                    kind=target.kind,
                    revision=target.revision,
                    runtime_id=target.runtime_id,
                    title="Topic",
                )
            )
        await db.commit()
    await keep(async_engine, annex, "Gone with the discussion")
    kept = await keep(async_engine, other, "Stays")
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        lifecycle = ConversationLifecycle(db)
        if action == "reset":
            await lifecycle.request_reset(
                owner, annex.id, operation_id=uuid4(), expected_revision=annex.revision
            )
        else:
            await lifecycle.request_delete(
                owner, annex.id, operation_id=uuid4(), expected_revision=annex.revision
            )
    assert await waiting_ids(async_engine, owner) == {kept.id}
