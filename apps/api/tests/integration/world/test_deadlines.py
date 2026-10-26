"""A connected but silent Redis must not pin world I/O indefinitely."""

import asyncio
import time
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.world.store import WorldStore
from src.domains.world.transport import socket_slot

pytestmark = pytest.mark.integration


@pytest.fixture
async def silent_redis() -> AsyncIterator[Redis]:
    writers: list[asyncio.StreamWriter] = []

    async def connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writers.append(writer)
        await reader.read()

    server = await asyncio.start_server(connected, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = Redis(host="127.0.0.1", port=port, socket_timeout=10)
    try:
        yield client
    finally:
        await client.aclose()
        for writer in writers:
            writer.close()
            await writer.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.parametrize("write", [False, True])
async def test_total_authority_deadline_cancels_silent_network_io(
    silent_redis: Redis, write: bool
) -> None:
    store = WorldStore(silent_redis, namespace="deadline", ttl=1800, timeout=0.05)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        if write:
            await store.update(lambda state, now: None)
        else:
            await store.read()
    assert time.monotonic() - started < 1


async def test_unauthenticated_socket_claim_has_a_total_network_deadline(
    silent_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "world_authority_timeout", 0.05)
    async with asyncio.timeout(0.5):
        with pytest.raises(TimeoutError):
            async with socket_slot(silent_redis, "proof-controller"):
                pytest.fail("Silent Redis must never grant a socket slot")
