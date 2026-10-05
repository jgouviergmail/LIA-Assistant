"""A credential-scoped lease protects personal credits across accounts/workers/tabs."""

from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from src.infrastructure.locks.redis_claim import release_claim, try_claim

_MARK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    redis.call('set', KEYS[1], ARGV[2], 'KEEPTTL')
    return 1
end
return 0
"""


class LeasePhase(str, Enum):
    MINTING = "minting"
    READY = "ready"
    UNKNOWN = "unknown"


class AvatarLease(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    user_id: UUID
    owner_id: UUID
    lease_id: UUID = Field(default_factory=uuid4)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    credential_version: str
    face_id: UUID | None = None
    phase: LeasePhase = LeasePhase.MINTING
    controlled: bool = False


class AvatarLeaseStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def claim(self, lease: AvatarLease, ttl_seconds: int) -> bool:
        if not await try_claim(
            self.redis, self._key(lease.digest), lease.model_dump_json(), ttl_seconds=ttl_seconds
        ):
            return False
        # An owner UUID belongs to one connection attempt only. An abandoned
        # index cannot be overwritten by a different credential/lease.
        try:
            indexed = await try_claim(
                self.redis,
                self._index(lease.user_id, lease.owner_id),
                lease.digest,
                ttl_seconds=ttl_seconds,
            )
        except Exception:
            await self.abandon_before_post(lease)
            raise
        if not indexed:
            await release_claim(self.redis, self._key(lease.digest), lease.model_dump_json())
        return indexed

    async def mark(self, lease: AvatarLease, phase: LeasePhase) -> AvatarLease | None:
        if lease.phase is not LeasePhase.MINTING or phase is LeasePhase.MINTING:
            return None
        updated = lease.model_copy(update={"phase": phase})
        changed = await self.redis.eval(
            _MARK_SCRIPT,
            1,
            self._key(lease.digest),
            lease.model_dump_json(),
            updated.model_dump_json(),
        )
        return updated if changed else None

    async def get(self, user_id: UUID, owner_id: UUID) -> AvatarLease | None:
        digest = await self.redis.get(self._index(user_id, owner_id))
        if digest is None:
            return None
        if isinstance(digest, bytes):
            digest = digest.decode("ascii")
        record = await self.redis.get(self._key(digest))
        if record is None:
            return None
        lease = AvatarLease.model_validate_json(record)
        return lease if lease.user_id == user_id and lease.owner_id == owner_id else None

    async def release(self, lease: AvatarLease) -> bool:
        if lease.phase is not LeasePhase.READY:
            return False
        return await self.abandon_before_post(lease)

    async def current(self, user_id: UUID, digest: str) -> AvatarLease | None:
        record = await self.redis.get(self._key(digest))
        if record is None:
            return None
        lease = AvatarLease.model_validate_json(record)
        return lease if lease.user_id == user_id else None

    async def abandon_before_post(self, lease: AvatarLease) -> bool:
        """Only safe before attempting POST, or after verified provider closure."""
        if not await release_claim(self.redis, self._key(lease.digest), lease.model_dump_json()):
            return False
        await release_claim(self.redis, self._index(lease.user_id, lease.owner_id), lease.digest)
        return True

    @staticmethod
    def _key(digest: str) -> str:
        return f"avatar:lease:{digest}"

    @staticmethod
    def _index(user_id: UUID, owner_id: UUID) -> str:
        return f"avatar:owner:{user_id}:{owner_id}"
