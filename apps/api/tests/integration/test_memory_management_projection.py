"""Actual UI list, detail and JSON export use one projection without activating memory usage."""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.memories.models import Memory
from src.domains.memories.router import router
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_shared_projection_survives_real_ui_routes_and_memory_opt_out(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    test_user.memory_enabled = False
    row = Memory(
        user_id=test_user.id,
        content="Explicitly inspect my stored rule",
        category="procedural",
        importance=0.0,
        usage_count=0,
        pinned=False,
        char_count=37,
    )
    async_session.add(row)
    await async_session.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: async_session
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        detail = await client.get(f"/memories/{row.id}")
        listing = await client.get("/memories")
        exported = await client.get("/memories/export?format=json")
    assert detail.status_code == listing.status_code == exported.status_code == 200
    expected = detail.json()
    assert listing.json()["items"] == exported.json()["memories"] == [expected]
    assert expected["importance"] == 0.0 and expected["purge_risk"] == "protected"
    assert expected["context_biometric"] is None and "embedding" not in expected
    await async_session.refresh(row)
    assert row.usage_count == 0 and row.last_accessed_at is None
