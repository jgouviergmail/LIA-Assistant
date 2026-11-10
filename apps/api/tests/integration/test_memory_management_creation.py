"""The shared UI creation command persists a deterministic identity without paid probes."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.memories.models import Memory
from src.domains.memories.router import router
from src.domains.memories.schemas import MemoryCreate
from src.domains.memories.service import MemoryService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_manual_creation_attributes_each_vector_before_the_provider(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infrastructure.llm.embedding_context import get_embedding_context

    owners: list[tuple[str | None, str | None, bool]] = []
    actor_id = str(test_user.id)

    async def vector(content: str) -> None:
        context = get_embedding_context()
        owners.append(
            (
                context.user_id if context else None,
                context.run_id if context else None,
                async_session.in_transaction(),
            )
        )

    monkeypatch.setattr(
        "src.domains.memories.creation_embeddings._generate_document_embedding", vector
    )
    response = await client.post(
        "/memories",
        json={
            "content": "A deliberately remembered quote",
            "category": "personal",
            "trigger_topic": "quote",
        },
    )
    assert response.status_code == 201, response.text
    assert len(owners) == 2
    assert all(owner == actor_id and run and not held for owner, run, held in owners)
    assert owners[0][1] == owners[1][1]


async def test_quota_refuses_manual_memory_before_provider_or_insert(
    async_session: AsyncSession, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.exceptions import UsageLimitExceededError
    from src.domains.memories import creation_embeddings
    from src.infrastructure.llm.embedding_context import get_embedding_context

    previous = get_embedding_context()
    budget = AsyncMock(side_effect=UsageLimitExceededError(limit_name="cycle_cost"))
    provider = AsyncMock()
    monkeypatch.setattr(creation_embeddings, "enforce_usage_limit", budget)
    monkeypatch.setattr(creation_embeddings, "_generate_document_embedding", provider)
    response = await client.post(
        "/memories", json={"content": "Quota must refuse this fact", "category": "personal"}
    )
    assert response.status_code == 429
    provider.assert_not_awaited()
    assert get_embedding_context() == previous
    assert (
        await async_session.scalar(
            select(Memory).where(Memory.content == "Quota must refuse this fact")
        )
        is None
    )


@pytest.fixture
async def client(async_session: AsyncSession, test_user: User) -> AsyncIterator[httpx.AsyncClient]:
    async def authenticated(db: AsyncSession = Depends(get_db)) -> User:
        # Production reads the account on the request's own session (`_authenticate`):
        # the creation's transaction is open before the route's first line.
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


async def test_ui_creation_keeps_generated_identity_and_manual_recall_opt_out(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_user.memory_enabled = False
    await async_session.commit()
    provider = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.domains.memories.creation_embeddings._generate_document_embedding", provider
    )
    response = await client.post(
        "/memories",
        json={
            "content": "Explicit UI instruction",
            "category": "procedural",
            "importance": 0.0,
        },
    )
    assert response.status_code == 201
    saved = response.json()
    assert saved["id"] and saved["pinned"] is True and saved["importance"] == 0.0
    assert test_user.memory_enabled is False
    provider.assert_awaited_once_with("Explicit UI instruction")


async def test_no_transaction_is_held_while_the_vectors_are_computed(
    async_session: AsyncSession,
    test_user: User,
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vector is a network call: the authentication's read is committed before it (ADR-304)."""
    await async_session.commit()
    held: list[bool] = []

    async def provider(content: str) -> None:
        held.append(async_session.in_transaction())
        return None

    monkeypatch.setattr(
        "src.domains.memories.creation_embeddings._generate_document_embedding", provider
    )

    response = await client.post(
        "/memories", json={"content": "A created fact", "category": "personal"}
    )

    assert response.status_code == 201, response.text
    assert held == [False]
    created = await async_session.scalar(
        select(Memory).where(Memory.id == response.json()["id"], Memory.user_id == test_user.id)
    )
    assert created is not None and created.content == "A created fact"


@pytest.mark.parametrize("category", ["personal", "procedural"])
async def test_shared_creation_retains_command_identity_and_source_initial_pin(
    async_session: AsyncSession, test_user: User, category: str
) -> None:
    target = uuid4()
    provider = AsyncMock(return_value=(None, None))
    data = MemoryCreate.model_validate(
        {
            "content": "Explicit stored fact",
            "category": category,
            "importance": 0.0,
            "trigger_topic": "topic",
        }
    )
    row = await MemoryService(async_session, embedder=provider).create_from_management(
        test_user.id, data, memory_id=target
    )
    await async_session.commit()
    current = await async_session.scalar(select(Memory).where(Memory.id == target))
    assert current is row and row.user_id == test_user.id and row.importance == 0.0
    assert row.pinned is (category == "procedural") and row.char_count == len(data.content)
    assert row.embedding is None and row.context_biometric is None and row.usage_count == 0
    provider.assert_awaited_once_with(data.content, data.trigger_topic)
