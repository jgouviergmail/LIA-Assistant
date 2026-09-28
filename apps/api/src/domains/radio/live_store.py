"""Where a radio session lives between two requests: Redis, never process memory.

Four workers serve one account (ADR-271): the start, every report, the stop and
every audio fetch may each land on a different one, and the loop producing the
session runs on ONE of them — whichever holds its lease. Everything the loop and
the routes share is therefore in Redis, under the account (ADR-260 family
``radio``, per-user runtime: a conversation reset never touches it, account
deletion does):

- the RECORD names the account's one session. A new start overwrites it, and
  the previous session's loop reads the change at its next tick and stops — two
  tabs never make two antennas, and a session nobody hears is never billed;
- the INBOX is what the routes write for the loop: the player's last report and
  the listener's stop;
- the STATE is what the loop publishes after its decisions, and the SEGMENTS
  every ready segment ONCE, apart from it: the state changes every few seconds,
  a transcript never, and rewriting forty transcripts at every tick would be the
  store's whole traffic;
- the LOOP key is the lease of the one loop producing the session
  (``locks.redis_claim.held_claim``): a report that finds it gone — the worker
  holding it was restarted — starts the loop again where it stopped.

The ACTIVE set (a GLOBAL sorted set) scores every live session by its last
publish: the instance cap counts it, and the audio sweep never removes what it
names.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import structlog

from src.domains.radio.codec import (
    playhead_from_dict,
    playhead_to_dict,
    segment_from_dict,
    segment_to_dict,
    state_from_dict,
    state_to_dict,
)
from src.domains.radio.media import segment_path
from src.domains.radio.pacing import Playhead
from src.domains.radio.production import ProducedSegment
from src.domains.radio.session import SessionState
from src.infrastructure.locks.redis_claim import try_claim

logger = structlog.get_logger(__name__)

#: The live sessions of the instance, scored by their last publish (GLOBAL).
ACTIVE_KEY: Final = "radio:active"

_PLAYHEAD: Final = "playhead"
_STOP: Final = "stop"
#: What a store reads back that it cannot decode: the shape changed under a
#: release, or the value is not ours. Never content in a log (ADR-317).
_UNREADABLE: Final = (KeyError, TypeError, ValueError)


def _text(raw: str | bytes) -> str:
    return raw.decode() if isinstance(raw, bytes) else raw


@dataclass(frozen=True, slots=True)
class RadioSessionRecord:
    """The one session an account holds.

    Attributes:
        session_id: The session.
        user_id: The account.
        run_id: What every euro of the session is filed under.
        started_at: When the listener started it.
        setup: What the loop needs to produce it — read back unchanged by a
            loop restarted on another worker.
    """

    session_id: UUID
    user_id: UUID
    run_id: str
    started_at: datetime
    setup: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """The record as stored."""
        return json.dumps(
            {
                "session_id": str(self.session_id),
                "user_id": str(self.user_id),
                "run_id": self.run_id,
                "started_at": self.started_at.isoformat(),
                "setup": self.setup,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> RadioSessionRecord:
        """The record as read."""
        payload = json.loads(raw)
        return cls(
            session_id=UUID(str(payload["session_id"])),
            user_id=UUID(str(payload["user_id"])),
            run_id=str(payload["run_id"]),
            started_at=datetime.fromisoformat(str(payload["started_at"])),
            setup=dict(payload["setup"]),
        )


def record_key(user_id: UUID) -> str:
    """The key naming an account's one session."""
    return f"radio:session:{user_id}"


