"""Manual pin acknowledgements must describe the fresh active owned row."""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.memories.models import Memory
from src.domains.memories.router import router
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("invalidated", [False, True])
async def test_ui_pin_uses_current_state_even_with_cached_row_and_recall_disabled(
    async_session: AsyncSession, test_user: User, invalidated: bool
) -> None:
    test_user.memory_enabled = False
    row = Memory(
        user_id=test_user.id,
        content="Owned fact",
        category="personal",
        importance=0.7,
        pinned=False,
        char_count=10,
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id
    changes: dict[str, object] = {"pinned": True}
    if invalidated:
        changes["invalidated_at"] = datetime.now(UTC)
    await async_session.execute(
        update(Memory)
        .where(Memory.id == identity)
        .values(changes)
        .execution_options(synchronize_session=False)
    )
    await async_session.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: async_session
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        if invalidated:
            response = await client.patch(f"/memories/{identity}/pin", json={"pinned": False})
            assert response.status_code == 404
        else:
            response = await client.patch(f"/memories/{identity}/pin", json={"pinned": False})
            assert response.status_code == 200 and response.json()["pinned"] is False
    current = await async_session.scalar(
        select(Memory).where(Memory.id == identity).execution_options(populate_existing=True)
    )
    assert current is not None and current.pinned is invalidated
