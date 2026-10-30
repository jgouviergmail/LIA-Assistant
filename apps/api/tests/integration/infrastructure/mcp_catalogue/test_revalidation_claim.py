"""Background revalidation through REAL Redis and PostgreSQL (spec 2026-10-21 §5.4, M2).

A mocked cache cannot show two workers contending for one claim, and a mocked
session never runs ``SELECT … FOR UPDATE``: the three properties are proven on
the real services. Two « workers » are two pools in one process sharing the
Redis claim and the database row; only the server's network answer is scripted.

- One discovery for two concurrent revalidations (the second is ``busy``).
- A row edited while its catalogue is being rediscovered refuses the old one.
- A slow revalidation whose claim expired, taken over by a newer one, completes
  LAST and is refused: the newer catalogue stays (stale completion fenced by the
  generation, not by the claim).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.user_mcp.models import UserMCPServer
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.mcp.auth import build_auth_for_server
from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint
from src.infrastructure.mcp.catalogue_revalidation import (
    revalidate_catalogue,
    revalidation_claim_key,
)
from src.infrastructure.mcp.catalogue_snapshot import (
    ValidSnapshot,
    build_snapshot,
    parse_catalogue_snapshot,
    snapshot_to_jsonb,
)
from src.infrastructure.mcp.user_pool import DiscoveredCatalogue, UserMCPClientPool
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration

URL = "https://mcp.example.test/mcp"
MODULE = "src.infrastructure.mcp.catalogue_revalidation"


def _tools(name: str) -> list[dict[str, Any]]:
    return [{"name": name, "description": name, "input_schema": {"type": "object"}}]


class Worker:
    """One pool whose discovery waits at a gate and answers a scripted catalogue."""

    def __init__(self, answer: list[dict[str, Any]]) -> None:
        self.answer = answer
        self.entered = asyncio.Event()
        self.gate = asyncio.Event()
        self.discoveries = 0
        self.pool = UserMCPClientPool()
        self.pool._discover_tools = self.discover  # type: ignore[method-assign]

    async def discover(self, url: str, auth: object, timeout: int, **_: Any) -> Any:
        self.discoveries += 1
        self.entered.set()
        await self.gate.wait()
        return DiscoveredCatalogue(tools=list(self.answer))


@pytest.fixture
def workers(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Worker]]:
    """The pool each revalidation reads, in the order they start."""
    queue: list[Worker] = []
    monkeypatch.setattr(f"{MODULE}.usable_tool_embeddings", AsyncMock(return_value={}))

    def next_pool() -> UserMCPClientPool:
        return queue.pop(0).pool

    monkeypatch.setattr(f"{MODULE}.get_user_mcp_pool", next_pool)
    yield queue


async def _committed_server(engine: AsyncEngine, owners: list[UUID]) -> tuple[UUID, UUID]:
    owner = await commit_owner(engine, owners)
    async with AsyncSession(engine) as db:
        server = UserMCPServer(user_id=owner, name="Notes", url=URL, status="active")
        db.add(server)
        await db.flush()
        server.discovered_tools_cache = snapshot_to_jsonb(
            build_snapshot(
                tools=_tools("old"),
                configuration_fingerprint=connection_fingerprint(
                    server.url,
                    build_auth_for_server(server),
                    server.timeout_seconds,
                    server.extra_headers,
                ),
                discovered_at=datetime(2026, 10, 1, tzinfo=UTC),
                generation=1,
            )
        )
        server_id = server.id
        await db.commit()
    return owner, server_id


async def _stored_tools(engine: AsyncEngine, server_id: UUID) -> list[str]:
    async with AsyncSession(engine) as db:
        raw = (
            await db.execute(
                select(UserMCPServer.discovered_tools_cache).where(UserMCPServer.id == server_id)
            )
        ).scalar_one()
    read = parse_catalogue_snapshot(raw)
    assert isinstance(read, ValidSnapshot)
    return [str(tool["name"]) for tool in read.snapshot.tools]


async def test_revalidation_single_flight_across_workers(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], workers: list[Worker]
) -> None:
    owner, server_id = await _committed_server(async_engine, committed_user_ids)
    first, second = Worker(_tools("new")), Worker(_tools("new"))
    workers.extend([first, second])

    running = asyncio.create_task(revalidate_catalogue(owner, server_id))
    await asyncio.wait_for(first.entered.wait(), timeout=10)
    # Bounded: a claim that let the second worker in would wait at its gate for ever.
    assert await asyncio.wait_for(revalidate_catalogue(owner, server_id), timeout=10) == "busy"
    first.gate.set()

    assert await running == "published"
    assert (first.discoveries, second.discoveries) == (1, 0)
    assert await _stored_tools(async_engine, server_id) == ["new"]


async def test_revalidation_refused_after_edit(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], workers: list[Worker]
) -> None:
    owner, server_id = await _committed_server(async_engine, committed_user_ids)
    worker = Worker(_tools("new"))
    workers.append(worker)

    running = asyncio.create_task(revalidate_catalogue(owner, server_id))
    await asyncio.wait_for(worker.entered.wait(), timeout=10)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(UserMCPServer)
            .where(UserMCPServer.id == server_id)
            .values(url="https://moved.example.test/mcp")
        )
        await db.commit()
    worker.gate.set()

    assert await running == "configuration_changed"
    assert await _stored_tools(async_engine, server_id) == ["old"]


async def test_late_older_revalidation_never_overwrites_newer(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], workers: list[Worker]
) -> None:
    owner, server_id = await _committed_server(async_engine, committed_user_ids)
    slow, fresh = Worker(_tools("older")), Worker(_tools("newer"))
    workers.extend([slow, fresh])

    late = asyncio.create_task(revalidate_catalogue(owner, server_id))
    await asyncio.wait_for(slow.entered.wait(), timeout=10)
    # The slow holder's claim expires; another worker takes it and completes first.
    redis = await get_redis_cache()
    await redis.delete(revalidation_claim_key(owner, server_id))
    fresh.gate.set()
    assert await revalidate_catalogue(owner, server_id) == "published"
    slow.gate.set()

    assert await late == "superseded"
    assert await _stored_tools(async_engine, server_id) == ["newer"]
    assert await redis.get(revalidation_claim_key(owner, server_id)) is None
