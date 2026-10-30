"""The catalogue snapshot through REAL PostgreSQL: JSONB round trip and conditional publication (M1).

A mocked session never executes ``SELECT … FOR UPDATE`` nor stores a JSONB value,
so the three properties the conditional publication guarantees are proven on
the database itself: what is written reads back equal, an edited URL refuses
the old catalogue, and a discovery reserved first and published last never
overwrites a newer one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.user_mcp.catalogue_publication import publish_catalogue_if_current
from src.domains.user_mcp.models import UserMCPServer
from src.infrastructure.mcp.auth import build_auth_for_server
from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint
from src.infrastructure.mcp.catalogue_snapshot import (
    CatalogueSnapshot,
    ValidSnapshot,
    build_snapshot,
    parse_catalogue_snapshot,
)
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration

URL = "https://mcp.example.test/mcp"
TOOLS = [{"name": "search", "description": "Search"}, {"name": "fetch", "description": "Fetch"}]


async def _committed_server(engine: AsyncEngine, owners: list[UUID]) -> tuple[UUID, UUID, str]:
    owner = await commit_owner(engine, owners)
    async with AsyncSession(engine) as db:
        server = UserMCPServer(user_id=owner, name="Notes", url=URL, status="active")
        db.add(server)
        await db.flush()
        fingerprint = connection_fingerprint(
            server.url, build_auth_for_server(server), server.timeout_seconds, server.extra_headers
        )
        server_id = server.id
        await db.commit()
    return owner, server_id, fingerprint


def _snapshot(
    fingerprint: str, generation: int, tools: list[dict[str, str]] = TOOLS
) -> CatalogueSnapshot:
    return build_snapshot(
        tools=tools,
        configuration_fingerprint=fingerprint,
        discovered_at=datetime(2026, 10, 28, 9, 0, tzinfo=UTC),
        generation=generation,
        has_reference_tool=True,
        server_ttl_ms=60_000,
        cache_scope="private",
        server_instructions="Search first.",
        reference_content="# Guide",
        reference_fetched_at=datetime(2026, 10, 28, 9, 1, tzinfo=UTC),
    )


async def _stored(engine: AsyncEngine, server_id: UUID) -> object:
    async with AsyncSession(engine) as db:
        return (
            await db.execute(
                select(UserMCPServer.discovered_tools_cache).where(UserMCPServer.id == server_id)
            )
        ).scalar_one()


async def test_published_snapshot_reads_back_equal(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    owner, server_id, fingerprint = await _committed_server(async_engine, committed_user_ids)
    snapshot = _snapshot(fingerprint, generation=10)

    outcome = await publish_catalogue_if_current(
        user_id=owner, server_id=server_id, snapshot=snapshot, tool_embeddings=None
    )

    assert outcome == "published"
    read = parse_catalogue_snapshot(await _stored(async_engine, server_id))
    assert isinstance(read, ValidSnapshot) and read.snapshot == snapshot


async def test_publication_refused_after_url_edit(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    owner, server_id, fingerprint = await _committed_server(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(UserMCPServer)
            .where(UserMCPServer.id == server_id)
            .values(url="https://other.example.test/mcp")
        )
        await db.commit()

    outcome = await publish_catalogue_if_current(
        user_id=owner,
        server_id=server_id,
        snapshot=_snapshot(fingerprint, 10),
        tool_embeddings=None,
    )

    assert outcome == "configuration_changed"
    assert await _stored(async_engine, server_id) is None


async def test_older_generation_never_overwrites_newer(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    """Reserved first (7), published last: refused; the newer catalogue (8) stays."""
    owner, server_id, fingerprint = await _committed_server(async_engine, committed_user_ids)
    newer = _snapshot(fingerprint, 8, tools=[{"name": "search", "description": "Search v2"}])
    older = _snapshot(fingerprint, 7)

    first = await publish_catalogue_if_current(
        user_id=owner, server_id=server_id, snapshot=newer, tool_embeddings=None
    )
    late = await publish_catalogue_if_current(
        user_id=owner, server_id=server_id, snapshot=older, tool_embeddings=None
    )

    assert (first, late) == ("published", "superseded")
    read = parse_catalogue_snapshot(await _stored(async_engine, server_id))
    assert isinstance(read, ValidSnapshot) and read.snapshot.generation == 8


async def test_another_account_cannot_publish_into_the_row(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    _owner, server_id, fingerprint = await _committed_server(async_engine, committed_user_ids)
    stranger = await commit_owner(async_engine, committed_user_ids)

    outcome = await publish_catalogue_if_current(
        user_id=stranger,
        server_id=server_id,
        snapshot=_snapshot(fingerprint, 9),
        tool_embeddings=None,
    )

    assert outcome == "missing"
