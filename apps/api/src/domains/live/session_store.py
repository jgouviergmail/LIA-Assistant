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

A session may sleep (ADR-329): in standby no provider connection exists, the
record lives to the standby bound instead of its cap, the cap is frozen and
shifted by the length of the sleep at the wake, and the session leaves the
instance count — a slot it does not use is a slot someone else may.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from redis.asyncio import Redis

from src.core.constants import (
    LIVE_SESSION_MAX_MINUTES_DEFAULT,
    LIVE_SESSION_RECORD_GRACE_SECONDS,
    REDIS_KEY_LIVE_ACTIVE,
    REDIS_KEY_LIVE_SESSION_PREFIX,
    REDIS_KEY_LIVE_STANDBY,
    REDIS_KEY_LIVE_TOOL_BUDGET_PREFIX,
)
from src.infrastructure.locks.redis_claim import refresh_claim, release_claim, try_claim

_RECORD_SUFFIX: Final = ":record"
#: The turns of a DIRECT session, kept until its end (ADR-301): a Redis LIST
#: beside the record — appended, never read-modify-written, so an extension
#: rewriting the record cannot lose a turn nor a turn an extension.
_TURNS_SUFFIX: Final = ":turns"
#: The fates of the relays a DIRECT session made at each standby (ADR-329): a
#: Redis LIST too, appended by the relay task while the browser may wake or
#: extend the session — a fate written into the record would be a
#: read-modify-write racing those rewrites, and one of the two would be lost.
_RELAYS_SUFFIX: Final = ":relays"


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
        standby_since: When the session went to sleep; None while awake.
        awake_since: When the current awake stretch began (the start, or the
            last wake); None on a record of the previous release (read as the start).
        awake_seconds: The completed awake stretches, in seconds.
        standbys: How many times the session went to sleep.
        provider_conversation_ids: Every conversation a wire named, in order,
            once each — each wake on a vendor-billed provider opens a new one.
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
    standby_since: datetime | None = None
    awake_since: datetime | None = None
    awake_seconds: int = 0
    standbys: int = 0
    provider_conversation_ids: tuple[str, ...] = ()

    def to_json(self) -> str:
        """The record as stored."""
        payload: dict[str, Any] = asdict(self)
        payload["user_id"] = str(self.user_id)
        for name in ("started_at", "expires_at", "nonce_until", "standby_since", "awake_since"):
            value = getattr(self, name)
            payload[name] = value.isoformat() if value else None
        payload["provider_conversation_ids"] = list(self.provider_conversation_ids)
        return json.dumps(payload)

    # -- the standby (ADR-329) ---------------------------------------------------

    @property
    def in_standby(self) -> bool:
        """No provider connection exists; nothing is billed."""
        return self.standby_since is not None

    def awake_duration_seconds(self, now: datetime) -> int:
        """The time the session spent AWAKE — what the cap, the card and the histogram measure."""
        if self.in_standby:
            return self.awake_seconds
        stretch = now - (self.awake_since or self.started_at)
        return self.awake_seconds + max(0, int(stretch.total_seconds()))

    def entering_standby(self, now: datetime, *, conversation_id: str | None) -> LiveSessionRecord:
        """The record as it reads once asleep: the awake stretch banked, the count moved.

        Args:
            now: The instant of the standby.
            conversation_id: The provider's id of the conversation the closed
                connection held, when its wire named one (kept once, in order).
        """
        named = self.provider_conversation_ids
        if conversation_id and conversation_id not in named:
            named = (*named, conversation_id)
        return replace(
            self,
            awake_seconds=self.awake_duration_seconds(now),
            standby_since=now,
            standbys=self.standbys + 1,
            provider_conversation_ids=named,
            nonce=None,
            nonce_until=None,
        )

    def waking(self, now: datetime) -> LiveSessionRecord:
        """The record as it reads once awake again: the cap shifted by the sleep's length."""
        slept = now - (self.standby_since or now)
        return replace(
            self,
            expires_at=self.expires_at + slept,
            awake_since=now,
            standby_since=None,
        )

    def standby_deadline(self, standby_max_seconds: int) -> datetime:
        """When an unbroken sleep ends the session (``expired``)."""
        return (self.standby_since or datetime.now(UTC)) + timedelta(seconds=standby_max_seconds)

    def life_seconds(self, now: datetime, *, standby_max_seconds: int) -> int:
        """How long the record lives from now: the standby bound asleep, the cap awake.

        Both carry the closing grace, and the answer is at least 1 s.
        """
        if not self.in_standby:
            return self.remaining_life_seconds(now)
        left = self.standby_deadline(standby_max_seconds) - now
        return max(1, int(left.total_seconds()) + LIVE_SESSION_RECORD_GRACE_SECONDS)

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

        def _instant(name: str) -> datetime | None:
            raw = payload.get(name)
            return datetime.fromisoformat(str(raw)) if raw else None

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
            nonce_until=_instant("nonce_until"),
            # A record of the previous release has never slept.
            standby_since=_instant("standby_since"),
            awake_since=_instant("awake_since"),
            awake_seconds=int(payload.get("awake_seconds") or 0),
            standbys=int(payload.get("standbys") or 0),
            provider_conversation_ids=tuple(
                str(item) for item in payload.get("provider_conversation_ids") or ()
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

    @classmethod
    def _relays_key(cls, user_id: uuid.UUID) -> str:
        return f"{cls._claim_key(user_id)}{_RELAYS_SUFFIX}"

    @staticmethod
    def _tool_budget_key(session_id: str) -> str:
        return f"{REDIS_KEY_LIVE_TOOL_BUDGET_PREFIX}{session_id}"

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
        return [_turn(item) for item in raw]

    async def drain_turns(self, user_id: uuid.UUID, *, max_rows: int) -> list[tuple[str, str]]:
        """Take the kept turns and remove them, in ONE command (ADR-329).

        ``LMPOP`` takes and removes atomically: a turn kept after the drain
        belongs to the next connection, and two standbys racing never relay
        a row twice. The list never holds more than ``max_rows``.
        """
        popped = await self._redis.lmpop(
            1, self._turns_key(user_id), direction="LEFT", count=max(1, max_rows)
        )
        # ``[key, [items]]``, or None on an empty list.
        items = popped[1] if popped else []
        return [_turn(item) for item in items] if isinstance(items, list) else []

    async def append_relay(
        self, user_id: uuid.UUID, fate: str, recap: str | None, *, ttl_seconds: int
    ) -> None:
        """Keep the fate of a standby's relay for the closing card (ADR-329)."""
        key = self._relays_key(user_id)
        await self._redis.rpush(key, json.dumps([fate, recap]))
        await self._redis.expire(key, max(1, ttl_seconds))

    async def relays(self, user_id: uuid.UUID) -> list[tuple[str, str | None]]:
        """The fates of the standbys' relays, in order."""
        rows: list[tuple[str, str | None]] = []
        for item in await self._redis.lrange(self._relays_key(user_id), 0, -1):
            fate, recap = json.loads(item.decode() if isinstance(item, bytes) else item)
            rows.append((str(fate), str(recap) if recap else None))
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
        # its turns and its relays' fates behind until their TTL: this session
        # starts with none.
        await self._redis.delete(self._turns_key(record.user_id), self._relays_key(record.user_id))
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
        # Every key of the session follows the record's new life (a no-op on a
        # key the session never wrote): the kept turns, the relays' fates and
        # the lookup budget were given the life the record had when they were
        # written, and a session extended — or asleep — past it would lose
        # its words, its fates, or find its budget reset to zero.
        for key in (
            self._turns_key(record.user_id),
            self._relays_key(record.user_id),
            self._tool_budget_key(record.session_id),
        ):
            await self._redis.expire(key, ttl_seconds)
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
            await self._redis.delete(
                self._record_key(user_id), self._turns_key(user_id), self._relays_key(user_id)
            )
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
        key = self._tool_budget_key(session_id)
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
        return await self._count(REDIS_KEY_LIVE_ACTIVE, now)

    async def register_standby(self, session_id: str, deadline: datetime) -> None:
        """Count the session among the sleeping ones until its standby deadline (ADR-329)."""
        await self._redis.zadd(REDIS_KEY_LIVE_STANDBY, {session_id: deadline.timestamp()})

    async def unregister_standby(self, session_id: str) -> None:
        """The session woke, or ended: it no longer sleeps."""
        await self._redis.zrem(REDIS_KEY_LIVE_STANDBY, session_id)

    async def count_standby(self, now: datetime | None = None) -> int:
        """Sessions asleep whose standby deadline is still ahead — the pruned count."""
        return await self._count(REDIS_KEY_LIVE_STANDBY, now)

    async def _count(self, key: str, now: datetime | None) -> int:
        stamp = (now or datetime.now(UTC)).timestamp()
        await self._redis.zremrangebyscore(key, "-inf", stamp)
        return int(await self._redis.zcard(key))


def _turn(item: bytes | str) -> tuple[str, str]:
    pair = json.loads(item.decode() if isinstance(item, bytes) else item)
    return str(pair[0]), str(pair[1])


__all__ = ["LiveSessionRecord", "LiveSessionStore"]
