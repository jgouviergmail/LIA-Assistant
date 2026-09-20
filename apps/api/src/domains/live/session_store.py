"""Where a live session lives between two requests: Redis, never process memory.

Four uvicorn workers serve the same account (ADR-271): the mint, the
reconnections, the turns and the end may each land on a different one, so the
record is in Redis. The claim is the codebase's one claim primitive
(``infrastructure/locks/redis_claim``: ``SET NX`` to take, compare-and-delete
on the OWNER token to release — never an unconditional ``DELETE``). The record
travels under a sibling key with the same TTL, and the claim is the authority:
a record whose claim expired is no session.

The instance cap is a sorted set scored by expiry, pruned on read: a soft
bound sized for the delegated-turn load, never a security boundary.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from redis.asyncio import Redis

from src.core.constants import (
    LIVE_SESSION_MAX_MINUTES_DEFAULT,
    LIVE_SESSION_RECORD_GRACE_SECONDS,
    REDIS_KEY_LIVE_ACTIVE,
    REDIS_KEY_LIVE_SESSION_PREFIX,
    REDIS_KEY_LIVE_TOOL_BUDGET_PREFIX,
)
from src.infrastructure.locks.redis_claim import refresh_claim, release_claim, try_claim

_RECORD_SUFFIX: Final = ":record"
#: The turns of a DIRECT session, kept until its end (ADR-301): a Redis LIST
#: beside the record — appended, never read-modify-written, so an extension
#: rewriting the record cannot lose a turn nor a turn an extension.
_TURNS_SUFFIX: Final = ":turns"


@dataclass(frozen=True, slots=True)
class LiveSessionRecord:
    """The one session an account holds.

    Attributes:
        session_id: The session, a hex uuid.
        user_id: The account.
        provider: The provider id (``gemini``).
        model: The model the session runs on.
        run_id: What every row and every euro of the session is filed under.
        started_at: The mint of the first credential.
        expires_at: The session's cap — moved by every explicit extension;
            the credential of a reconnection is minted to it.
        token: The owner token of the claim — the only thing that releases it.
        setup_inputs: What the provider setup was rendered from, kept so a
            reconnection replays the SAME setup with a fresh credential
            (measured 2026-09-18: one credential opens one connection).
        extensions: How many times the person prolonged the session — a
            rolling cap's renewals are not counted (nobody decided them).
        unlimited_cap: The model's cap is « no limit » (owner decision
            2026-09-19): the cap rolls by extension slices the client renews
            in silence, and no renewal is the person's extension.
        nonce: For an ``offer`` connection, the single-use credential the
            browser hands back with its SDP; None once consumed or for a
            ``token`` connection.
        nonce_until: The instant the nonce stops opening a connection.
    """

    session_id: str
    user_id: uuid.UUID
    provider: str
    model: str
    run_id: str
    started_at: datetime
    expires_at: datetime
    token: str
    setup_inputs: dict[str, Any] = field(default_factory=dict)
    extensions: int = 0
    unlimited_cap: bool = False
    #: ``delegated`` (the voice hands every request to the chat) or ``direct``
    #: (the voice holds LIA's read-only tools itself, ADR-300 wave 4).
    mode: str = "delegated"
    nonce: str | None = None
    nonce_until: datetime | None = None

    def to_json(self) -> str:
        """The record as stored."""
        payload: dict[str, Any] = asdict(self)
        payload["user_id"] = str(self.user_id)
        payload["started_at"] = self.started_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        payload["nonce_until"] = self.nonce_until.isoformat() if self.nonce_until else None
        return json.dumps(payload)

    def remaining_life_seconds(self, now: datetime) -> int:
        """How long the record still lives: to its cap, plus the closing grace (at least 1 s)."""
        return max(
            1, int((self.expires_at - now).total_seconds()) + LIVE_SESSION_RECORD_GRACE_SECONDS
        )

    @classmethod
    def from_json(cls, raw: str) -> LiveSessionRecord:
        """The record as read."""
        payload = json.loads(raw)
        started_at = datetime.fromisoformat(str(payload["started_at"]))
        # A record minted by the previous release carries no expiry: it was
        # minted under the default cap, and lives at most that cap plus grace.
        expires_at = (
            datetime.fromisoformat(str(payload["expires_at"]))
            if payload.get("expires_at")
            else started_at + timedelta(minutes=LIVE_SESSION_MAX_MINUTES_DEFAULT)
        )
        return cls(
            session_id=str(payload["session_id"]),
            user_id=uuid.UUID(str(payload["user_id"])),
            provider=str(payload["provider"]),
            model=str(payload["model"]),
            run_id=str(payload["run_id"]),
            started_at=started_at,
            expires_at=expires_at,
            token=str(payload["token"]),
            setup_inputs=dict(payload.get("setup_inputs") or {}),
            extensions=int(payload.get("extensions") or 0),
            unlimited_cap=bool(payload.get("unlimited_cap", False)),
            # A record minted by the previous release names no mode: delegated.
            mode=str(payload.get("mode") or "delegated"),
            nonce=str(payload["nonce"]) if payload.get("nonce") else None,
            nonce_until=(
                datetime.fromisoformat(str(payload["nonce_until"]))
                if payload.get("nonce_until")
                else None
            ),
        )


class LiveSessionStore:
    """Claim, read, release — and the instance-wide count."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _claim_key(user_id: uuid.UUID) -> str:
        return f"{REDIS_KEY_LIVE_SESSION_PREFIX}{user_id}"

    @classmethod
    def _record_key(cls, user_id: uuid.UUID) -> str:
        return f"{cls._claim_key(user_id)}{_RECORD_SUFFIX}"

    @classmethod
    def _turns_key(cls, user_id: uuid.UUID) -> str:
        return f"{cls._claim_key(user_id)}{_TURNS_SUFFIX}"

    async def append_turns(
        self, user_id: uuid.UUID, rows: list[tuple[str, str]], *, ttl_seconds: int, max_rows: int
    ) -> int:
        """Keep the exchange of a DIRECT session for its closing (ADR-301).

        Args:
            user_id: The account.
            rows: ``(role, text)`` in order.
            ttl_seconds: The record's remaining life — the list dies with it.
            max_rows: The bound; rows past it are dropped and counted.

        Returns:
            How many rows were kept.
        """
        if not rows:
            return 0
        key = self._turns_key(user_id)
        held = int(await self._redis.llen(key))
        room = max(0, max_rows - held)
        kept = rows[:room]
        if kept:
            await self._redis.rpush(key, *(json.dumps([role, text]) for role, text in kept))
            await self._redis.expire(key, max(1, ttl_seconds))
        return len(kept)

    async def turns(self, user_id: uuid.UUID) -> list[tuple[str, str]]:
        """The turns a DIRECT session kept, in order."""
        raw = await self._redis.lrange(self._turns_key(user_id), 0, -1)
        rows: list[tuple[str, str]] = []
        for item in raw:
            pair = json.loads(item.decode() if isinstance(item, bytes) else item)
            rows.append((str(pair[0]), str(pair[1])))
        return rows

    async def claim(self, record: LiveSessionRecord, *, ttl_seconds: int) -> bool:
        """Hold the account's one session slot; False when it is already held.

        Args:
            record: The session, whose ``token`` owns the claim.
            ttl_seconds: The session's longest life — the claim and the record
                die together.

        Returns:
            True when the slot was taken.

        Raises:
            Exception: Whatever the cache raised — a session must not open on
                an unknown claim state.
        """
        taken = await try_claim(
            self._redis, self._claim_key(record.user_id), record.token, ttl_seconds=ttl_seconds
        )
        if not taken:
            return False
        await self._redis.set(self._record_key(record.user_id), record.to_json(), ex=ttl_seconds)
        # A session that died without its end (a killed tab) may have left
        # its turns behind until their TTL: this session starts with none.
        await self._redis.delete(self._turns_key(record.user_id))
        return True

    async def extend(self, record: LiveSessionRecord, *, ttl_seconds: int) -> bool:
        """Rewrite the record under its claim, owner-checked, with a new life.

        Args:
            record: The session as extended (a NEW expiry, one more extension);
                its ``token`` must still hold the claim.
            ttl_seconds: The new life of the claim and the record, from now.

        Returns:
            True when the owner still held the claim and the record moved;
            False when a successor holds it (the caller's session is over).

        Raises:
            Exception: Whatever the cache raised — an extension on an unknown
                claim state is refused, never assumed.
        """
        refreshed = await refresh_claim(
            self._redis, self._claim_key(record.user_id), record.token, ttl_seconds=ttl_seconds
        )
        if not refreshed:
            return False
        await self._redis.set(self._record_key(record.user_id), record.to_json(), ex=ttl_seconds)
        # The kept turns of a direct session were given the record's life at
        # their last append: they follow the record's new cap (a no-op on a
        # session that keeps none), or a session extended past its first cap
        # would end with its words already expired.
        await self._redis.expire(self._turns_key(record.user_id), ttl_seconds)
        return True

    async def rewrite(self, record: LiveSessionRecord, *, now: datetime) -> bool:
        """Rewrite the record under its claim with the life it still has (a nonce written or consumed).

        Args:
            record: The session as it must now read; its ``token`` must still hold the claim.
            now: The instant, for the remaining life.

        Returns:
            True when the owner still held the claim; False when a successor holds it.
        """
        return await self.extend(record, ttl_seconds=record.remaining_life_seconds(now))

    async def get(self, user_id: uuid.UUID) -> LiveSessionRecord | None:
        """The account's session, or None when no claim is held."""
        claim = await self._redis.get(self._claim_key(user_id))
        if claim is None:
            return None
        raw = await self._redis.get(self._record_key(user_id))
        if raw is None:
            return None
        return LiveSessionRecord.from_json(raw.decode() if isinstance(raw, bytes) else raw)

    async def release(self, user_id: uuid.UUID, token: str) -> bool:
        """Free the slot if — and only if — the caller holds it.

        Args:
            user_id: The account.
            token: The owner token of the record.

        Returns:
            True when the claim was this caller's and is now released (the
            record goes with it); False when a successor holds it.
        """
        released = await release_claim(self._redis, self._claim_key(user_id), token)
        if released:
            await self._redis.delete(self._record_key(user_id), self._turns_key(user_id))
        return released

    async def consume_tool_budget(self, session_id: str, *, limit: int, ttl_seconds: int) -> bool:
        """Count one lookup of a DIRECT session against its budget (ADR-300 wave 4).

        The counter lives as long as the session's record may (its own TTL),
        under the session family, so a session that ended takes its counter
        with it.

        Args:
            session_id: The session.
            limit: Lookups allowed per session.
            ttl_seconds: How long the counter lives.

        Returns:
            True when this lookup is within the budget.
        """
        key = f"{REDIS_KEY_LIVE_TOOL_BUDGET_PREFIX}{session_id}"
        count = int(await self._redis.incr(key))
        if count == 1:
            await self._redis.expire(key, max(1, ttl_seconds))
        return count <= limit

    async def register_active(self, session_id: str, expires_at: datetime) -> None:
        """Count the session among the open ones until ``expires_at``."""
        await self._redis.zadd(REDIS_KEY_LIVE_ACTIVE, {session_id: expires_at.timestamp()})

    async def unregister_active(self, session_id: str) -> None:
        """Stop counting the session."""
        await self._redis.zrem(REDIS_KEY_LIVE_ACTIVE, session_id)

    async def count_active(self, now: datetime | None = None) -> int:
        """Sessions whose expiry is still ahead — the pruned count."""
        stamp = (now or datetime.now(UTC)).timestamp()
        await self._redis.zremrangebyscore(REDIS_KEY_LIVE_ACTIVE, "-inf", stamp)
        return int(await self._redis.zcard(REDIS_KEY_LIVE_ACTIVE))


__all__ = ["LiveSessionRecord", "LiveSessionStore"]
