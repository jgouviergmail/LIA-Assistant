"""Source exact discovery remains opt-in, anti-enumeration and quota bounded."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.config import settings
from src.domains.agents.tools import application_peer_tools
from src.domains.peers.models import PeerBlock
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["match", "prefix", "blocked", "rate_limit"])
async def test_exact_owned_discovery_respects_source_population_and_shared_quota(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    visible = User(
        id=uuid4(),
        email=f"visible-{uuid4()}@example.com",
        hashed_password="controlled",
        full_name="Élodie Exemple",
        discovery_enabled=True,
        is_active=True,
    )
    hidden = User(
        id=uuid4(),
        email=f"hidden-{uuid4()}@example.com",
        hashed_password="controlled",
        full_name="Élodie Exemple",
        discovery_enabled=False,
        is_active=True,
    )
    async_session.add_all([visible, hidden])
    await async_session.flush()
    if scenario == "blocked":
        async_session.add(PeerBlock(blocker_id=visible.id, blocked_id=owner))
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_peer_tools, "get_db_context", session)
    if scenario == "rate_limit":
        monkeypatch.setattr(settings, "peers_discovery_rate_limit_calls", 1)
        limiter = await get_rate_limiter()
        assert await limiter.acquire(
            key=f"auth:peers_discovery:user:{owner}",
            max_calls=1,
            window_seconds=settings.peers_discovery_rate_limit_window_seconds,
        )
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_peer_tools.search_lia_peer_directory_tool.coroutine(
            query={"query": "elodie" if scenario == "prefix" else "elodie exemple"},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    if scenario == "rate_limit":
        assert not result.success and result.error_code == "RATE_LIMIT_EXCEEDED"
    else:
        assert result.success
        rows = result.structured_data["matches"]
        assert len(rows) == (1 if scenario == "match" else 0)
        if rows:
            assert rows[0]["peer_id"] == str(visible.id)
            assert visible.email not in str(result.structured_data)


@pytest.mark.parametrize("scenario", ["redis_failure", "rate_off", "late_off"])
async def test_directory_refuses_dependency_failure_and_late_access(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_peer_tools, "get_db_context", session)
    calls = AsyncMock(return_value=[])

    async def search(service, actor_id, query):
        assert actor_id == owner
        if scenario == "late_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return await calls(actor_id, query)

    monkeypatch.setattr(PeersService, "search_discoverable", search)
    if scenario == "redis_failure":
        monkeypatch.setattr(
            "src.domains.agents.application.peer_discovery.get_rate_limiter",
            AsyncMock(side_effect=RedisConnectionError("Unavailable")),
        )
    if scenario == "rate_off":
        limiter = await get_rate_limiter()
        original = limiter.acquire

        async def withdraw(**kwargs):
            allowed = await original(**kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return allowed

        monkeypatch.setattr(limiter, "acquire", withdraw)
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_peer_tools.search_lia_peer_directory_tool.coroutine(
            query={"query": "Alice"},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    assert not result.success and not result.structured_data
    if scenario != "late_off":
        calls.assert_not_awaited()
