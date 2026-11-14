"""An export imported back: what is new is created, what is there is left, nothing half done.

Run on PostgreSQL through the real router: the file is the one the export route serves,
the provider is the only thing replaced, and the oracle is the rows the account holds.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import UsageLimitExceededError
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_active_session
from src.domains.memories import creation_embeddings
from src.domains.memories.models import Memory
from src.domains.memories.router import router
from src.domains.memories.schemas import MemoryCreate
from src.domains.memories.service import MemoryService
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_VECTOR = [0.5] * 1536


@pytest.fixture
async def client(async_session: AsyncSession, test_user: User) -> AsyncIterator[httpx.AsyncClient]:
    async def authenticated(db: AsyncSession = Depends(get_db)) -> User:
        # Production reads the account on the request's own session: the import's
        # transaction is open before the route's first line.
        account = await db.scalar(select(User).where(User.id == test_user.id))
        assert account is not None
        return account

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: async_session
    app.dependency_overrides[get_current_active_session] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    calls = AsyncMock(side_effect=lambda texts: [_VECTOR for _ in texts])
    monkeypatch.setattr(creation_embeddings, "generate_document_embeddings", calls)
    monkeypatch.setattr(creation_embeddings, "enforce_usage_limit", AsyncMock())
    return calls


async def _stored(session: AsyncSession, user: User) -> dict[str, Memory]:
    rows = await session.scalars(
        select(Memory)
        .where(Memory.user_id == user.id, Memory.invalidated_at.is_(None))
        .execution_options(populate_existing=True)
    )
    return {row.content: row for row in rows}


async def _create(session: AsyncSession, user: User, content: str, **fields: object) -> Memory:
    service = MemoryService(session, embedder=AsyncMock(return_value=(None, None)))
    memory = await service.create_from_management(
        user.id, MemoryCreate.model_validate({"content": content, "category": "personal", **fields})
    )
    await session.commit()
    return memory


async def _export(client: httpx.AsyncClient, export_format: str) -> bytes:
    response = await client.get("/memories/export", params={"format": export_format})
    assert response.status_code == 200, response.text
    return response.content


def _upload(content: bytes, name: str = "memories.csv") -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, content, "application/octet-stream")}


@pytest.mark.parametrize("export_format", ["csv", "json"])
async def test_an_export_comes_back_whole_into_an_account_that_was_emptied(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    provider: AsyncMock,
    export_format: str,
) -> None:
    await _create(
        async_session,
        test_user,
        "=je préfère le thé — 你好",
        category="preference",
        emotional_weight=-4,
        trigger_topic="boissons",
        usage_nuance="Proposer du thé",
        importance=0.25,
    )
    pinned = await _create(async_session, test_user, "A fact the person pinned")
    pinned.pinned = True
    unpinned = await _create(async_session, test_user, "Never do that", category="procedural")
    unpinned.pinned = False  # a directive is pinned at creation; the person unpinned this one
    await async_session.commit()
    exported = await _export(client, export_format)
    assert (
        await client.delete("/memories", params={"preserve_pinned": "false"})
    ).status_code == 200
    assert await _stored(async_session, test_user) == {}

    response = await client.post("/memories/import", files=_upload(exported))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total": 3,
        "imported": 3,
        "already_present": 0,
        "duplicates": 0,
        "invalid": 0,
    }
    stored = await _stored(async_session, test_user)
    tea = stored["=je préfère le thé — 你好"]
    assert (tea.category, tea.emotional_weight, tea.trigger_topic, tea.usage_nuance) == (
        "preference",
        -4,
        "boissons",
        "Proposer du thé",
    )
    assert tea.importance == pytest.approx(0.25)
    assert tea.embedding is not None and tea.keyword_embedding is not None
    # The pin is the person's choice, both ways: it travels with the memory.
    assert stored["A fact the person pinned"].pinned is True
    assert stored["Never do that"].pinned is False


async def test_what_the_account_already_holds_is_left_alone_and_not_paid_for(
    async_session: AsyncSession, test_user: User, client: httpx.AsyncClient, provider: AsyncMock
) -> None:
    kept = await _create(async_session, test_user, "Already here", importance=0.9)
    exported = await _export(client, "json")
    document = json.loads(exported)
    document["memories"].append({"content": "Brought by the file", "category": "event"})
    document["memories"].append({"content": "Brought by the file", "category": "personal"})
    document["memories"].append({"content": "x" * (settings.memory_content_max_chars + 1)})

    response = await client.post(
        "/memories/import", files=_upload(json.dumps(document).encode(), "memories.json")
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total": 4,
        "imported": 1,
        "already_present": 1,
        "duplicates": 1,
        "invalid": 1,
    }
    stored = await _stored(async_session, test_user)
    assert set(stored) == {"Already here", "Brought by the file"}
    assert stored["Already here"].id == kept.id
    # Only the new memory reached the provider.
    assert [call.args[0] for call in provider.await_args_list] == [["Brought by the file"]]


async def test_importing_the_same_file_twice_creates_nothing_the_second_time(
    async_session: AsyncSession, test_user: User, client: httpx.AsyncClient, provider: AsyncMock
) -> None:
    await _create(async_session, test_user, "One fact")
    exported = await _export(client, "csv")
    await client.delete("/memories", params={"preserve_pinned": "false"})
    first = await client.post("/memories/import", files=_upload(exported))
    assert first.json()["imported"] == 1
    provider.reset_mock()

    second = await client.post("/memories/import", files=_upload(exported))

    assert second.json() == {
        "total": 1,
        "imported": 0,
        "already_present": 1,
        "duplicates": 0,
        "invalid": 0,
    }
    provider.assert_not_awaited()
    count = await async_session.scalar(
        select(func.count()).select_from(Memory).where(Memory.user_id == test_user.id)
    )
    assert count == 1


async def test_no_transaction_is_held_while_the_vectors_are_computed(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    provider: AsyncMock,
) -> None:
    """A batch of vectors is a network call: every read is over before it (ADR-304)."""
    held: list[bool] = []

    def record(texts: list[str]) -> list[list[float]]:
        held.append(async_session.in_transaction())
        return [_VECTOR for _ in texts]

    provider.side_effect = record
    document = {"memories": [{"content": "A fact to embed", "category": "personal"}]}

    response = await client.post(
        "/memories/import", files=_upload(json.dumps(document).encode(), "memories.json")
    )

    assert response.status_code == 200, response.text
    assert held == [False]


async def test_a_memory_written_while_the_vectors_were_computed_is_not_created_twice(
    async_session: AsyncSession, test_user: User, client: httpx.AsyncClient, provider: AsyncMock
) -> None:
    """Nothing is held across the provider, so another writer may come in between: the
    read taken again under the account's lock is the one that sees it."""

    async def answer_after_a_rival_wrote(texts: list[str]) -> list[list[float]]:
        await _create(async_session, test_user, "Written in between")
        return [_VECTOR for _ in texts]

    provider.side_effect = answer_after_a_rival_wrote
    document = {
        "memories": [
            {"content": "Written in between", "category": "event"},
            {"content": "Still new", "category": "personal"},
        ]
    }

    response = await client.post(
        "/memories/import", files=_upload(json.dumps(document).encode(), "memories.json")
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total": 2,
        "imported": 1,
        "already_present": 1,
        "duplicates": 0,
        "invalid": 0,
    }
    rivals = await async_session.scalar(
        select(func.count()).select_from(Memory).where(Memory.content == "Written in between")
    )
    assert rivals == 1
    assert (await _stored(async_session, test_user))["Written in between"].category == "personal"


