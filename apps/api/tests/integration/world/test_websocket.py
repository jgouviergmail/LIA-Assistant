"""Real ASGI socket, tickets, controller claims and Redis; native policy port double.

The policy double supplies inert proof accounts, never a developer account or DB.
Native session/database policy is qualified separately against disposable SQL.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.world import router as world_router
from src.domains.world import service as world_service
from src.domains.world.avatar import AvatarAppearance, PublicWorldIdentity
from src.domains.world.collision import SCENE
from src.domains.world.policy import WorldPolicy
from src.domains.world.schemas import ReadyFrame, WorldState, WorldView
from src.domains.world.store import WorldStore
from src.domains.world.tickets import WorldTicket, WorldTickets, cookie_binding
from tests.redis_test_url import validated_test_redis_url

pytestmark = pytest.mark.integration
ORIGIN = "http://world-proof.invalid"


@dataclass
class Harness:
    client: TestClient
    revoked: set[str] = field(default_factory=set)

    def connect(
        self, stack: ExitStack, account: str, resume: str | None = None
    ) -> tuple[WebSocketTestSession, ReadyFrame, WorldView]:
        token = self.client.post(f"/proof-ticket/{account}").json()["ticket"]
        socket = stack.enter_context(
            self.client.websocket_connect(
                "/world/ws", headers={"origin": ORIGIN, "cookie": f"lia_session=proof-{account}"}
            )
        )
        socket.send_json(
            {
                "type": "authenticate",
                "version": 1,
                "scene": SCENE,
                "ticket": token,
                "resume": resume,
            }
        )
        ready = ReadyFrame.model_validate(socket.receive_json())
        return socket, ready, WorldView.model_validate(socket.receive_json())


@pytest.fixture
def world_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    url = validated_test_redis_url(os.environ.get("TEST_REDIS_URL"))
    if url is None:
        pytest.fail("An explicit disposable TEST_REDIS_URL is required")
    namespace, revoked = uuid4().hex, set[str]()
    monkeypatch.setattr(settings, "world_enabled", True)
    monkeypatch.setattr(settings, "world_namespace", namespace)
    monkeypatch.setattr(settings, "cors_origins", [ORIGIN])

    async def policy(cookie: str, account: str, participants: set[str]) -> WorldPolicy:
        if cookie != f"proof-{account}" or account in revoked:
            raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
        return WorldPolicy(
            "en",
            frozenset(),
            frozenset((participants | {account}) - revoked),
            public_identity=PublicWorldIdentity(
                name="Native visitor", appearance=AvatarAppearance()
            ),
        )

    async def admission[R](
        account: str, store: WorldStore, transition: Callable[[WorldState, float], R]
    ) -> tuple[WorldState, R]:
        # Inert accounts in this transport harness; real SQL locking is tested
        # in test_lifecycle and the native browser suite, without this double.
        if account in revoked:
            raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
        return await store.update(transition)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        redis = Redis.from_url(url, decode_responses=True)

        async def cache() -> Redis:
            return redis

        monkeypatch.setattr(world_router, "get_redis_cache", cache)
        monkeypatch.setattr(world_router, "read_policy", policy)
        monkeypatch.setattr(world_service, "read_policy", policy)
        monkeypatch.setattr(world_service, "commit_admission", admission)
        try:
            await redis.ping()
            yield
        finally:
            keys = [key async for key in redis.scan_iter(match=f"world:*:{namespace}*")]
            if keys:
                await redis.delete(*keys)
            await redis.aclose()

    app = FastAPI(lifespan=lifespan)
    app.include_router(world_router.router)

    @app.post("/proof-ticket/{account}")
    async def issue(account: str) -> dict[str, str]:
        redis = await world_router.get_redis_cache()
        tickets = WorldTickets(redis, namespace=namespace, ttl=30)
        return {
            "ticket": await tickets.create(
                WorldTicket(
                    account_id=account,
                    binding=cookie_binding(f"proof-{account}"),
                    alias="Proof visitor",
                )
            )
        }

    with TestClient(app) as client:
        yield Harness(client, revoked)


def test_five_accounts_share_one_world_and_sixth_waits_without_a_participant_stream(
    world_client: Harness,
) -> None:
    with ExitStack() as stack:
        accounts = [str(uuid4()) for _ in range(6)]
        sessions = [world_client.connect(stack, account) for account in accounts]
        assert all(view.status == "active" for _, _, view in sessions[:5])
        assert len({view.epoch for _, _, view in sessions}) == 1
        waiting = sessions[5][2]
        assert waiting.status == "waiting" and waiting.position == 1
        assert waiting.actors == [] and waiting.you is None
        for account in accounts:
            assert account not in str(waiting)
        first, _, view = sessions[0]
        first.send_json({"type": "leave", "version": 1, "epoch": view.epoch})
        sixth = sessions[5][0]
        offer = WorldView.model_validate(sixth.receive_json())
        for _ in range(30):
            if offer.offer_until is not None:
                break
            offer = WorldView.model_validate(sixth.receive_json())
        assert offer.offer_until is not None
        sixth.send_json({"type": "accept", "version": 1, "epoch": offer.epoch})
        for _ in range(30):
            view = WorldView.model_validate(sixth.receive_json())
            if view.status == "active":
                break
        assert view.status == "active" and view.controlling


def test_reconnect_rotates_control_without_moving_or_duplicating_the_avatar(
    world_client: Harness,
) -> None:
    account = str(uuid4())
    with ExitStack() as first_stack:
        _, ready, before = world_client.connect(first_stack, account)
    with ExitStack() as stack:
        socket, resumed, after = world_client.connect(stack, account, ready.resume)
        assert resumed.resume != ready.resume
        assert after.you is not None and before.you is not None
        assert after.you.id == before.you.id
        assert after.you.position == before.you.position
        assert after.controlling
        socket.send_json(
            {"type": "move", "version": 1, "epoch": after.epoch, "seq": 1, "dx": 1, "dy": 0}
        )
        for _ in range(30):
            moved = WorldView.model_validate(socket.receive_json())
            if moved.ack == 1:
                break
        assert moved.ack == 1


def test_unauthenticated_or_wrong_purpose_ticket_never_receives_a_ready_frame(
    world_client: Harness,
) -> None:
    with world_client.client.websocket_connect("/world/ws", headers={"origin": ORIGIN}) as socket:
        socket.send_json({"type": "authenticate", "version": 1, "scene": SCENE, "ticket": "v" * 43})
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 4401


def test_forged_coordinate_frame_is_rejected_without_a_business_dispatch(
    world_client: Harness,
) -> None:
    with ExitStack() as stack:
        socket, _, view = world_client.connect(stack, str(uuid4()))
        socket.send_json(
            {
                "type": "move",
                "version": 1,
                "epoch": view.epoch,
                "seq": 1,
                "dx": 1,
                "dy": 0,
                "position": {"x": 60, "y": 25},
            }
        )
        with pytest.raises(WebSocketDisconnect) as error:
            while True:
                socket.receive_json()
        assert error.value.code == 1008


def test_stale_scene_cannot_admit_an_invisible_occupant(world_client: Harness) -> None:
    account = str(uuid4())
    token = world_client.client.post(f"/proof-ticket/{account}").json()["ticket"]
    with world_client.client.websocket_connect(
        "/world/ws", headers={"origin": ORIGIN, "cookie": f"lia_session=proof-{account}"}
    ) as socket:
        socket.send_json(
            {"type": "authenticate", "version": 1, "scene": "lia-campus:obsolete", "ticket": token}
        )
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 1008
    with ExitStack() as stack:
        _, ready, view = world_client.connect(stack, str(uuid4()))
        assert ready.scene == SCENE
        assert view.actors == []


def test_idle_socket_retains_only_coarse_presence_and_rejoins_through_admission(
    world_client: Harness,
) -> None:
    from src.domains.world.configuration import configured_store
    from src.domains.world.presence import peer_presence

    account = str(uuid4())
    portal = world_client.client.portal
    assert portal is not None

    async def expire_activity() -> None:
        store = configured_store(await world_router.get_redis_cache())

        def expire(state: WorldState, now: float) -> None:
            state.actors[account].activity_at = now - 601
            world_service.configured_authority().prune(state, now)

        await store.update(expire)

    async def status() -> str:
        store = configured_store(await world_router.get_redis_cache())
        state, now = await store.read()
        return peer_presence(state, account, now)

    with ExitStack() as stack:
        socket, _, initial = world_client.connect(stack, account)
        portal.call(expire_activity)
        for _ in range(30):
            idle = WorldView.model_validate(socket.receive_json())
            if idle.status == "absent":
                break
        assert idle.status == "absent" and idle.you is None and idle.actors == []
        assert portal.call(status) == "away"
        socket.send_json(
            {
                "type": "heartbeat",
                "version": 1,
                "epoch": initial.epoch,
                "visible": True,
                "active": False,
            }
        )
        assert WorldView.model_validate(socket.receive_json()).status == "absent"
        socket.send_json({"type": "accept", "version": 1, "epoch": initial.epoch})
        for _ in range(30):
            rejoined = WorldView.model_validate(socket.receive_json())
            if rejoined.status == "active":
                break
        assert rejoined.status == "active"
        assert portal.call(status) == "online"

    async def disconnected() -> None:
        async with asyncio.timeout(2):
            while await status() != "offline":
                await asyncio.sleep(0.01)

    portal.call(disconnected)
