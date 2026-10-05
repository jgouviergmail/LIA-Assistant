"""Own Simli's control socket on the server; RTC media stays peer-to-peer."""

import asyncio
import json
from contextlib import suppress
from time import monotonic
from uuid import UUID

import aiohttp
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError

from src.core.config import settings
from src.domains.avatars.accounts import AvatarAccountStore
from src.domains.avatars.client import SimliClient, SimliError
from src.domains.avatars.control_store import AvatarControlStore, RelayEnvelope
from src.domains.avatars.leases import AvatarLeaseStore
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/avatars", tags=["Avatars"])
SIMLI_RELAY_ORIGIN = "wss://api.simli.ai/compose/webrtc/p2p"


class AvatarRelay:
    def __init__(
        self,
        browser: WebSocket,
        envelope: RelayEnvelope,
        controls: AvatarControlStore,
        leases: AvatarLeaseStore,
    ) -> None:
        self.browser = browser
        self.envelope = envelope
        self.controls = controls
        self.leases = leases
        self.last_seen = monotonic()
        self.started = self.last_seen
        self.offered = False

    async def run(self) -> None:
        async with aiohttp.ClientSession() as client:
            provider = await asyncio.wait_for(
                client.ws_connect(
                    SIMLI_RELAY_ORIGIN,
                    params={"session_token": self.envelope.token, "enableSFU": "true"},
                    heartbeat=20,
                    max_msg_size=131072,
                ),
                timeout=settings.avatar_connect_timeout_seconds,
            )
            async with provider:
                try:
                    await self._duplex(provider)
                finally:
                    await self._terminate(provider)

    async def _duplex(self, provider: aiohttp.ClientWebSocketResponse) -> None:
        tasks = [
            asyncio.create_task(self._up(provider)),
            asyncio.create_task(self._down(provider)),
            asyncio.create_task(self._guard()),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _up(self, provider: aiohttp.ClientWebSocketResponse) -> None:
        while True:
            message = await self.browser.receive()
            if message["type"] == "websocket.disconnect":
                return
            self.last_seen = monotonic()
            pcm = message.get("bytes")
            if pcm is not None:
                if not self.offered or not 0 < len(pcm) <= 6000 or len(pcm) % 2:
                    raise ValueError("avatar_bad_pcm")
                await provider.send_bytes(pcm)
            else:
                text = message.get("text")
                if not isinstance(text, str):
                    raise ValueError("avatar_bad_signal")
                await self._text(provider, text)

    async def _text(self, provider: aiohttp.ClientWebSocketResponse, text: str) -> None:
        if text == "PING":
            return
        if text in ("SKIP", "DONE") and self.offered:
            await provider.send_str(text)
            if text == "DONE":
                raise WebSocketDisconnect()
            return
        if self.offered or len(text) > 131072:
            raise ValueError("avatar_bad_signal")
        offer = json.loads(text)
        if (
            not isinstance(offer, dict)
            or set(offer) != {"type", "sdp"}
            or offer["type"] != "offer"
            or not isinstance(offer["sdp"], str)
        ):
            raise ValueError("avatar_bad_offer")
        # A stop winning the ticket/offer race never starts the remote session.
        if await self.controls.stopped(self.envelope.lease.lease_id):
            raise WebSocketDisconnect()
        await provider.send_str(text)
        self.offered = True

    async def _down(self, provider: aiohttp.ClientWebSocketResponse) -> None:
        async for message in provider:
            if message.type is aiohttp.WSMsgType.TEXT:
                if message.data in ("STOP", "RATE", "ERROR", "CLOSING"):
                    logger.info(
                        "avatar_provider_terminal_control",
                        lease_id=str(self.envelope.lease.lease_id),
                        code=message.data,
                    )
                await self.browser.send_text(message.data)

    async def _guard(self) -> None:
        while True:
            await asyncio.sleep(1)
            lease = self.envelope.lease
            current = await self.leases.get(lease.user_id, lease.owner_id)
            if current != lease or await self.controls.stopped(lease.lease_id):
                return
            if not await self.controls.present(lease.lease_id):
                logger.info("avatar_relay_authorization_expired", lease_id=str(lease.lease_id))
                return
            age = monotonic() - self.started
            if (
                age >= settings.avatar_session_length_seconds
                or monotonic() - self.last_seen >= settings.avatar_presence_timeout_seconds
            ):
                logger.info("avatar_relay_presence_expired", lease_id=str(lease.lease_id))
                return
            if not self.offered and age >= settings.avatar_connect_timeout_seconds:
                return

    async def _terminate(self, provider: aiohttp.ClientWebSocketResponse) -> None:
        # Clear queued speech before DONE, then wait for the provider to close.
        # Billing confirmation remains a separate GET; Redis deletion alone is never proof.
        with suppress(aiohttp.ClientError, ConnectionError, TimeoutError):
            if not provider.closed:
                await provider.send_str("SKIP")
                await provider.send_str("DONE")
                async with asyncio.timeout(3):
                    async for _ in provider:
                        if provider.closed:
                            break
            await provider.close()


@router.websocket("/ws")
async def avatar_socket(websocket: WebSocket, ticket: UUID) -> None:
    redis = await get_redis_cache()
    controls = AvatarControlStore(redis)
    envelope = await controls.consume(ticket)
    if envelope is None:
        await websocket.close(code=4001)
        return
    leases = AvatarLeaseStore(redis)
    try:
        account = await AvatarAccountStore().read(envelope.lease.user_id, credentials=True)
        if (
            not account.active
            or not account.available
            or not account.enabled
            or account.credential_digest != envelope.lease.digest
            or account.face_id != envelope.lease.face_id
        ):
            raise ValueError("avatar_unavailable")
        if await leases.get(envelope.lease.user_id, envelope.lease.owner_id) != envelope.lease:
            raise ValueError("avatar_lease_expired")
        await websocket.accept()
        async with asyncio.timeout(settings.avatar_session_length_seconds + 10):
            await AvatarRelay(websocket, envelope, controls, leases).run()
    except aiohttp.ClientError, WebSocketDisconnect, ValueError, TimeoutError, RedisError:
        logger.info("avatar_relay_closed", lease_id=str(envelope.lease.lease_id))
    finally:
        await controls.closed(envelope.lease.lease_id)
        # Keep the lease when the provider is unreachable or still active.
        try:
            if await SimliClient(envelope.api_key).active_count() == 0:
                await leases.release(envelope.lease)
                logger.info(
                    "avatar_provider_closure_confirmed", lease_id=str(envelope.lease.lease_id)
                )
        except SimliError, RedisError:
            logger.warning(
                "avatar_provider_closure_unconfirmed", lease_id=str(envelope.lease.lease_id)
            )
        # A disconnected browser requires no extra close frame.
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close()