class RadioSessions:
    """The account's one session, and the instance's live ones."""

    def __init__(self, redis: Any, *, ttl_s: int) -> None:
        """Bind the store.

        Args:
            redis: The cache client (``decode_responses`` or not).
            ttl_s: How long a record outlives its last publish.
        """
        self._redis = redis
        self._ttl_s = ttl_s

    async def open(self, record: RadioSessionRecord) -> None:
        """Make ``record`` the account's session — whatever held the place stops.

        Raises:
            Exception: Whatever the cache raised: a session must not start on
                an unknown state.
        """
        await self._redis.set(record_key(record.user_id), record.to_json(), ex=self._ttl_s)

    async def current(self, user_id: UUID) -> RadioSessionRecord | None:
        """The account's session, or None when it has none (or none we can read)."""
        raw = await self._redis.get(record_key(user_id))
        if raw is None:
            return None
        try:
            return RadioSessionRecord.from_json(_text(raw))
        except _UNREADABLE as exc:
            logger.warning("radio_record_unreadable", error_type=type(exc).__name__)
            return None

    async def admit(
        self,
        session_id: UUID,
        *,
        replacing: UUID | None,
        now: datetime,
        horizon_s: float,
        cap: int,
    ) -> bool:
        """Take a place among the instance's live sessions, or refuse at the cap.

        The session JOINS the set before it counts, so two starts racing for
        the last place never both land — both may be refused, and the ceiling
        holds. The account's own previous session does not count: it stops at
        its next tick. A session that stopped publishing (its worker died) is
        pruned first, so it never holds a place for good.

        Args:
            session_id: The session starting.
            replacing: The account's previous session, when it has one.
            now: The start's instant.
            horizon_s: How recently a live session has published, at the least.
            cap: The instance's ceiling.

        Returns:
            Whether the session holds a place (False: it took none).
        """
        member = str(session_id)
        await self._redis.zremrangebyscore(ACTIVE_KEY, "-inf", now.timestamp() - horizon_s)
        await self._redis.zadd(ACTIVE_KEY, {member: now.timestamp()})
        live = {_text(entry) for entry in await self._redis.zrange(ACTIVE_KEY, 0, -1)}
        live.discard(str(replacing))
        if len(live) <= cap:
            return True
        await self.release(session_id)
        return False

    async def release(self, session_id: UUID) -> None:
        """Give back the place of a session that did not start."""
        await self._redis.zrem(ACTIVE_KEY, str(session_id))

    async def active_ids(self, *, now: datetime, horizon_s: float) -> set[UUID]:
        """The sessions that published within ``horizon_s`` (older entries pruned)."""
        await self._redis.zremrangebyscore(ACTIVE_KEY, "-inf", now.timestamp() - horizon_s)
        members = await self._redis.zrange(ACTIVE_KEY, 0, -1)
        return {UUID(_text(member)) for member in members}


