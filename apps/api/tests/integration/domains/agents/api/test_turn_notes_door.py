"""The answer being written opens, reads and closes the person's notes (ADR-385).

Real PostgreSQL, admission, authority and archive: the note is deleted and archived as
the person's message in ONE transaction, by the exact invocation it joined.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionRevoked, RunAdmission
from src.core.field_names import FIELD_RUN_ID, FIELD_STREAM_ID, FIELD_TURN_NOTE
from src.core.run_authority import RunAuthority, run_authority_scope
from src.domains.agents.api import turn_notes
from src.domains.agents.services.streaming.latency_sli import awaited_by_a_person
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.publication_repository import ConversationPublicationRepository
from src.domains.conversations.service import ConversationService
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus
from src.domains.conversations.waiting_repository import WaitingMessageRepository
from tests.fixtures.conversation_executions import reserved as reserved

pytestmark = pytest.mark.integration


@pytest.fixture
def signals(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Every door session on the test database; the tabs' signals recorded."""

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    told: list[dict[str, Any]] = []
    monkeypatch.setattr(turn_notes, "get_db_context", session)
    monkeypatch.setattr(
        turn_notes, "arm_conversation_signal", lambda _db, **signal: told.append(signal)
    )
    return told


async def keep(engine: AsyncEngine, admission: RunAdmission, text: str) -> WaitingMessage:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        row, _ = await WaitingMessageRepository(db).keep(
            admission.target, text, rendering=None, status=WaitingStatus.WAITING
        )
        await db.commit()
        return row


async def join(engine: AsyncEngine, admission: RunAdmission, row: WaitingMessage) -> WaitingMessage:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        joined = await WaitingMessageRepository(db).join(
            admission.target.owner_id,
            admission.target.id,
            version=row.version,
            stream_id=admission.stream_id,
        )
        assert joined is not None
        await db.commit()
        return joined


async def accepts_notes(engine: AsyncEngine, admission: RunAdmission) -> bool:
    async with AsyncSession(engine) as db:
        row = await db.get(ConversationExecution, admission.activity_id)
        assert row is not None
        return row.accepts_notes


async def person_rows(engine: AsyncEngine, conversation_id: UUID) -> list[ConversationMessage]:
    async with AsyncSession(engine) as db:
        result = await db.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.role == "user",
            )
            .order_by(ConversationMessage.created_at)
        )
        return list(result)


async def test_the_first_read_opens_the_notes_and_a_later_one_archives_what_joined(
    reserved: RunAdmission, async_engine: AsyncEngine, signals: list[dict[str, Any]]
) -> None:
    with run_authority_scope(RunAuthority(reserved)):
        assert await turn_notes.read_turn_notes() == []
    assert await accepts_notes(async_engine, reserved)
    row = await keep(async_engine, reserved, "only the ones open on Sunday")
    joined = await join(async_engine, reserved, row)
    with run_authority_scope(RunAuthority(reserved)):
        [note] = await turn_notes.read_turn_notes()
        assert await turn_notes.read_turn_notes() == []
    assert note.text == "only the ones open on Sunday"
    # The last thing the person did to it: here, addressing it to the answer.
    assert note.written_at == joined.updated_at
    [archived] = await person_rows(async_engine, reserved.target.id)
    assert archived.id == note.message_id
    assert archived.content == "only the ones open on Sunday"
    metadata = archived.message_metadata or {}
    assert metadata[FIELD_TURN_NOTE] is True
    assert metadata[FIELD_RUN_ID] == reserved.run_id
    assert metadata[FIELD_STREAM_ID] == reserved.stream_id
    async with AsyncSession(async_engine) as db:
        assert await db.scalar(select(WaitingMessage)) is None


async def test_opening_tells_the_tabs_only_when_something_waits_there(
    reserved: RunAdmission, async_engine: AsyncEngine, signals: list[dict[str, Any]]
) -> None:
    with run_authority_scope(RunAuthority(reserved)):
        await turn_notes.read_turn_notes()
    assert signals == []
    await keep(async_engine, reserved, "and near the station")
    with run_authority_scope(RunAuthority(reserved)):
        await turn_notes.close_turn_notes()
    [closed] = signals
    assert closed["user_id"] == reserved.target.owner_id
    assert closed["conversation_id"] == reserved.target.id
    assert not await accepts_notes(async_engine, reserved)


