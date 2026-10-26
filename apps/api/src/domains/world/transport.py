"""Bounded socket I/O. Private policy is resolved before every projection lane."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import REDIS_KEY_WORLD_RUNTIME_PREFIX
from src.domains.world.schemas import COMMAND_ADAPTER, WorldCommand
from src.domains.world.service import WorldConnection, WorldService
from src.domains.world.store import WorldUnavailable
from src.infrastructure.locks.redis_claim import held_claim, try_claim


def origin_allowed(origin: str | None, origins: str | list[str]) -> bool:
    """Match a complete configured origin; never accept missing, substring or inferred origins."""
    allowed = origins if isinstance(origins, list) else origins.split(",")
    return origin is not None and origin in {value.strip().rstrip("/") for value in allowed}


def decode_command(text: str, limit: int) -> WorldCommand:
    """Enforce the UTF-8 byte limit before strict discriminated command validation."""
    if len(text.encode("utf-8")) > limit:
        raise ValueError("frame_limit")
    return COMMAND_ADAPTER.validate_json(text)


async def receive_text(socket: WebSocket, limit: int) -> str:
    """Receive one bounded text frame, refusing binary frames and propagating disconnects."""
    event = await socket.receive()
    if event["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(event.get("code", 1000))
    text = event.get("text")
    if not isinstance(text, str) or len(text.encode("utf-8")) > limit:
        raise ValueError("frame_limit")
    return text


@asynccontextmanager
async def socket_slot(redis: Redis, token: str) -> AsyncIterator[None]:
    """Own, renew and cancellation-safely release one distributed bounded socket claim."""
    claims = _ClaimRedis(redis)
    key = await _acquire_slot(claims, token)
    async with held_claim(
        claims,
        key,
        token,
        ttl_seconds=10,
        max_hold_seconds=settings.world_state_seconds,
    ):
        yield


class _ClaimRedis:
    """Bound native claim I/O, including its cancellation-safe release."""

    def __init__(self, redis: Redis) -> None:
        """Wrap Redis claim operations in the World authority I/O timeout."""
        self.redis = redis

    async def set(self, key: str, token: str, *, ex: int, nx: bool) -> bool:
        """Acquire a socket claim with bounded Redis SET I/O and the caller's ownership token."""
        async with asyncio.timeout(settings.world_authority_timeout):
            return bool(await self.redis.set(key, token, ex=ex, nx=nx))

    async def eval(self, script: str, count: int, key: str, token: str, *values: int) -> int:
        """Execute an ownership-conditioned claim script within the authority timeout."""
        async with asyncio.timeout(settings.world_authority_timeout):
            return int(await self.redis.eval(script, count, key, token, *values))


async def _acquire_slot(redis: _ClaimRedis, token: str) -> str:
    """Bound the complete search for an available distributed socket slot."""
    async with asyncio.timeout(settings.world_authority_timeout):
        return await _find_slot(redis, token)


async def _find_slot(redis: _ClaimRedis, token: str) -> str:
    """Try configured socket slots once each, failing closed when capacity is exhausted."""
    for index in range(settings.world_socket_limit):
        key = f"{REDIS_KEY_WORLD_RUNTIME_PREFIX}{settings.world_namespace}:socket:{index}"
        if await try_claim(redis, key, token, ttl_seconds=10):
            return key
    raise WorldUnavailable("socket_limit")


async def _receive(
    socket: WebSocket, cookie: str, service: WorldService, connection: WorldConnection
) -> None:
    """Bound command rate and frame size; recheck policy before takeover or admission."""
    started, count = time.monotonic(), 0
    while True:
        text = await receive_text(socket, settings.world_frame_bytes)
        now = time.monotonic()
        if now - started >= 1:
            started, count = now, 0
        count += 1
        if count > settings.world_input_rate:
            raise ValueError("frame_rate")
        command = decode_command(text, settings.world_frame_bytes)
        if command.type in {"accept", "takeover"}:
            await service.policy(cookie, connection)
        await service.command(connection, command)
        if command.type == "leave":
            return


async def _send(
    socket: WebSocket, cookie: str, service: WorldService, connection: WorldConnection
) -> None:
    """Send filtered snapshots with periodic policy refresh and bounded socket I/O."""
    policy = await service.policy(cookie, connection)
    checked = time.monotonic()
    while True:
        if time.monotonic() - checked >= 2:
            policy = await service.policy(cookie, connection)
            checked = time.monotonic()
        view = await service.view(connection, policy)
        async with asyncio.timeout(settings.world_send_timeout):
            await socket.send_text(view.model_dump_json())
        # An idle connection keeps its private away presence, while admission
        # capacity has already been released. Rejoin still uses normal FIFO.
        await asyncio.sleep(settings.world_tick_seconds)


async def run_connection(
    socket: WebSocket, cookie: str, service: WorldService, connection: WorldConnection
) -> None:
    """Own both socket lanes and cancel/await the sibling when either lane ends."""
    tasks = [
        asyncio.create_task(_receive(socket, cookie, service, connection), name="world_receive"),
        asyncio.create_task(_send(socket, cookie, service, connection), name="world_send"),
    ]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