class RadioSessionStore:
    """One session's shared state: the loop's inbox and board, the routes' view.

    One instance per loop (it remembers what it already published) or per
    request (it only reads, or writes the inbox).
    """

    def __init__(
        self,
        redis: Any,
        *,
        user_id: UUID,
        session_id: UUID,
        ttl_s: int,
        media_root: Path,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Bind the store to one session.

        Args:
            redis: The cache client.
            user_id: The account.
            session_id: The session.
            ttl_s: How long every key outlives its last write.
            media_root: Where the sessions' audio lies (a segment's path is
                rebuilt from it, never read from the store).
            clock: When a publish happens (the active set's score).
        """
        self._redis = redis
        self._user_id = user_id
        self._session_id = session_id
        self._ttl_s = ttl_s
        self._media_root = media_root
        self._clock = clock
        self._published: set[int] = set()
        self._last_state: str | None = None

    # Spelled on a local ``user_id`` so the ADR-260 guard reads every family.

    @property
    def loop_key(self) -> str:
        """The lease of the session's one loop."""
        user_id = self._user_id
        return f"radio:loop:{user_id}:{self._session_id}"

    @property
    def _inbox_key(self) -> str:
        user_id = self._user_id
        return f"radio:inbox:{user_id}:{self._session_id}"

    @property
    def _state_key(self) -> str:
        user_id = self._user_id
        return f"radio:state:{user_id}:{self._session_id}"

    @property
    def _segments_key(self) -> str:
        user_id = self._user_id
        return f"radio:segments:{user_id}:{self._session_id}"

    # --- written by the routes ------------------------------------------------

    async def write_playhead(self, playhead: Playhead) -> None:
        """Leave the player's report for the loop (the last one wins)."""
        await self._redis.hset(self._inbox_key, _PLAYHEAD, json.dumps(playhead_to_dict(playhead)))
        await self._redis.expire(self._inbox_key, self._ttl_s)

    async def request_stop(self) -> None:
        """Ask the loop to stop at its next tick."""
        await self._redis.hset(self._inbox_key, _STOP, "1")
        await self._redis.expire(self._inbox_key, self._ttl_s)

    async def claim_loop(self, token: str, *, lease_s: int) -> bool:
        """Take the session's loop lease; False when a loop already holds it."""
        return await try_claim(self._redis, self.loop_key, token, ttl_seconds=lease_s)

    async def loop_alive(self) -> bool:
        """Whether a loop holds the lease."""
        return bool(await self._redis.exists(self.loop_key))

    async def read_state(self) -> SessionState | None:
        """The state the loop last published, or None (nothing yet, or unreadable)."""
        raw = await self._redis.get(self._state_key)
        if raw is None:
            return None
        try:
            return state_from_dict(json.loads(_text(raw)))
        except _UNREADABLE as exc:
            logger.warning("radio_state_unreadable", error_type=type(exc).__name__)
            return None

    async def read_segments(self, seqs: Collection[int]) -> dict[int, ProducedSegment]:
        """The published segments among ``seqs`` (an unreadable one is skipped)."""
        wanted = sorted(seqs)
        if not wanted:
            return {}
        raws = await self._redis.hmget(self._segments_key, [str(seq) for seq in wanted])
        return self._decoded(zip(wanted, raws, strict=True))

    async def read_ready(self) -> dict[int, ProducedSegment]:
        """Every published segment — what a restarted loop starts from."""
        raws = await self._redis.hgetall(self._segments_key)
        return self._decoded(raws.items())

    def _decoded(self, pairs: Any) -> dict[int, ProducedSegment]:
        """Decode ``(place, raw)`` pairs; a place or a value this release cannot read is skipped."""
        segments: dict[int, ProducedSegment] = {}
        for place, raw in pairs:
            if raw is None:
                continue
            try:
                seq = place if isinstance(place, int) else int(_text(place))
                segments[seq] = segment_from_dict(
                    json.loads(_text(raw)),
                    audio_path=segment_path(self._media_root, self._session_id, seq),
                )
            except _UNREADABLE as exc:
                logger.warning("radio_segment_unreadable", error_type=type(exc).__name__)
        return segments

    # --- read by the loop (its inbox) -------------------------------------------

    async def playhead(self) -> Playhead | None:
        """The player's last report."""
        raw = await self._redis.hget(self._inbox_key, _PLAYHEAD)
        if raw is None:
            return None
        try:
            return playhead_from_dict(json.loads(_text(raw)))
        except _UNREADABLE as exc:
            logger.warning("radio_playhead_unreadable", error_type=type(exc).__name__)
            return None

    async def stop_requested(self) -> bool:
        """Whether the listener stopped — or another session took the account's place."""
        if await self._redis.hget(self._inbox_key, _STOP) is not None:
            return True
        current = await RadioSessions(self._redis, ttl_s=self._ttl_s).current(self._user_id)
        return current is None or current.session_id != self._session_id

    # --- written by the loop (its board) ----------------------------------------

    async def publish(self, state: SessionState, ready: Mapping[int, ProducedSegment]) -> None:
        """Publish the state, and every segment not published yet.

        An unchanged state is not written again: the loop decides every
        second, the player reports every few, and each report changes the
        state — so every key's life is renewed while someone listens.
        """
        encoded = json.dumps(state_to_dict(state))
        fresh = {
            str(seq): json.dumps(segment_to_dict(segment))
            for seq, segment in ready.items()
            if seq not in self._published
        }
        if encoded == self._last_state and not fresh:
            return
        async with self._redis.pipeline(transaction=False) as pipe:
            if fresh:
                pipe.hset(self._segments_key, mapping=fresh)
                pipe.expire(self._segments_key, self._ttl_s)
            pipe.set(self._state_key, encoded, ex=self._ttl_s)
            pipe.expire(self._inbox_key, self._ttl_s)
            pipe.expire(record_key(self._user_id), self._ttl_s)
            if state.ended is None:
                pipe.zadd(ACTIVE_KEY, {str(self._session_id): self._clock().timestamp()})
            else:
                pipe.zrem(ACTIVE_KEY, str(self._session_id))
            await pipe.execute()
        self._published.update(int(seq) for seq in fresh)
        self._last_state = encoded


__all__ = [
    "ACTIVE_KEY",
    "RadioSessionRecord",
    "RadioSessionStore",
    "RadioSessions",
    "record_key",
]