async def test_a_reopening_with_something_waiting_tells_the_tabs(
    reserved: RunAdmission, async_engine: AsyncEngine, signals: list[dict[str, Any]]
) -> None:
    await keep(async_engine, reserved, "written before the loop's first call")
    with run_authority_scope(RunAuthority(reserved)):
        await turn_notes.read_turn_notes()
        await turn_notes.read_turn_notes()
    assert len(signals) == 1


async def test_closing_twice_tells_the_tabs_once(
    reserved: RunAdmission, async_engine: AsyncEngine, signals: list[dict[str, Any]]
) -> None:
    with run_authority_scope(RunAuthority(reserved)):
        await turn_notes.read_turn_notes()
    await keep(async_engine, reserved, "a waiting message")
    with run_authority_scope(RunAuthority(reserved)):
        await turn_notes.close_turn_notes()
        await turn_notes.close_turn_notes()
    assert len(signals) == 1


async def test_a_stale_invocation_neither_opens_nor_reads(
    reserved: RunAdmission, async_engine: AsyncEngine, signals: list[dict[str, Any]]
) -> None:
    row = await keep(async_engine, reserved, "for the real run")
    await join(async_engine, reserved, row)
    stale = replace(reserved, owner_token=uuid4())
    with run_authority_scope(RunAuthority(stale)), pytest.raises(ExecutionRevoked):
        await turn_notes.read_turn_notes()
    assert not await accepts_notes(async_engine, reserved)
    async with AsyncSession(async_engine) as db:
        kept = await db.get(WaitingMessage, row.id)
        assert kept is not None and kept.status == WaitingStatus.JOINING
    assert await person_rows(async_engine, reserved.target.id) == []


async def test_a_run_nobody_waits_for_neither_opens_nor_reads(
    reserved: RunAdmission, async_engine: AsyncEngine, signals: list[dict[str, Any]]
) -> None:
    row = await keep(async_engine, reserved, "written while a routine ran")
    await join(async_engine, reserved, row)
    with awaited_by_a_person(False), run_authority_scope(RunAuthority(reserved)):
        assert await turn_notes.read_turn_notes() == []
        await turn_notes.close_turn_notes()
    assert not await accepts_notes(async_engine, reserved)
    async with AsyncSession(async_engine) as db:
        kept = await db.get(WaitingMessage, row.id)
        assert kept is not None and kept.status == WaitingStatus.JOINING
    assert signals == []


async def test_outside_any_invocation_there_is_nothing_to_read(
    signals: list[dict[str, Any]],
) -> None:
    assert await turn_notes.read_turn_notes() == []
    await turn_notes.close_turn_notes()
    assert signals == []


async def test_an_archive_that_fails_leaves_the_note_joining(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    signals: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with run_authority_scope(RunAuthority(reserved)):
        await turn_notes.read_turn_notes()
    row = await keep(async_engine, reserved, "a note")
    await join(async_engine, reserved, row)

    async def broken(*_args: object, **_kwargs: object) -> ConversationMessage:
        raise ConnectionError("the archive failed")

    monkeypatch.setattr(ConversationService, "archive_message", broken)
    with run_authority_scope(RunAuthority(reserved)):
        assert await turn_notes.read_turn_notes() == []
    async with AsyncSession(async_engine) as db:
        kept = await db.get(WaitingMessage, row.id)
        assert kept is not None and kept.status == WaitingStatus.JOINING
    assert await person_rows(async_engine, reserved.target.id) == []


async def test_a_note_is_never_taken_for_the_invocations_request(
    reserved: RunAdmission, async_engine: AsyncEngine, signals: list[dict[str, Any]]
) -> None:
    with run_authority_scope(RunAuthority(reserved)):
        await turn_notes.read_turn_notes()
    row = await keep(async_engine, reserved, "a note")
    await join(async_engine, reserved, row)
    with run_authority_scope(RunAuthority(reserved)):
        await turn_notes.read_turn_notes()
    async with AsyncSession(async_engine) as db:
        request = await ConversationPublicationRepository(db).request_message_id(
            reserved, "the question"
        )
    assert request is None
