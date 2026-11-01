"""Per-tool choices on real PostgreSQL (spec 2026-10-30 D6).

A choice is written one tool at a time: two writes on two tools both persist and a
second write on one tool replaces it — the (server, tool) constraint is the identity,
honoured by an upsert. A choice leaves with its server (FK cascade), and the database
refuses a value outside the vocabulary. Proven on the statements themselves: a mocked
session never executes the upsert or the cascade.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.tool_choice_repository import UserMCPToolChoiceRepository
from src.infrastructure.mcp.confirmation import StoredToolChoice, ToolChoice
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _server(db: AsyncSession, name: str = "Notes") -> UUID:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    server = UserMCPServer(user_id=user.id, name=name, url="https://mcp.example.test/mcp")
    db.add(server)
    await db.flush()
    return server.id


async def test_two_tools_written_apart_both_persist_and_a_rewrite_replaces(
    async_session: AsyncSession,
) -> None:
    server_id = await _server(async_session)
    repo = UserMCPToolChoiceRepository(async_session)

    await repo.set_choice(server_id, "delete_note", ToolChoice.NEVER, "fp-delete")
    await repo.set_choice(server_id, "read_note", ToolChoice.ALWAYS, "fp-read")
    await repo.set_choice(server_id, "delete_note", ToolChoice.ALWAYS, "fp-delete-2")

    assert await repo.choices_for([server_id]) == {
        server_id: {
            "delete_note": StoredToolChoice(ToolChoice.ALWAYS, "fp-delete-2"),
            "read_note": StoredToolChoice(ToolChoice.ALWAYS, "fp-read"),
        }
    }


async def test_clearing_returns_one_tool_to_the_levels_below(
    async_session: AsyncSession,
) -> None:
    server_id = await _server(async_session)
    repo = UserMCPToolChoiceRepository(async_session)
    await repo.set_choice(server_id, "delete_note", ToolChoice.NEVER, "fp")
    await repo.set_choice(server_id, "read_note", ToolChoice.ALWAYS, "fp")

    await repo.clear_choice(server_id, "delete_note")
    await repo.clear_choice(server_id, "absent_tool")

    assert await repo.choices_for([server_id]) == {
        server_id: {"read_note": StoredToolChoice(ToolChoice.ALWAYS, "fp")}
    }


async def test_choices_are_read_per_server_and_leave_with_their_server(
    async_session: AsyncSession,
) -> None:
    kept, deleted = await _server(async_session, "Kept"), await _server(async_session, "Gone")
    repo = UserMCPToolChoiceRepository(async_session)
    await repo.set_choice(kept, "a", ToolChoice.NEVER, "fp")
    await repo.set_choice(deleted, "a", ToolChoice.NEVER, "fp")

    await async_session.execute(
        text("DELETE FROM user_mcp_servers WHERE id = :id"), {"id": deleted}
    )

    assert await repo.choices_for([kept, deleted]) == {
        kept: {"a": StoredToolChoice(ToolChoice.NEVER, "fp")}
    }
    assert await repo.choices_for([]) == {}


async def test_the_database_refuses_a_value_outside_the_vocabulary(
    async_session: AsyncSession,
) -> None:
    server_id = await _server(async_session)

    with pytest.raises(IntegrityError):
        await async_session.execute(
            text(
                "INSERT INTO user_mcp_tool_choices "
                "(id, server_id, tool_name, choice, declaration_fingerprint, "
                "created_at, updated_at) "
                "VALUES (gen_random_uuid(), :server, 'a', 'sometimes', 'fp', now(), now())"
            ),
            {"server": server_id},
        )
