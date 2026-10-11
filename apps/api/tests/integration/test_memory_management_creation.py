"""The shared UI creation command persists a deterministic identity without paid probes."""

from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
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


async def test_ui_creation_keeps_generated_identity_and_manual_recall_opt_out(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_user.memory_enabled = False
    await async_session.commit()
    provider = AsyncMock(return_value=(None, None))
    monkeypatch.setattr("src.domains.memories.service._generate_dual_embeddings", provider)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: async_session
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
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
    provider.assert_awaited_once_with("Explicit UI instruction", "")


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
