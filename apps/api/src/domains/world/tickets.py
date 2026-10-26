"""Single-use world-purpose tickets. Cookie binding is checked again at consumption."""

import hashlib
import hmac
import re
import secrets
from typing import Literal
from uuid import UUID

from pydantic import Field
from redis.asyncio import Redis

from src.core.constants import REDIS_KEY_WORLD_TICKET_PREFIX
from src.domains.world.schemas import StrictModel
from src.domains.world.store import WorldUnavailable


class WorldTicket(StrictModel):
    purpose: Literal["world-v1"] = Field(
        default="world-v1",
        description="Single-use World authentication ticket purpose discriminator.",
    )
    account_id: str = Field(
        pattern=r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$",
        description="Native account identifier; internal except on owner-scoped ticket responses.",
    )
    binding: str = Field(
        description="Digest of the native session cookie; raw cookie material is never serialized here."
    )
    alias: str = Field(
        min_length=1,
        max_length=24,
        description="Bounded public account display name; never an email or private profile inference.",
    )


def cookie_binding(cookie: str) -> str:
    """Hash the native cookie so its raw value never enters a ticket or snapshot."""
    return hashlib.sha256(cookie.encode("utf-8")).hexdigest()


class WorldTickets:
    def __init__(self, redis: Redis, *, namespace: str, ttl: int) -> None:
        """Bind single-use World tickets to the configured namespace and short lifetime."""
        self.redis, self.namespace, self.ttl = redis, namespace, ttl

    def key(self, token: str) -> str:
        """Derive a hashed ticket key from the opaque bearer."""
        owner, separator, entropy = token.partition(".")
        if (
            not separator
            or str(UUID(owner)) != owner
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", entropy) is None
        ):
            raise ValueError("invalid_world_ticket")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"{REDIS_KEY_WORLD_TICKET_PREFIX}{self.namespace}:{owner}:{digest}"

    async def create(self, ticket: WorldTicket) -> str:
        """Store one purpose-bound ticket with a fresh random bearer and bounded TTL."""
        token = f"{ticket.account_id}.{secrets.token_urlsafe(32)}"
        stored = await self.redis.set(
            self.key(token), ticket.model_dump_json(), ex=self.ttl, nx=True
        )
        if not stored:
            raise WorldUnavailable("world_ticket_store")
        return token

    async def consume(self, token: str, cookie: str) -> WorldTicket | None:
        """Consume once and require a constant-time match to the actual cookie binding."""
        if not 32 <= len(token) <= 128:
            return None
        try:
            key = self.key(token)
        except ValueError:
            return None
        raw = await self.redis.getdel(key)
        if raw is None:
            return None
        try:
            ticket = WorldTicket.model_validate_json(raw)
        except ValueError:
            return None
        if ticket.account_id != token.partition(".")[0] or not hmac.compare_digest(
            ticket.binding, cookie_binding(cookie)
        ):
            return None
        return ticket
