"""Reading presence — the fourth rhythm source (ADR-214 amendment 2026-09-03).

The rhythm detector learned from typed messages, human runs and resets. A
user who lives by the heartbeat — reads the briefing, opens the notification,
gives it a thumb — was invisible to it (measured on the primary account: 106
notifications read in 30 days, 361 app openings in 20 days, 5 typed turns).
Two signals now count as presence, decided by the owner:

- ``visibility``: the client says "the user has LIA in front of them" (on
  mount, on ``visibilitychange``→visible, on focus — never from a background
  poll). Gated by ``habits_presence_enabled`` (OFF by default) on top of the
  master flag and the user preference.
- ``feedback``: a thumb on a notification is an explicit human act; it counts
  whenever habits are enabled for the user, whatever the visibility flag.

A notification being SENT is never a presence — nothing here is reachable
from the proactive runners.

Storage: at most one banked hour per user per local hour (``SET NX EX`` on
``presence:{uid}:{date}:{hour}``), written straight into the durable rollup
``user_activity_days`` through a server-side atomic UPSERT, plus a
last-presence marker (``presence:last:{uid}``) the heartbeat inactivity
gate reads. Both are ``USER_LEARNING`` families (ADR-260): a conversation
reset never touches them; « Tout oublier » and account deletion do.

Fail-open everywhere: Redis down means no throttle (the client already
throttles) and the hour is still banked; a DB failure is the caller's
transaction to report.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import HABITS_PRESENCE_HOUR_LOCK_SECONDS, REDIS_KEY_PRESENCE_PREFIX
from src.core.time_utils import resolve_user_timezone
from src.domains.habits.repository import HabitsRepository
from src.infrastructure.observability.metrics_habits import habits_presence_recorded_total

logger = structlog.get_logger(__name__)

PresenceKind = Literal["visibility", "feedback"]
PresenceOutcome = Literal["banked", "throttled", "disabled"]


def hour_key(user_id: UUID | str, local_date: date, hour: int) -> str:
    """The per-hour throttle key."""
    return f"{REDIS_KEY_PRESENCE_PREFIX}{user_id}:{local_date.isoformat()}:{hour:02d}"


def last_key(user_id: UUID | str) -> str:
    """The last-presence marker key."""
    return f"{REDIS_KEY_PRESENCE_PREFIX}last:{user_id}"


def _observe(kind: str, outcome: str) -> None:
    with suppress(Exception):
        habits_presence_recorded_total.labels(kind=kind, outcome=outcome).inc()


def presence_allowed(user: Any, kind: PresenceKind) -> bool:
    """Whether this signal may count for this user (pure gate).

    Args:
        user: The User row (``habits_enabled`` preference).
        kind: ``visibility`` or ``feedback``.

    Returns:
        False when habits are off (globally or for the user), or when the
        visibility signal is not enabled by the owner.
    """
    if not getattr(settings, "habits_enabled", False):
        return False
    if not getattr(user, "habits_enabled", True):
        return False
    if kind == "visibility" and not getattr(settings, "habits_presence_enabled", False):
        return False
    return True


async def _redis_or_none() -> Any:
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        return await get_redis_cache()
    except Exception as exc:  # noqa: BLE001 — fail-open: presence never blocks a request
        logger.debug("presence_redis_unavailable", error=str(exc))
        return None


async def record_presence(
    db: AsyncSession,
    user: Any,
    *,
    kind: PresenceKind,
    at: datetime | None = None,
) -> PresenceOutcome:
    """Bank one presence hour for ``user`` (idempotent per local hour).

    Args:
        db: Caller-owned session; the caller commits.
        user: The User row (id, timezone, preference).
        kind: ``visibility`` (app opening) or ``feedback`` (a thumb).
        at: The instant of the signal (UTC); defaults to now.

    Returns:
        ``banked`` (an hour was written), ``throttled`` (that local hour was
        already banked) or ``disabled`` (gate refused).
    """
    if not presence_allowed(user, kind):
        _observe(kind, "disabled")
        return "disabled"

    moment = (at or datetime.now(UTC)).astimezone(resolve_user_timezone(user))
    local_date, hour = moment.date(), moment.hour
    redis = await _redis_or_none()

    acquired = True
    if redis is not None:
        # Redis failure → fail-open: bank anyway (the client throttles, and
        # the rollup write is idempotent by MAX).
        with suppress(Exception):
            acquired = bool(
                await redis.set(
                    hour_key(user.id, local_date, hour),
                    "1",
                    nx=True,
                    ex=HABITS_PRESENCE_HOUR_LOCK_SECONDS,
                )
            )
        with suppress(Exception):
            await redis.set(
                last_key(user.id),
                moment.astimezone(UTC).isoformat(),
                ex=int(settings.habits_presence_last_ttl_days) * 86400,
            )

    if not acquired:
        _observe(kind, "throttled")
        return "throttled"

    await HabitsRepository(db).bump_activity_hour(user.id, local_date, hour)
    _observe(kind, "banked")
    logger.debug(
        "habits_presence_banked",
        user_id=str(user.id),
        kind=kind,
        local_hour=hour,
    )
    return "banked"


async def last_presence_at(user_id: UUID | str) -> datetime | None:
    """The last presence marker (UTC), or None (never seen / Redis down)."""
    redis = await _redis_or_none()
    if redis is None:
        return None
    try:
        raw = await redis.get(last_key(user_id))
    except Exception as exc:  # noqa: BLE001 — advisory read
        logger.debug("presence_last_read_failed", error=str(exc))
        return None
    if not raw:
        return None
    value = raw.decode() if isinstance(raw, bytes) else str(raw)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


async def last_seen_at(user: Any) -> datetime | None:
    """The user's last sign of life: the later of ``last_login`` and the last
    presence marker (UTC). The heartbeat inactivity gate reads this instead
    of ``last_login`` alone — a user who reads without signing in again is
    not inactive (two accounts were silenced that way, measured 2026-09-03).

    Args:
        user: The User row.

    Returns:
        The latest instant, or None when neither exists.
    """
    candidates: list[datetime] = []
    login = getattr(user, "last_login", None)
    if login is not None:
        candidates.append(login if login.tzinfo is not None else login.replace(tzinfo=UTC))
    presence = await last_presence_at(user.id)
    if presence is not None:
        candidates.append(presence)
    return max(candidates, default=None)


async def forget_user(redis: Any, user_id: UUID | str) -> int:
    """Delete every presence key of one user (« Tout oublier », ADR-260).

    Args:
        redis: Async Redis client.
        user_id: Owner.

    Returns:
        Number of keys deleted (exact).
    """
    keys: list[str] = []
    async for key in redis.scan_iter(match=f"{REDIS_KEY_PRESENCE_PREFIX}{user_id}:*"):
        keys.append(key.decode() if isinstance(key, bytes) else str(key))
    keys.append(last_key(user_id))
    deleted = await redis.delete(*keys)
    return int(deleted or 0)