async def test_a_provider_that_fails_imports_nothing(
    async_session: AsyncSession, test_user: User, client: httpx.AsyncClient, provider: AsyncMock
) -> None:
    provider.side_effect = RuntimeError("provider down")
    document = {
        "memories": [
            {"content": "First of two", "category": "personal"},
            {"content": "Second of two", "category": "personal"},
        ]
    }

    response = await client.post(
        "/memories/import", files=_upload(json.dumps(document).encode(), "memories.json")
    )

    assert response.status_code == 500
    assert await _stored(async_session, test_user) == {}


async def test_the_usage_limit_refuses_before_anything_is_paid_or_written(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    provider: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        creation_embeddings,
        "enforce_usage_limit",
        AsyncMock(side_effect=UsageLimitExceededError(limit_name="cycle_cost")),
    )
    document = {"memories": [{"content": "Refused by the ceiling", "category": "personal"}]}

    response = await client.post(
        "/memories/import", files=_upload(json.dumps(document).encode(), "memories.json")
    )

    assert response.status_code == 429
    provider.assert_not_awaited()
    assert await _stored(async_session, test_user) == {}


class TestAFileRefusedWhole:
    async def test_a_file_that_is_not_an_export(
        self,
        async_session: AsyncSession,
        test_user: User,
        client: httpx.AsyncClient,
        provider: AsyncMock,
    ) -> None:
        response = await client.post(
            "/memories/import", files=_upload(b"just a note somebody saved", "notes.txt")
        )

        assert response.status_code == 400
        assert response.json()["detail"] == APIMessages.memory_import_file_unreadable()
        provider.assert_not_awaited()

    async def test_more_memories_than_one_import_takes(
        self,
        async_session: AsyncSession,
        test_user: User,
        client: httpx.AsyncClient,
        provider: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "memory_import_max_memories", 2)
        document = {
            "memories": [
                {"content": f"Fact number {index}", "category": "personal"} for index in range(3)
            ]
        }

        response = await client.post(
            "/memories/import", files=_upload(json.dumps(document).encode(), "memories.json")
        )

        assert response.status_code == 400
        # The limit that refused is the limit that is said, beside what the file held.
        assert response.json()["detail"] == APIMessages.memory_import_too_many(3, 2)
        assert await _stored(async_session, test_user) == {}

    async def test_a_file_larger_than_an_import_reads(
        self,
        async_session: AsyncSession,
        test_user: User,
        client: httpx.AsyncClient,
        provider: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "memory_import_max_file_kb", 16)
        oversized = b"content,category\n" + b"x" * (16 * 1024)

        response = await client.post("/memories/import", files=_upload(oversized))

        assert response.status_code == 413
        assert response.json()["detail"] == APIMessages.memory_import_file_too_large(16)
        provider.assert_not_awaited()
