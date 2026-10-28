"""Validate byte limits and protocol before dispatch; no provider or database."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from redis.asyncio import Redis
from starlette.types import Message
from starlette.websockets import WebSocket

from src.domains.world.authority import Identity
from src.domains.world.policy import WorldPolicy
from src.domains.world.schemas import WorldCommand
from src.domains.world.service import WorldConnection, WorldService
from src.domains.world.socket_models import EmoteCommand
from src.domains.world.store import WorldStore
from src.domains.world.transport import _receive, decode_command, origin_allowed

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "origin", [None, "null", "https://evil.invalid", "https://lia.invalid.evil.invalid"]
)
def test_socket_origins_are_exact_and_never_inferred(origin: str | None) -> None:
    assert not origin_allowed(origin, ["https://lia.invalid"])


def test_configured_origin_is_accepted_without_accepting_a_substring() -> None:
    assert origin_allowed("https://lia.invalid", ["https://lia.invalid"])


def test_frame_limit_counts_utf8_bytes_before_parsing() -> None:
    with pytest.raises(ValueError, match="frame_limit"):
        decode_command('"' + "界" * 1000 + '"', 2000)


@pytest.mark.parametrize(
    "text", ["null", "[]", '{"type":"tool"}', '{"type":"heartbeat","version":2}', '{"dx":NaN}']
)
def test_invalid_payload_cannot_reach_dispatch(text: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        decode_command(text, 8192)


def test_valid_move_round_trips_without_client_chosen_actor_fields() -> None:
    epoch = str(uuid4())
    value = decode_command(
        json.dumps({"type": "move", "version": 2, "epoch": epoch, "seq": 1, "dx": 0.5, "dy": -0.5}),
        8192,
    )
    assert value.type == "move" and value.epoch == epoch


class _RecordingService(WorldService):
    """The socket lanes' service, recording which door each frame took."""

    def __init__(self, store: WorldStore, *, refused: bool) -> None:
        super().__init__(store)
        self.refused = refused
        self.calls: list[str] = []

    async def refuse_emote(self, connection: WorldConnection, command: EmoteCommand) -> bool:
        self.calls.append("refuse_emote")
        return self.refused

    async def policy(self, cookie: str, connection: WorldConnection) -> WorldPolicy:
        self.calls.append("policy")
        return WorldPolicy("fr", frozenset(), frozenset())

    async def command(self, connection: WorldConnection, command: WorldCommand) -> None:
        self.calls.append(command.type)


@pytest.mark.parametrize(
    ("refused", "doors"),
    [
        (True, ["refuse_emote", "leave"]),
        (False, ["refuse_emote", "policy", "emote", "leave"]),
    ],
)
async def test_a_refused_gesture_settles_without_reading_native_policy(
    refused: bool, doors: list[str]
) -> None:
    epoch = str(uuid4())
    frames = [
        json.dumps({"type": "emote", "version": 2, "epoch": epoch, "seq": 1, "emote": "wave"}),
        json.dumps({"type": "leave", "version": 2, "epoch": epoch}),
    ]
    incoming: list[Message] = [{"type": "websocket.connect"}]
    incoming += [{"type": "websocket.receive", "text": frame} for frame in frames]

    async def receive() -> Message:
        return incoming.pop(0)

    async def send(message: Message) -> None:
        return None

    socket = WebSocket({"type": "websocket", "path": "/world/ws", "headers": []}, receive, send)
    await socket.accept()
    # Never contacted: the recording service answers every door itself.
    redis = Redis.from_url("redis://127.0.0.1:1/15")
    try:
        service = _RecordingService(WorldStore(redis, namespace="unit", ttl=60), refused=refused)
        connection = WorldConnection(Identity(str(uuid4()), "Visitor", "fr"), "controller")
        await _receive(socket, "cookie", service, connection)
    finally:
        await redis.aclose()
    assert service.calls == doors
