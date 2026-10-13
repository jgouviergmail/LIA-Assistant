"""The persisted vector envelope is deferred by the turn's listing and read alone (ADR-283 amendment).

Real PostgreSQL: a deferred column on a row read in a session already closed
raises when touched, so the listing's deferral and the dedicated read are proven
on the statements themselves, not on a mocked session.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.repository import UserMCPServerRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

ENVELOPE: dict[str, Any] = {
    "embedding_model": "model:4",
    "tools": {"hub_search": {"description": [0.1, 0.2, 0.3, 0.4], "keywords": []}},
    "catalogue_fingerprint": "abc",
}


async def _server(db: AsyncSession, envelope: dict[str, Any] | None) -> tuple[UUID, UUID]:
    """One active server of a fresh account; returns ``(server id, user id)`` before any expiry."""
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    server = UserMCPServer(
        user_id=user.id,
        name="Hub",
        url="https://mcp.example.test/sse",
        tool_embeddings_cache=envelope,
    )
    db.add(server)
    await db.flush()
    return server.id, user.id


async def test_the_listing_does_not_load_the_envelope(async_session: AsyncSession) -> None:
    server_id, user_id = await _server(async_session, ENVELOPE)
    async_session.expire_all()  # the listing re-selects; the identity map is not the proof

    rows = await UserMCPServerRepository(async_session).get_enabled_active_for_user(user_id)

    assert [row.id for row in rows] == [server_id]
    assert "tool_embeddings_cache" in inspect(rows[0]).unloaded
    assert rows[0].name == "Hub", "every other column is loaded as before"


async def test_the_envelope_is_read_alone(async_session: AsyncSession) -> None:
    server_id, _ = await _server(async_session, ENVELOPE)
    async_session.expire_all()
    repo = UserMCPServerRepository(async_session)

    assert await repo.get_tool_embeddings_cache(server_id) == ENVELOPE


async def test_a_row_without_envelope_and_an_unknown_id_read_as_none(
    async_session: AsyncSession,
) -> None:
    server_id, _ = await _server(async_session, None)
    repo = UserMCPServerRepository(async_session)

    assert await repo.get_tool_embeddings_cache(server_id) is None
    assert await repo.get_tool_embeddings_cache(uuid4()) is None
