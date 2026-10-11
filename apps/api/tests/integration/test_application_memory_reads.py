"""Explicit management reads cover the owned active set beyond the UI's old page cap."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application import memory_queries
from src.domains.agents.application.memory_queries import read_memories
from src.domains.agents.application.memory_read_schemas import MemoryRead
from src.domains.agents.tools.application_memory_tools import get_lia_memories_tool
from src.domains.memories.management_queries import MemoryManagementPage
from src.domains.memories.models import Memory
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "case",
    [
        "page",
        "category",
        "single",
        "missing",
        "foreign",
        "disabled",
        "inactive",
        "automatic_off",
        "source_changed",
        "unknown_cursor",
        "invalidated_cursor",
        "invalidated",
    ],
)
async def test_management_memory_read_is_owned_bounded_current_and_without_usage_writes(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", case != "disabled")
    actor_id = test_user.id
    base = uuid4().int & ~65535
    if case == "inactive":
        test_user.is_active = False
    if case == "automatic_off":
        test_user.memory_enabled = False
    rows = [
        Memory(
            id=UUID(int=base + index + 1),
            user_id=actor_id,
            content=f"Managed fact {index}",
            category="personal" if index % 2 == 0 else "procedural",
            importance=0.0,
            char_count=len(f"Managed fact {index}"),
            usage_count=0,
            pinned=False,
        )
        for index in range(205)
    ]
    stale = Memory(
        id=UUID(int=base + 500),
        user_id=actor_id,
        content="Old invalidated fact",
        category="personal",
        invalidated_at=datetime.now(UTC),
        char_count=20,
    )
    async_session.add_all([*rows, stale])
    await async_session.commit()
    if case == "foreign":
        other = User(
            email=f"other-memory-{uuid4()}@read.test", hashed_password="test", is_active=True
        )
        async_session.add(other)
        await async_session.commit()
        actor_id = other.id
    selected = rows[0].id
    if case == "source_changed":
        await async_session.execute(
            update(Memory)
            .where(Memory.id == selected)
            .values(content="Updated source fact")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    query = MemoryRead(
        memory_id=(
            stale.id
            if case == "invalidated"
            else (
                uuid4()
                if case == "missing"
                else selected if case in {"single", "foreign", "source_changed"} else None
            )
        ),
        category="procedural" if case == "category" else None,
        after_id=(
            uuid4()
            if case == "unknown_cursor"
            else stale.id if case == "invalidated_cursor" else None
        ),
        limit=50,
    )
    if case in {"disabled", "inactive", "missing", "foreign", "unknown_cursor", "invalidated"}:
        with pytest.raises(
            ResourceNotFoundError
            if case in {"missing", "foreign", "unknown_cursor", "invalidated"}
            else AuthorizationError
        ):
            await read_memories(async_session, actor_id, query)
        if case == "foreign":
            empty = await read_memories(async_session, actor_id, MemoryRead())
            assert empty.total_available == 0 and not empty.memories and not empty.by_category
    else:
        result = await read_memories(async_session, actor_id, query)
        assert result.total_available == (
            1 if case in {"single", "source_changed"} else 102 if case == "category" else 205
        )
        assert result.returned_count == len(result.memories)
        assert result.by_category == {"personal": 103, "procedural": 102}
        assert result.automatic_use_enabled is (case != "automatic_off")
        assert all(item.importance == 0.0 for item in result.memories)
        assert "embedding" not in result.model_dump_json()
        if case == "source_changed":
            assert result.memories[0].content == "Updated source fact"
        if case == "page":
            identities = [item.id for item in result.memories]
            while result.next_cursor:
                result = await read_memories(
                    async_session, actor_id, MemoryRead(after_id=result.next_cursor, limit=50)
                )
                identities.extend(item.id for item in result.memories)
            assert len(identities) == len(set(identities)) == 205
            empty = await read_memories(
                async_session, actor_id, MemoryRead(after_id=UUID(identities[-1]))
            )
            assert empty.total_available == 205 and not empty.memories and not empty.truncated
    for row in rows:
        assert row.usage_count == 0 and row.last_accessed_at is None


@pytest.mark.parametrize("withdrawn", [False, True])
async def test_public_memory_tool_rechecks_source_io_and_reports_current_recall_opt_out(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    withdrawn: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.memory_enabled = True
    row = Memory(user_id=test_user.id, content="A managed fact", category="personal", char_count=14)
    async_session.add(row)
    await async_session.commit()
    source_read = memory_queries.read_management_page

    async def source_io(
        db: AsyncSession,
        actor_id: UUID,
        *,
        limit: int,
        category: str | None,
        memory_id: UUID | None,
        after_id: UUID | None,
    ) -> MemoryManagementPage:
        observed = await source_read(
            db, actor_id, limit=limit, category=category, memory_id=memory_id, after_id=after_id
        )
        test_user.memory_enabled = False
        await async_session.commit()
        if withdrawn:
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return observed

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(memory_queries, "read_management_page", source_io)
    monkeypatch.setattr("src.domains.agents.tools.application_memory_tools.get_db_context", session)
    with installed_runtime_context(user_id=test_user.id, memory_enabled=True):
        output = await get_lia_memories_tool.coroutine(
            runtime=make_tool_runtime(
                user_id=test_user.id, memory_enabled=True, store=InMemoryStore()
            ),
        )
    if withdrawn:
        assert not output.success and output.error_code == "CAPABILITY_DISABLED"
    else:
        assert output.success and output.structured_data["automatic_use_enabled"] is False
        assert output.structured_data["memories"][0]["id"] == str(row.id)
        assert output.metadata["application_memory_cursor"] is True
    assert row.usage_count == 0 and row.last_accessed_at is None


async def test_management_pages_preserve_ui_newest_order_and_creation_ties(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    base = uuid4().int & ~65535
    now = datetime.now(UTC)
    rows = [
        Memory(
            id=UUID(int=base + index + 1),
            user_id=test_user.id,
            content=f"Timed fact {index}",
            category="personal",
            char_count=12,
            created_at=now - timedelta(days=1 if index < 2 else 0),
        )
        for index in range(4)
    ]
    async_session.add_all(rows)
    await async_session.commit()
    first = await read_memories(async_session, test_user.id, MemoryRead(limit=2))
    assert [item.id for item in first.memories] == [str(rows[3].id), str(rows[2].id)]
    second = await read_memories(
        async_session, test_user.id, MemoryRead(limit=2, after_id=first.next_cursor)
    )
    assert [item.id for item in second.memories] == [str(rows[1].id), str(rows[0].id)]
    assert not second.truncated and second.next_cursor is None
