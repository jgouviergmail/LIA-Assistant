"""Real local provider WebSocket: disconnect, stop, cancellation and stalled presence."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiohttp import WSMsgType, web
from starlette.types import Message
from starlette.websockets import WebSocket

from src.domains.avatars.control_store import AvatarControlStore, RelayEnvelope
from src.domains.avatars.leases import AvatarLease, AvatarLeaseStore, LeasePhase
from src.domains.avatars.relay import AvatarRelay

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("reason", ["disconnect", "stop", "presence", "cancel"])
async def test_server_sends_skip_done_and_closes_owned_provider_socket(
    reason, unused_tcp_port, monkeypatch
):
    received: list[str] = []
    offered = asyncio.Event()
    closed = asyncio.Event()

    async def provider(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type is WSMsgType.TEXT:
                received.append(msg.data)
                if msg.data.startswith("{"):
                    offered.set()
                    await ws.send_str('{"type":"answer","sdp":"fixture"}')
                if msg.data == "DONE":
                    await ws.close()
        closed.set()
        return ws

    app = web.Application()
    app.router.add_get("/compose/webrtc/p2p", provider)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()
    monkeypatch.setattr(
        "src.domains.avatars.relay.SIMLI_RELAY_ORIGIN",
        f"http://127.0.0.1:{unused_tcp_port}/compose/webrtc/p2p",
    )
    inputs: asyncio.Queue[Message] = asyncio.Queue()
    outputs: list[Message] = []

    async def receive() -> Message:
        return await inputs.get()

    async def send(message: Message) -> None:
        outputs.append(message)

    browser = WebSocket({"type": "websocket", "path": "/avatars/ws", "headers": []}, receive, send)
    await inputs.put({"type": "websocket.connect"})
    await browser.accept()
    lease = AvatarLease(
        user_id=uuid4(),
        owner_id=uuid4(),
        digest="a" * 64,
        credential_version="v",
        phase=LeasePhase.READY,
        controlled=True,
    )
    controls = AsyncMock(spec=AvatarControlStore)
    controls.stopped.return_value = False
    controls.present.return_value = True
    leases = AsyncMock(spec=AvatarLeaseStore)
    leases.get.return_value = lease
    relay = AvatarRelay(
        browser,
        RelayEnvelope(lease=lease, token="test-only", api_key="test-only"),
        controls,
        leases,
    )
    task = asyncio.create_task(relay.run())
    try:
        await inputs.put({"type": "websocket.receive", "text": '{"type":"offer","sdp":"fixture"}'})
        await asyncio.wait_for(offered.wait(), 3)
        if reason == "disconnect":
            await inputs.put({"type": "websocket.disconnect", "code": 1000})
        elif reason == "stop":
            controls.stopped.return_value = True
        elif reason == "presence":
            controls.present.return_value = False
        else:
            task.cancel()
        results = await asyncio.gather(task, return_exceptions=True)
        assert not isinstance(results[0], Exception)
        await asyncio.wait_for(closed.wait(), 3)
        assert received[-2:] == ["SKIP", "DONE"]
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runner.cleanup()
