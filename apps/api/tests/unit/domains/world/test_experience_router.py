"""HTTP preference privacy: no reflected input and no caller-selected owner."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.users.models import User
from src.domains.world import experience_router
from src.domains.world.experience import ExperiencePreferences, ExperienceView

pytestmark = pytest.mark.unit


@pytest.fixture
async def http_experience(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, User, AsyncMock, AsyncMock]]:
    app = FastAPI()
    app.include_router(experience_router.router)
    owner = User(id=uuid4(), email="inert@example.invalid", is_active=True)
    view = ExperienceView(owner_id=str(owner.id), preferences=ExperiencePreferences())
    read = AsyncMock(return_value=view)
    write = AsyncMock(return_value=view)
    monkeypatch.setattr(experience_router, "read_owner_experience", read)
    monkeypatch.setattr(experience_router, "update_owner_experience", write)

    async def allow() -> None:
        return None

    async def identity() -> User:
        return owner

    for dependency in experience_router.router.dependencies:
        app.dependency_overrides[dependency.dependency] = allow
    app.dependency_overrides[get_current_active_session_for_stream] = identity
    app.dependency_overrides[experience_router._write_limit] = allow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://inert.test"
    ) as client:
        yield client, owner, read, write


async def test_private_experience_rejects_reflected_input_and_cannot_be_cached(
    http_experience: tuple[httpx.AsyncClient, User, AsyncMock, AsyncMock],
) -> None:
    client, _, _, write = http_experience
    response = await client.put(
        "/experience",
        json={"expected_revision": 0, "owner_id": "PRIVATE_OWNER", "show_route": "PRIVATE_VALUE"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": {"error_code": "INVALID_INPUT"}}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    write.assert_not_called()


async def test_preference_read_and_write_use_only_the_native_session_owner(
    http_experience: tuple[httpx.AsyncClient, User, AsyncMock, AsyncMock],
) -> None:
    client, owner, read, write = http_experience
    response = await client.get("/experience?owner_id=another-account")
    assert response.status_code == 200
    assert response.json()["owner_id"] == str(owner.id)
    read.assert_awaited_once_with(owner.id)
    response = await client.put("/experience", json={"expected_revision": 0, "show_route": False})
    assert response.status_code == 200
    assert write.await_args is not None and write.await_args.args[0] == owner.id
