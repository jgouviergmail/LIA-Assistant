"""Single-use server relay tickets. Provider tokens never reach the browser."""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from src.core.config import settings
from src.core.security import decrypt_data, encrypt_data
from src.domains.avatars.leases import AvatarLease

_TAKE = """
local id = redis.call('get', KEYS[1])
if not id then return nil end
redis.call('del', KEYS[1])
local key = 'avatar:control:' .. id
if redis.call('hget', key, 'phase') ~= 'pending' then return nil end
redis.call('hset', key, 'phase', 'open')
return redis.call('hget', key, 'envelope')
"""
_STOP = """
local phase = redis.call('hget', KEYS[1], 'phase')
if not phase then return 0 end
redis.call('hset', KEYS[1], 'stop', '1')
if phase == 'pending' then
    redis.call('hset', KEYS[1], 'phase', 'closed')
    redis.call('del', KEYS[2])
    return 1
end
return phase == 'closed' and 1 or 0
"""
_PHASE = """
local phase = redis.call('hget', KEYS[1], 'phase')
if phase == 'pending' then
    local ticket = redis.call('hget', KEYS[1], 'ticket')
    if ticket and redis.call('exists', 'avatar:ticket:' .. ticket) == 0 then
        redis.call('hset', KEYS[1], 'phase', 'closed', 'stop', '1')
        return 'closed'
    end
end
return phase
"""


class RelayEnvelope(BaseModel):
    lease: AvatarLease
    token: str = Field(repr=False, max_length=8192)
    api_key: str = Field(repr=False)


class AvatarControlStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def key(lease_id: UUID) -> str:
        return f"avatar:control:{lease_id}"

    async def issue(self, lease: AvatarLease, token: str, api_key: str, ttl: int) -> str:
        ticket = str(uuid4())
        envelope = encrypt_data(
            RelayEnvelope(lease=lease, token=token, api_key=api_key).model_dump_json()
        )
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                self.key(lease.lease_id),
                mapping={"phase": "pending", "stop": "0", "ticket": ticket, "envelope": envelope},
            )
            pipe.expire(self.key(lease.lease_id), ttl)
            pipe.set(f"avatar:ticket:{ticket}", str(lease.lease_id), ex=30)
            pipe.set(
                f"{self.key(lease.lease_id)}:presence",
                "1",
                ex=settings.avatar_presence_timeout_seconds,
            )
            await pipe.execute()
        return ticket

    async def consume(self, ticket: UUID) -> RelayEnvelope | None:
        encrypted = await self.redis.eval(_TAKE, 1, f"avatar:ticket:{ticket}")
        if not encrypted:
            return None
        text = encrypted.decode() if isinstance(encrypted, bytes) else encrypted
        return RelayEnvelope.model_validate_json(decrypt_data(text))

    async def stop(self, lease: AvatarLease) -> bool:
        ticket = await self.redis.hget(self.key(lease.lease_id), "ticket")
        if isinstance(ticket, bytes):
            ticket = ticket.decode()
        return bool(
            await self.redis.eval(_STOP, 2, self.key(lease.lease_id), f"avatar:ticket:{ticket}")
        )

    async def stopped(self, lease_id: UUID) -> bool:
        return await self.redis.hget(self.key(lease_id), "stop") in (b"1", "1", None)

    async def closed(self, lease_id: UUID) -> None:
        # A late shutdown must not recreate an expired hash without a TTL.
        await self.redis.eval(
            "if redis.call('exists', KEYS[1]) == 1 then "
            "return redis.call('hset', KEYS[1], 'phase', 'closed') end return 0",
            1,
            self.key(lease_id),
        )

    async def phase(self, lease_id: UUID) -> str | None:
        value = await self.redis.eval(_PHASE, 1, self.key(lease_id))
        return value.decode() if isinstance(value, bytes) else value

    async def touch(self, lease_id: UUID) -> bool:
        return bool(
            await self.redis.set(
                f"{self.key(lease_id)}:presence",
                "1",
                ex=settings.avatar_presence_timeout_seconds,
                xx=True,
            )
        )

    async def present(self, lease_id: UUID) -> bool:
        return bool(await self.redis.exists(f"{self.key(lease_id)}:presence"))

    async def completed(
        self, user_id: UUID, owner_id: UUID, lease_id: UUID
    ) -> RelayEnvelope | None:
        if await self.phase(lease_id) != "closed":
            return None
        raw = await self.redis.hget(self.key(lease_id), "envelope")
        if not raw:
            return None
        encrypted = raw.decode() if isinstance(raw, bytes) else raw
        envelope = RelayEnvelope.model_validate_json(decrypt_data(encrypted))
        lease = envelope.lease
        return (
            envelope
            if (lease.user_id, lease.owner_id, lease.lease_id) == (user_id, owner_id, lease_id)
            else None
        )
