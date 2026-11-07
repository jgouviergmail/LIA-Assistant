"""A manual edit of a memory through its route, on real PostgreSQL.

When five refused saves were read in production on 2026-11-06, Prometheus held no 200
for this route at all: nothing had ever shown its success path, only that it could
refuse. These tests walk it for real, down to the rows.
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.memory_update_schemas import (
    MemoryUpdateChanges,
    MemoryUpdateRequest,
)
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_memory_tools import update_lia_memory_tool
from src.domains.memories.models import MEMORY_EMBEDDING_DIMENSIONS, Memory
from src.domains.memories.router import router
from src.domains.memories.schemas import MemoryLimits
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration

CONTENT_VECTOR = [0.1] * MEMORY_EMBEDDING_DIMENSIONS
KEYWORD_VECTOR = [0.2] * MEMORY_EMBEDDING_DIMENSIONS


@pytest.fixture
def embedder() -> Iterator[AsyncMock]:
    """The provider is the only thing replaced: the route, the service and the rows are real."""
    with patch(
        "src.domains.memories.service._generate_dual_embeddings",
        new=AsyncMock(return_value=(CONTENT_VECTOR, None)),
    ) as stub:
        yield stub


@pytest.fixture
async def client(async_session: AsyncSession, test_user: User) -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: async_session
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


async def _stored(
    db: AsyncSession, user: User, *, content: str = "An owned fact", **fields: object
) -> Memory:
    row = Memory(
        user_id=user.id,
        content=content,
        category="personal",
        importance=0.7,
        pinned=False,
        char_count=len(content),
        trigger_topic="a topic",
        usage_nuance="a nuance",
        embedding=[0.5] * MEMORY_EMBEDDING_DIMENSIONS,
        keyword_embedding=KEYWORD_VECTOR,
        **fields,
    )
    db.add(row)
    await db.commit()
    return row


async def _reread(db: AsyncSession, row: Memory) -> Memory:
    current = await db.scalar(
        select(Memory).where(Memory.id == row.id).execution_options(populate_existing=True)
    )
    assert current is not None
    return current


async def test_an_edit_at_the_ceiling_is_saved_with_its_new_vector(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    embedder: AsyncMock,
) -> None:
    row = await _stored(async_session, test_user)
    text = "x" * settings.memory_content_max_chars

    response = await client.patch(f"/memories/{row.id}", json={"content": text})

    assert response.status_code == 200, response.text
    assert response.json()["content"] == text
    embedder.assert_awaited_once()
    current = await _reread(async_session, row)
    assert current.content == text
    assert current.char_count == len(text)
    assert current.embedding is not None
    assert list(current.embedding) == pytest.approx(CONTENT_VECTOR)


async def test_an_edit_keeping_the_text_rewrites_no_vector(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    embedder: AsyncMock,
) -> None:
    """The form sends every field: saving an unchanged text must stay free of charge."""
    row = await _stored(async_session, test_user)

    response = await client.patch(
        f"/memories/{row.id}",
        json={"content": row.content, "trigger_topic": row.trigger_topic, "importance": 0.9},
    )

    assert response.status_code == 200, response.text
    embedder.assert_not_awaited()
    assert (await _reread(async_session, row)).importance == pytest.approx(0.9)


async def test_an_edit_past_the_ceiling_is_refused_and_changes_nothing(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    embedder: AsyncMock,
) -> None:
    row = await _stored(async_session, test_user)
    before = row.content

    response = await client.patch(
        f"/memories/{row.id}", json={"content": "x" * (settings.memory_content_max_chars + 1)}
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "string_too_long"
    assert response.json()["detail"][0]["loc"] == ["body", "content"]
    embedder.assert_not_awaited()
    assert (await _reread(async_session, row)).content == before


async def test_a_cleared_nuance_and_topic_are_saved_empty(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    embedder: AsyncMock,
) -> None:
    """An empty string is an edit: the form sends it, and the row must end up empty."""
    row = await _stored(async_session, test_user)

    response = await client.patch(
        f"/memories/{row.id}", json={"usage_nuance": "", "trigger_topic": ""}
    )

    assert response.status_code == 200, response.text
    current = await _reread(async_session, row)
    assert current.usage_nuance == "" and current.trigger_topic == ""
    embedder.assert_awaited_once_with("An owned fact", "")


async def test_one_row_past_the_ceiling_leaves_the_list_open(
    async_session: AsyncSession, test_user: User, client: httpx.AsyncClient
) -> None:
    """One such row answered 500 for the whole list, and hid every other memory with it."""
    past = "x" * (settings.memory_content_max_chars + 1)
    await _stored(async_session, test_user, content=past)
    await _stored(async_session, test_user)

    response = await client.get("/memories")

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(len(item["content"]) for item in body["items"]) == [13, len(past)]
    assert body["limits"] == MemoryLimits().model_dump()


async def test_a_row_past_the_ceiling_can_be_shortened(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    embedder: AsyncMock,
) -> None:
    row = await _stored(
        async_session, test_user, content="x" * (settings.memory_content_max_chars + 1)
    )

    response = await client.patch(f"/memories/{row.id}", json={"content": "Now within its bound"})

    assert response.status_code == 200, response.text
    assert (await _reread(async_session, row)).content == "Now within its bound"


async def test_the_assistant_can_shorten_a_row_past_the_ceiling(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The assistant's other door: it reads the row before it proposes anything."""
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    row = await _stored(
        async_session, test_user, content="x" * (settings.memory_content_max_chars + 1)
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    async def budget(user_id: UUID, *, layer: str) -> None:
        assert user_id == owner

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    with (
        installed_runtime_context(user_id=owner, language="fr", deps=object()),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch(
            "src.domains.agents.application.memory_creation_embeddings.enforce_usage_limit", budget
        ),
        patch(
            "src.domains.agents.application.memory_creation_embeddings._generate_document_embedding",
            AsyncMock(return_value=None),
        ),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        output = await update_lia_memory_tool.coroutine(
            selection=MemoryUpdateRequest(
                memory_id=row.id, changes=MemoryUpdateChanges(content="Now within its bound")
            ),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert output.success, output.message
        item = next(iter(output.registry_updates.values()))
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "memory-update"}},
            "memory-update",
            "fr",
        )

    assert result.success
    assert (await _reread(async_session, row)).content == "Now within its bound"
