"""Single-use, short-lived opaque tokens backed by Redis.

Three flows had independently written the same mechanism before this module
existed — the two-step MFA bridge (``mfa:pending:``), the OAuth CSRF state
(``oauth:state:``) and, joining them, the native-shell session handoff. Each is
the same object: an unguessable token, a JSON payload held **server-side**, a
short TTL, and a consumption that must be atomic.

Atomicity is the load-bearing part. ``GET`` followed by ``DELETE`` leaves a
window in which two concurrent callers both read the payload and both succeed —
on an authentication path that is a replay. ``GETDEL`` closes it, and this
module exists so no caller has to remember that.

Nothing here decides *policy*: the TTL, the prefix and the payload shape belong
to the flow that owns them. This only guarantees the mechanics.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import structlog

from src.infrastructure.cache.redis import get_redis_session

logger = structlog.get_logger(__name__)

T = TypeVar("T")

#: Bytes of entropy per token. 32 bytes → 43 url-safe characters, the same
#: order of magnitude as the OAuth state tokens this joins.
_TOKEN_BYTES = 32


@dataclass(frozen=True, slots=True)
class SingleUseTokenStore(Generic[T]):
    """Issue and consume opaque tokens carrying a typed payload.

    Attributes:
        prefix: Redis key prefix owned by the calling flow, e.g. ``mfa:pending:``.
        decode: Turns the stored mapping into the flow's payload type. Raising
            ``KeyError``/``TypeError``/``ValueError`` marks the payload
            unusable, which :meth:`consume` reports as ``None``.
    """

    prefix: str
    decode: Callable[[dict[str, Any]], T]

    async def issue(self, payload: dict[str, Any], ttl_seconds: int) -> str:
        """Store a payload under a fresh token.

        Args:
            payload: JSON-serialisable mapping to hold server-side. It never
                travels to the client — only the token does.
            ttl_seconds: Lifetime. Must be positive: a zero or negative TTL is
                a caller bug that Redis would silently turn into "no expiry",
                leaving a credential alive forever.

        Returns:
            The opaque token to hand to the client.

        Raises:
            ValueError: When ``ttl_seconds`` is not positive.
        """
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")

        token = secrets.token_urlsafe(_TOKEN_BYTES)
        redis = await get_redis_session()
        await redis.set(f"{self.prefix}{token}", json.dumps(payload), ex=ttl_seconds)
        return token

    async def consume(self, token: str) -> T | None:
        """Atomically read and destroy a token's payload.

        Args:
            token: Opaque token presented by the client.

        Returns:
            The decoded payload, or ``None`` when the token is empty, unknown,
            expired, already used, or carries something this store cannot
            decode. Callers on authentication paths must treat every ``None``
            identically — distinguishing them would leak which tokens exist.
        """
        if not token:
            # Guard the bare prefix: an empty token would build a key that a
            # scan-and-set could plant, turning "no token" into a valid one.
            return None

        redis = await get_redis_session()
        raw = await redis.getdel(f"{self.prefix}{token}")
        if not raw:
            return None

        try:
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            return self.decode(payload)
        except json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError:
            # The token was real and is now destroyed; only its content was
            # unusable. Fail closed and say nothing more than "no".
            logger.warning("single_use_token_undecodable", prefix=self.prefix)
            return None
