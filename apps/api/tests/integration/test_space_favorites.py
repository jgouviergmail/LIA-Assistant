"""Prove favorite writes, ownership and rollback through the real space service and HTTP."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import ResourceConflictError
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.space_update import execute_space_update, prepare_space_update
from src.domains.agents.application.space_update_schemas import SpaceUpdateInput
from src.domains.rag_spaces.models import RAGSpace
from src.domains.rag_spaces.router import list_spaces, update_space
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


async def test_favorites_round_trip_without_changing_managed_space_activation(
    async_session: AsyncSession, test_user: User
) -> None:
    """An absolute preference is idempotent, persisted, listed and private to its owner."""
    foreign = User(id=uuid4(), email=f"favorite-{uuid4()}@example.com")
    async_session.add(foreign)
    await async_session.flush()
    managed = RAGSpace(user_id=test_user.id, name="Kept answers", kind="bookmarks", is_active=False)
    other = RAGSpace(user_id=foreign.id, name="Other owner's space")
    async_session.add_all([managed, other])
    await async_session.flush()
    assert managed.is_favorite is False

    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    async def owner() -> User:
        return test_user

    app = FastAPI()
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_active_session] = owner
    app.add_api_route("/spaces", list_spaces, methods=["GET"])
    app.add_api_route("/spaces/{space_id}", update_space, methods=["PATCH"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for favorite in (True, True, False):
            response = await client.patch(f"/spaces/{managed.id}", json={"is_favorite": favorite})
            assert response.status_code == 200
            assert response.json()["is_favorite"] is favorite
            assert response.json()["is_active"] is False
            await async_session.refresh(managed)
            assert managed.is_favorite is favorite
            rows = (await client.get("/spaces")).json()["spaces"]
            assert len(rows) == 1
            assert rows[0]["is_favorite"] is favorite
        refused = await client.patch(f"/spaces/{other.id}", json={"is_favorite": True})
        assert refused.status_code == 404
        await async_session.refresh(other)
        assert other.is_favorite is False


async def test_favorite_write_participates_in_its_callers_transaction(
    async_session: AsyncSession, test_user: User
) -> None:
    """A rolled-back preference never leaks into a later listing."""
    space = RAGSpace(user_id=test_user.id, name="Transactional preference")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    transaction = await async_session.begin_nested()
    await RAGSpaceService(async_session).update_space(
        space_id, test_user.id, is_favorite=True, commit=False
    )
    assert space.is_favorite is True
    await transaction.rollback()
    await async_session.refresh(space)
    assert space.is_favorite is False


@pytest.mark.parametrize("favorite", [True, False])
async def test_conversation_favorites_apply_exact_approved_state(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, favorite: bool
) -> None:
    """The inherited model field is previewed, applied and returned without activating a space."""
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = RAGSpace(
        user_id=test_user.id,
        name="Managed favorite",
        kind="bookmarks",
        is_active=False,
        is_favorite=not favorite,
    )
    async_session.add(space)
    await async_session.commit()
    draft = await prepare_space_update(
        async_session, test_user.id, SpaceUpdateInput(space_id=space.id, is_favorite=favorite)
    )
    assert space.is_favorite is not favorite
    receipt = PreferenceWriteReceipt()
    await execute_space_update(async_session, test_user.id, draft, receipt)
    await async_session.refresh(space)
    assert receipt.committed and not receipt.no_op
    assert space.is_favorite is favorite
    assert space.is_active is False


async def test_ui_favorite_change_retires_a_conversation_approval(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An intervening UI preference write requires a fresh exact confirmation."""
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = RAGSpace(user_id=test_user.id, name="Before approval")
    async_session.add(space)
    await async_session.commit()
    draft = await prepare_space_update(
        async_session, test_user.id, SpaceUpdateInput(space_id=space.id, name="Approved name")
    )
    await RAGSpaceService(async_session).update_space(space.id, test_user.id, is_favorite=True)
    with pytest.raises(ResourceConflictError):
        await execute_space_update(async_session, test_user.id, draft, PreferenceWriteReceipt())
    await async_session.rollback()
    await async_session.refresh(space)
    assert space.is_favorite is True
    assert space.name == "Before approval"
