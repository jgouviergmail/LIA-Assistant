"""Complete filtered timeline reads, on the actual PostgreSQL source schemas."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, event, select
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DISPLAY_READ_BATCH_ROWS
from src.domains.activity.repository import ActivityReadRepository, heartbeat_rows_stmt
from src.domains.activity.schemas import ActivityCriteria
from src.domains.habits.models import UserHabit
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.interests.models import InterestNotification
from src.domains.journals.models import JournalEntry
from src.domains.open_loops.models import OpenLoop
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.shared.display_queries import read_display_rows
from src.domains.users.models import User
from src.infrastructure.database.models import BaseModel

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 1, tzinfo=UTC)
SINCE = NOW - timedelta(days=30)


def heartbeat(owner: UUID, text: str, when: datetime) -> HeartbeatNotification:
    return HeartbeatNotification(
        user_id=owner,
        content=text,
        created_at=when,
        run_id=str(uuid4()),
        content_hash=str(uuid4()),
        sources_used="[]",
    )


def interest(owner: UUID, text: str, when: datetime) -> InterestNotification:
    return InterestNotification(
        user_id=owner,
        content=text,
        created_at=when,
        run_id=str(uuid4()),
        content_hash=str(uuid4()),
        source="test",
    )


def journal(owner: UUID, text: str, when: datetime) -> JournalEntry:
    return JournalEntry(
        user_id=owner,
        title=text,
        content="Undisplayed secret",
        created_at=when,
        theme="learnings",
        source="conversation",
    )


def habit(owner: UUID, text: str, when: datetime) -> UserHabit:
    return UserHabit(
        user_id=owner,
        key=text,
        kind=str(uuid4())[:20],
        payload={},
        created_at=when,
        last_observed_at=when,
    )


def loop(owner: UUID, text: str, when: datetime) -> OpenLoop:
    return OpenLoop(
        user_id=owner,
        subject=text,
        direction="user_owes",
        status="closed",
        created_at=when,
        updated_at=when,
    )


def routine(owner: UUID, text: str, when: datetime) -> ScheduledAction:
    return ScheduledAction(
        user_id=owner,
        title=text,
        action_prompt="Undisplayed secret",
        recurrence={"anchor_date": "2026-01-01"},
        last_executed_at=when,
    )


@dataclass(frozen=True)
class Source:
    make: Callable[[UUID, str, datetime], BaseModel]
    read: Callable[
        [ActivityReadRepository, UUID, datetime, int, ActivityCriteria],
        Awaitable[tuple[Sequence[BaseModel], int]],
    ]


SOURCES = (
    Source(heartbeat, ActivityReadRepository.heartbeat_notifications_since),
    Source(interest, ActivityReadRepository.interest_notifications_since),
    Source(journal, ActivityReadRepository.journal_entries_since),
    Source(habit, ActivityReadRepository.habits_since),
    Source(loop, ActivityReadRepository.open_loops_created_since),
    Source(loop, ActivityReadRepository.open_loops_closed_since),
    Source(routine, ActivityReadRepository.scheduled_action_runs_since),
)


@pytest.mark.parametrize("source", SOURCES, ids=lambda source: source.read.__name__)
async def test_every_source_filters_before_cap_and_counts_owned_window_once(
    async_session: AsyncSession,
    test_user: User,
    source: Source,
) -> None:
    stranger = User(id=uuid4(), email=f"activity-{uuid4()}@example.com")
    async_session.add(stranger)
    await async_session.flush()
    newest = source.make(test_user.id, "Unrelated", NOW)
    later = source.make(test_user.id, "Été 100%_ 中文", NOW - timedelta(hours=1))
    oldest = source.make(test_user.id, "Été 100%_ 中文", NOW - timedelta(hours=2))
    async_session.add_all(
        [
            newest,
            later,
            oldest,
            source.make(stranger.id, "Été 100%_ 中文", NOW),
            source.make(test_user.id, "Été 100%_ 中文", NOW + timedelta(seconds=1)),
            source.make(test_user.id, "Été 100%_ 中文", SINCE - timedelta(seconds=1)),
        ]
    )
    await async_session.flush()
    statements: list[str] = []

    def capture(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    connection = await async_session.connection()
    event.listen(connection.sync_connection, "before_cursor_execute", capture)
    try:
        rows, total = await source.read(
            ActivityReadRepository(async_session),
            test_user.id,
            SINCE,
            1,
            ActivityCriteria(q="ete 100%_ 中", as_of=NOW, sort="oldest"),
        )
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", capture)
    assert [row.id for row in rows] == [oldest.id]
    assert total == 2
    assert len(statements) == 1  # Includes eager relationships: no hidden queries.
    assert "embedding" not in statements[0]
    assert "action_prompt" not in statements[0]
    assert "journal_entries.content" not in statements[0]
    rows, total = await source.read(
        ActivityReadRepository(async_session),
        test_user.id,
        SINCE,
        1,
        ActivityCriteria(as_of=NOW),
    )
    assert [row.id for row in rows] == [newest.id]
    assert total == 3
    assert (
        await source.read(
            ActivityReadRepository(async_session),
            test_user.id,
            SINCE,
            1,
            ActivityCriteria(q="Undisplayed secret", as_of=NOW),
        )
    ) == ([], 0)


async def test_ties_null_content_and_journal_scope(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    first, second = interest(test_user.id, "Été", NOW), interest(test_user.id, "Été", NOW)
    first.id, second.id = UUID(int=1), UUID(int=2)
    second.content = None
    manual, archived = journal(test_user.id, "Été", NOW), journal(test_user.id, "Été", NOW)
    manual.source, archived.status = "manual", "archived"
    async_session.add_all([second, first, manual, archived])
    await async_session.flush()
    repo = ActivityReadRepository(async_session)
    for sort in ("recent", "oldest"):
        criteria = ActivityCriteria.model_validate({"as_of": NOW, "sort": sort})
        rows, total = await repo.interest_notifications_since(test_user.id, SINCE, 5, criteria)
        assert [row.id for row in rows] == [first.id, second.id]
        assert total == 2
    assert await repo.journal_entries_since(test_user.id, SINCE, 5, criteria) == ([], 0)
    rows, total = await repo.interest_notifications_since(
        test_user.id,
        SINCE,
        5,
        ActivityCriteria(q="ete", as_of=NOW),
    )
    assert [row.id for row in rows] == [first.id] and total == 1


async def test_complete_scan_beyond_batches_and_cursor_closed_on_cancellation(
    async_session: AsyncSession,
    test_user: User,
    record_property: Callable[[str, object], None],
) -> None:
    count = DISPLAY_READ_BATCH_ROWS * 9 + 1
    async_session.add_all(heartbeat(test_user.id, "Été", NOW) for _ in range(count))
    await async_session.flush()
    started = perf_counter()
    rows, total = await ActivityReadRepository(async_session).heartbeat_notifications_since(
        test_user.id,
        SINCE,
        1,
        ActivityCriteria(q="ete", as_of=NOW),
    )
    record_property("scan_seconds", perf_counter() - started)
    record_property("rows", count)
    assert len(rows) == 1 and total == count
    statement = heartbeat_rows_stmt(test_user.id, SINCE, 1)
    stream = await async_session.stream(statement.limit(None))

    def cancelled(row: HeartbeatNotification) -> str:
        raise asyncio.CancelledError

    with (
        patch.object(async_session, "stream", AsyncMock(return_value=stream)),
        patch.object(stream, "close", AsyncMock(wraps=stream.close)) as close,
        pytest.raises(asyncio.CancelledError),
    ):
        await read_display_rows(async_session, statement, query="ete", text_of=cancelled, cap=1)
    close.assert_awaited_once()
    assert stream.closed
    assert await async_session.scalar(select(1)) == 1
