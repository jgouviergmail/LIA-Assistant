"""Wake queue: a processed push notification asks for a heartbeat decision (ADR-261).

The webhook stays fast and dumb: it enqueues ``(user, provider)`` with what
it already knows (the Gmail history id it just saw, the Drive page token)
and answers 200. A short leader-elected sweep (``infrastructure/scheduler/
heartbeat_wake_sweep.py``) pops the queue and does the work — delta, pre-
filter, then the heartbeat task for THAT user under the full eligibility
checker. Nothing here decides anything.

Storage (Redis, families declared in ADR-260):

- ``heartbeat:wake:pending`` — a SET of user ids (global: no user id in the
  key), popped atomically by the sweep (``SPOP``: two workers never serve
  the same user twice);
- ``heartbeat:wake:payload:{user_id}:{provider}`` — the oldest queued
  payload for that pair (``SET NX EX``: a storm of notifications is ONE
  wake, dated by the first); the TTL is the staleness bound;
- ``heartbeat:wake:cooldown:{user_id}`` — ``SET NX EX`` per served wake.

Best-effort everywhere: a Redis failure costs a wake, never a notification
(the periodic tick remains).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from src.core.constants import (
    REDIS_KEY_WAKE_COOLDOWN_PREFIX,
    REDIS_KEY_WAKE_PAYLOAD_PREFIX,
    REDIS_KEY_WAKE_PENDING,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class WakePayload:
    """One queued wake.

    Attributes:
        user_id: Owner of the channel that notified.
        provider: ``google_gmail`` | ``google_calendar`` | ``google_drive``.
        enqueued_at: When the FIRST notification of the pair was queued (UTC).
        history_id: Gmail history id carried by the notification, if any.
        page_token: Drive changes page token to consume, if any.
    """

    user_id: UUID
    provider: str
    enqueued_at: datetime
    history_id: int | None = None
    page_token: str | None = None
    # Enriched by the sweep, in process only (never persisted): what the
    # pre-filter fetched, handed to the aggregator so nothing is read twice.
    messages: tuple[dict[str, Any], ...] = ()
    events: tuple[dict[str, Any], ...] = ()
    new_history_id: str | None = None

    def to_json(self) -> str:
        """The QUEUED shape only — the enriched fields never leave the process."""
        return json.dumps(
            {
                "user_id": str(self.user_id),
                "provider": self.provider,
                "enqueued_at": self.enqueued_at.isoformat(),
                "history_id": self.history_id,
                "page_token": self.page_token,
            }
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> WakePayload | None:
        try:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            return cls(
                user_id=UUID(str(data["user_id"])),
                provider=str(data["provider"]),
                enqueued_at=datetime.fromisoformat(str(data["enqueued_at"])),
                history_id=int(data["history_id"]) if data.get("history_id") is not None else None,
                page_token=str(data["page_token"]) if data.get("page_token") else None,
            )
        except KeyError, ValueError, TypeError, json.JSONDecodeError:
            return None


def payload_key(user_id: UUID | str, provider: str) -> str:
    return f"{REDIS_KEY_WAKE_PAYLOAD_PREFIX}{user_id}:{provider}"


def cooldown_key(user_id: UUID | str) -> str:
    return f"{REDIS_KEY_WAKE_COOLDOWN_PREFIX}{user_id}"


async def enqueue_wake(
    redis: Any,
    user_id: UUID,
    provider: str,
    *,
    ttl_seconds: int,
    history_id: int | None = None,
    page_token: str | None = None,
) -> bool:
    """Queue one wake for ``(user, provider)`` (best-effort).

    Args:
        redis: Async Redis client.
        user_id: Channel owner.
        provider: Push provider value.
        ttl_seconds: Staleness bound of the queued payload.
        history_id: Gmail history id from the notification, if any.
        page_token: Drive changes token to consume, if any.

    Returns:
        True when a NEW payload was queued; False when one was already
        pending (the storm case) or Redis failed.
    """
    payload = WakePayload(
        user_id=user_id,
        provider=provider,
        enqueued_at=datetime.now(UTC),
        history_id=history_id,
        page_token=page_token,
    )
    try:
        created = await redis.set(
            payload_key(user_id, provider), payload.to_json(), nx=True, ex=ttl_seconds
        )
        await redis.sadd(REDIS_KEY_WAKE_PENDING, str(user_id))
        return bool(created)
    except Exception as exc:  # noqa: BLE001 — best-effort: a lost wake is a tick, not a bug
        logger.debug("push_wake_enqueue_failed", provider=provider, error=str(exc))
        return False


async def pop_wakes(redis: Any, limit: int, providers: tuple[str, ...]) -> list[WakePayload]:
    """Pop up to ``limit`` users from the queue and collect their payloads.

    A user popped with no live payload (expired TTL) yields nothing — that
    wake is stale by definition. Payloads are DELETED on read: the sweep owns
    them from here.

    Args:
        redis: Async Redis client.
        limit: Maximum users to pop.
        providers: The provider values to look up per user.

    Returns:
        The payloads to serve, oldest first.
    """
    try:
        popped = await redis.spop(REDIS_KEY_WAKE_PENDING, limit)
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.debug("push_wake_pop_failed", error=str(exc))
        return []
    if not popped:
        return []
    if isinstance(popped, str | bytes):
        popped = [popped]
    payloads: list[WakePayload] = []
    for raw_user in popped:
        user_str = raw_user.decode() if isinstance(raw_user, bytes) else str(raw_user)
        for provider in providers:
            key = payload_key(user_str, provider)
            raw = await redis.get(key)
            if not raw:
                continue
            await redis.delete(key)
            payload = WakePayload.from_json(raw)
            if payload is not None:
                payloads.append(payload)
    payloads.sort(key=lambda p: p.enqueued_at)
    return payloads


async def try_acquire_wake_cooldown(redis: Any, user_id: UUID, minutes: int) -> bool:
    """One served wake per user per cooldown window (``SET NX EX``).

    Redis failure → False: a wake must not fire when its own budget cannot
    be checked (the periodic tick still runs).
    """
    try:
        return bool(await redis.set(cooldown_key(user_id), "1", nx=True, ex=minutes * 60))
    except Exception as exc:  # noqa: BLE001 — closed on failure by design
        logger.debug("push_wake_cooldown_check_failed", error=str(exc))
        return False
