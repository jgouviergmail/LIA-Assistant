"""Close codes: another generation reloads (4426), a bad frame is refused (1008), a defect is 1011.

The three classes are told apart before anything else is trusted: the protocol
generation is read from the frame's envelope before strict validation, so an
outdated client is asked to reload instead of being treated as a hostile one.
"""

import json
from collections.abc import Iterator
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from starlette.types import Message
from starlette.websockets import WebSocket

from src.core.constants import (
    WORLD_SOCKET_CLOSE_INTERNAL,
    WORLD_SOCKET_CLOSE_POLICY,
    WORLD_SOCKET_CLOSE_UPGRADE_REQUIRED,
)
from src.domains.world import router as world_router
from src.domains.world.collision import SCENE
from src.domains.world.schemas import AuthFrame, WorldCommand
from src.domains.world.service import WorldService
from src.domains.world.socket_models import (
    SOCKET_PROTOCOL_VERSION,
    ClientProtocolUpgradeRequired,
    require_socket_generation,
)
from src.domains.world.store import WorldIntegrityError, WorldStore
from src.domains.world.transport import decode_command

pytestmark = pytest.mark.unit


def _socket(*frames: str) -> tuple[WebSocket, list[Message]]:
    """A real Starlette socket over an in-memory ASGI channel."""
    incoming: list[Message] = [
        {"type": "websocket.connect"},
        *({"type": "websocket.receive", "text": frame} for frame in frames),
    ]
    sent: list[Message] = []

    async def receive() -> Message:
        return incoming.pop(0) if incoming else {"type": "websocket.disconnect", "code": 1000}

    async def send(message: Message) -> None:
        sent.append(message)

    return WebSocket({"type": "websocket", "path": "/world/ws", "headers": []}, receive, send), sent


def _heartbeat(version: object) -> str:
    return json.dumps(
        {"type": "heartbeat", "version": version, "epoch": str(uuid4()), "visible": True}
    )


def _frame_models() -> Iterator[type[BaseModel]]:
    """Every model a client may send: the authentication frame and each command."""
    yield AuthFrame
    union = get_args(WorldCommand)[0]
    yield from get_args(union)


def test_every_client_frame_declares_exactly_the_current_generation() -> None:
    models = list(_frame_models())
    assert len(models) == 7
    for model in models:
        version = model.model_fields["version"].annotation
        assert get_args(version) == (SOCKET_PROTOCOL_VERSION,), model


@pytest.mark.parametrize("version", [1, 3, 0, -2])
def test_another_integer_generation_asks_for_a_reload(version: int) -> None:
    with pytest.raises(ClientProtocolUpgradeRequired):
        decode_command(_heartbeat(version), 8192)


@pytest.mark.parametrize("version", [True, 2.0, "1", None])
def test_a_malformed_version_is_an_ordinary_invalid_frame(version: object) -> None:
    with pytest.raises(ValidationError):
        decode_command(_heartbeat(version), 8192)


@pytest.mark.parametrize("text", ["null", "[1]", "not json", '{"type":"heartbeat"}', "[" * 400])
def test_a_frame_claiming_no_generation_is_left_to_the_strict_reader(text: str) -> None:
    require_socket_generation(text)
    with pytest.raises(ValueError):
        decode_command(text, 8192)


def test_the_current_generation_is_validated_normally() -> None:
    assert decode_command(_heartbeat(SOCKET_PROTOCOL_VERSION), 8192).type == "heartbeat"


async def test_an_old_authentication_frame_asks_for_a_reload_before_any_ticket_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("an outdated frame must not reach the ticket store")

    monkeypatch.setattr(world_router, "WorldTickets", forbidden)
    old = {"type": "authenticate", "version": 1, "scene": SCENE, "ticket": "v" * 43}
    socket, _ = _socket(json.dumps(old))
    await socket.accept()
    # Never contacted: the refusal happens before the first Redis call.
    redis = Redis.from_url("redis://127.0.0.1:1/15")
    try:
        service = WorldService(WorldStore(redis, namespace="unit", ttl=60))
        with pytest.raises(ClientProtocolUpgradeRequired):
            await world_router.authenticate(socket, service)
    finally:
        await redis.aclose()


def _invalid_frame() -> ValidationError:
    with pytest.raises(ValidationError) as refused:
        decode_command(json.dumps({"type": "move", "version": SOCKET_PROTOCOL_VERSION}), 8192)
    return refused.value


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (ClientProtocolUpgradeRequired(), WORLD_SOCKET_CLOSE_UPGRADE_REQUIRED),
        (_invalid_frame(), WORLD_SOCKET_CLOSE_POLICY),
        (ValueError("frame_rate"), WORLD_SOCKET_CLOSE_POLICY),
        (WorldIntegrityError("game_members", "games"), WORLD_SOCKET_CLOSE_INTERNAL),
    ],
)
async def test_each_failure_class_closes_the_socket_with_its_own_code(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, code: int
) -> None:
    async def serve(socket: WebSocket) -> None:
        raise failure

    monkeypatch.setattr(world_router, "_serve", serve)
    socket, sent = _socket()
    await world_router.world_socket(socket)
    assert sent == [{"type": "websocket.close", "code": code, "reason": ""}]
