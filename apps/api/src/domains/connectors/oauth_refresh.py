"""One door to a fresh OAuth token, whoever holds it (audit AC-029, ADR-302 amendment 2026-10-23).

Four paths refreshed a legacy connector's token and only one of them took a lock; the
shared grants held a row lock across the provider's answer (ADR-304 forbids it); the Hue
bridge refreshed with no lock and no margin. Two refreshes of one token in flight are not
a waste, they are a hazard: a provider that ROTATES its refresh token answers the second
one ``invalid_grant``, and that refusal disconnected a person whose consent was intact.

So every refresh goes through :func:`ensure_fresh_credentials`, and the rules hold for
every holder of a token — a legacy connector, a shared grant, a Hue bridge:

- **One exchange per token.** Callers in one worker join one flight
  (``run_single_flight``); workers coordinate through an owner-token claim
  (``run_shared_flight``) whose lifetime and wait budget are derived from the
  exchange's own retry policy. A forced refresh JOINS a refresh in flight: either
  one ends with a fresh token.
- **No transaction across the network.** The door never uses its caller's session:
  it reads on a short session of its own, calls the provider with none open, and
  writes on another (ADR-304). Nothing of the caller's is committed behind its back.
- **The write is conditional.** It lands only if the token is still the one the
  exchange started from and its holder is still active; otherwise the winner's token
  is returned, and a revocation that happened during the call is never undone.
- **A revocation is verified before it disconnects anyone.** ``invalid_grant`` marks
  the holder in error only when the stored token is still the one that was refused —
  a token another worker rotated meanwhile is the winner's, not a revocation.
- **Waiters learn the verdict, not only the success.** Every attempt publishes
  ``<attempt>:<verdict>`` — a failure it did not expect included; a waiter accepts
  only a verdict published after it began waiting, so a revocation or an outage ends
  the wait at once.
- **A held row never hangs the door.** Writing on its own session, the door could
  wait for a row its caller's open transaction holds while the caller waits for the
  door — a cycle PostgreSQL cannot see. Every transition waits for its row under a
  bounded ``lock_timeout``; past it, a write is abandoned (the caller is served the
  token just issued, unstored; a waiter is told the refresh failed, never handed the
  expired token left stored) and a revocation is a failure, never a disconnection.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import StrEnum
from typing import Final, NamedTuple, Protocol
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.connectors.oauth_refresh_exchange import (
    RefreshRefusal,
    RefreshRefused,
    worst_case_refresh_seconds,
)
from src.infrastructure.async_utils import write_through_cancellation
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.errors import classify_database_error
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics import (
    oauth_refresh_flights_total,
    oauth_refresh_outcomes_total,
)
from src.infrastructure.utils.shared_flight import CLAIM_PREFIX, run_shared_flight
from src.infrastructure.utils.single_flight import run_single_flight

logger = structlog.get_logger(__name__)

#: The family of the verdict markers, declared in ``infrastructure/cache/key_families.py``.
OAUTH_REFRESH_MARKER_PREFIX: Final = "oauth_refresh"

#: A claim outlives the worst exchange by this much, and a waiter waits as long.
_CLAIM_MARGIN_SECONDS: Final = 5

#: Re-deliveries of a cancellation the final write survives: a rotated token lost
#: between the provider and the database disconnects the person at the next refresh.
_WRITE_CANCELLATION_ATTEMPTS: Final = 3


class StoredToken[C](NamedTuple):
    """A token as its holder stores it.

    Attributes:
        ciphertext: The stored ciphertext — the identity a conditional write compares.
        credentials: The decrypted credentials.
        active: Whether the holder may still be served (not revoked, not in error).
    """

    ciphertext: str
    credentials: C
    active: bool


class Refreshed[C](NamedTuple):
    """What an exchange produced, in the holder's own credential format.

    Attributes:
        credentials: The fresh credentials.
        reported_scopes: The scopes the provider reported; empty when it reported none.
    """

    credentials: C
    reported_scopes: frozenset[str]


class RefreshTarget[C](Protocol):
    """A holder of a refreshable token: its store, its exchange and its errors."""

    @property
    def kind(self) -> str:
        """A bounded label for the metrics (``connector``, ``grant``, ``hue_remote``)."""
        ...

    @property
    def flight_key(self) -> str:
        """The identity of the token: two callers with one key refresh one token."""
        ...

    @property
    def user_id(self) -> UUID:
        """The account the token belongs to."""
        ...

    async def read(self, db: AsyncSession) -> StoredToken[C] | None:
        """The stored token, or None when its holder is gone."""
        ...

    def needs_refresh(self, credentials: C, refresh_before: datetime | None) -> bool:
        """Whether these credentials expire before the threshold."""
        ...

    async def exchange(self, credentials: C) -> Refreshed[C]:
        """Exchange the refresh token. Raises ``RefreshRefused`` with why."""
        ...

    async def write_if_unchanged(
        self, db: AsyncSession, expected_ciphertext: str, refreshed: Refreshed[C]
    ) -> bool:
        """Store the fresh token if the stored one is still ``expected_ciphertext``."""
        ...

    async def revoke_if_unchanged(self, db: AsyncSession, expected_ciphertext: str) -> bool:
        """Mark the holder in error if the stored token is still the refused one."""
        ...

    def inactive_error(self) -> Exception:
        """What a caller receives when the holder is gone or no longer active."""
        ...

    def revoked_error(self, status_code: int | None) -> Exception:
        """What a caller receives when the person's consent is gone."""
        ...

    def failed_error(self) -> Exception:
        """What a caller receives when the provider could not refresh, for now."""
        ...


class RefreshOutcome(StrEnum):
    """What one refresh attempt ended with (``oauth_refresh_outcomes_total``)."""

    REFRESHED = "refreshed"
    FRESH_ALREADY = "fresh_already"
    WRITE_LOST = "write_lost"
    WRITE_CONTENDED = "write_contended"
    REVOKED = "revoked"
    REVOCATION_SUPERSEDED = "revocation_superseded"
    REVOCATION_CONTENDED = "revocation_contended"
    FAILED = "failed"
    INACTIVE = "inactive"


class _Landing(StrEnum):
    """How one conditional transition of a holder's store ended."""

    LANDED = "landed"
    #: The stored token is no longer the one the exchange started from.
    LOST = "lost"
    #: The row stayed held past the bounded lock wait.
    CONTENDED = "contended"


class _Granted[C](NamedTuple):
    """A refresh that ends with credentials to serve."""

    credentials: C


class _Refused(NamedTuple):
    """A refresh that ends with an error, and the verdict word its waiters read."""

    error: Callable[[], Exception]
    verdict: str
    #: The holder whose OWN state an ``inactive`` refusal states; None when it is another
    #: worker's verdict, read from its marker.
    holder: object | None = None


type _Verdict[C] = _Granted[C] | _Refused

#: The verdict word published for a refresh that ended with credentials.
_GRANTED: Final = "refreshed"


async def ensure_fresh_credentials[C](
    target: RefreshTarget[C],
    *,
    current: StoredToken[C] | None = None,
    force: bool = False,
    refresh_before: datetime | None = None,
) -> C:
    """Credentials valid past ``refresh_before``, refreshed at most once at a time.

    Args:
        target: The holder of the token.
        current: What the caller already read, so a fresh token costs no read at all.
        force: Refresh even a token that is still valid (or join a refresh in flight).
        refresh_before: The threshold; None means the on-demand margin.

    Returns:
        Fresh credentials in the holder's own format.

    Raises:
        Exception: The holder's ``inactive_error``, ``revoked_error`` or
            ``failed_error`` — or what an unexpected failure raised.
    """
    start = current if current is not None else await _read(target)
    if start is None or not start.active:
        raise target.inactive_error()
    if not force and not target.needs_refresh(start.credentials, refresh_before):
        return start.credentials
    verdict = await _flown(target, start, force=force, refresh_before=refresh_before)
    if _refuses_another_holder(verdict, target):
        # The holder that ran the attempt was refused for ITSELF (a service detached from a
        # shared grant meanwhile, say): this caller's own link is its own question.
        verdict = await _flown(target, start, force=force, refresh_before=refresh_before)
    if isinstance(verdict, _Refused):
        if _refuses_another_holder(verdict, target):
            # Refused twice for other holders: the refresh failed for now — never
            # « reconnect » for a link this caller may still hold.
            raise target.failed_error()
        raise verdict.error()
    return verdict.credentials


async def _flown[C](
    target: RefreshTarget[C], start: StoredToken[C], *, force: bool, refresh_before: datetime | None
) -> _Verdict[C]:
    """One flight of this worker for the token: run it, or join the one in flight."""
    flight = await run_single_flight(
        (OAUTH_REFRESH_MARKER_PREFIX, target.flight_key),
        lambda: _coalesced(target, start, force=force, refresh_before=refresh_before),
    )
    if flight.joined:
        oauth_refresh_flights_total.labels(kind=target.kind, how="joined").inc()
    return flight.value


def _refuses_another_holder[C](verdict: _Verdict[C], target: RefreshTarget[C]) -> bool:
    """Whether an ``inactive`` refusal states another holder's link, not this caller's."""
    return (
        isinstance(verdict, _Refused)
        and verdict.verdict == RefreshOutcome.INACTIVE.value
        and verdict.holder is not target
    )


async def _coalesced[C](
    target: RefreshTarget[C], start: StoredToken[C], *, force: bool, refresh_before: datetime | None
) -> _Verdict[C]:
    """One attempt across every worker; the others wait for its published verdict."""
    start_marker = await _marker(target)
    shared = await run_shared_flight(
        f"{CLAIM_PREFIX}:{OAUTH_REFRESH_MARKER_PREFIX}:{target.flight_key}",
        build=lambda: _attempt(target, start, force=force, refresh_before=refresh_before),
        read_shared=lambda: _published(target, start_marker),
        wait_budget_s=float(claim_ttl_seconds()),
        claim_ttl_s=claim_ttl_seconds(),
    )
    how = "claimed" if shared.claimed else ("waited" if shared.waited else "unclaimed")
    oauth_refresh_flights_total.labels(kind=target.kind, how=how).inc()
    return shared.value


async def _attempt[C](
    target: RefreshTarget[C], start: StoredToken[C], *, force: bool, refresh_before: datetime | None
) -> _Verdict[C]:
    """One attempt, whose verdict reaches the waiters whatever ends it.

    A failure the attempt did not expect — a database error, a client that changed, a
    read budget spent — publishes no verdict of its own: a waiter of another worker
    would wait the whole claim out (about 40 s at the defaults) before trying itself.
    It is published and counted as a failure, then raised to this worker's callers.
    """
    try:
        return await _exchange_and_store(target, start, force=force, refresh_before=refresh_before)
    except Exception:
        failed = _Refused(target.failed_error, RefreshOutcome.FAILED.value)
        await _concluded(target, RefreshOutcome.FAILED, failed)
        raise


async def _exchange_and_store[C](
    target: RefreshTarget[C], start: StoredToken[C], *, force: bool, refresh_before: datetime | None
) -> _Verdict[C]:
    """Re-read, exchange with no transaction open, then write conditionally."""
    stored = await _read(target)
    if stored is None or not stored.active:
        refused = _Refused(target.inactive_error, RefreshOutcome.INACTIVE.value, target)
        return await _concluded(target, RefreshOutcome.INACTIVE, refused)
    rotated_meanwhile = stored.ciphertext != start.ciphertext
    still_fresh = not target.needs_refresh(stored.credentials, refresh_before)
    if still_fresh and (rotated_meanwhile or not force):
        return await _concluded(target, RefreshOutcome.FRESH_ALREADY, _Granted(stored.credentials))
    try:
        refreshed = await target.exchange(stored.credentials)
    except RefreshRefused as refusal:
        if refusal.reason is RefreshRefusal.REVOKED:
            return await _settle_revocation(target, stored, refusal.status_code)
        failed = _Refused(target.failed_error, RefreshOutcome.FAILED.value)
        return await _concluded(target, RefreshOutcome.FAILED, failed)
    landing = await _write(target, stored.ciphertext, refreshed)
    if landing is _Landing.LANDED:
        await invalidate_oauth_connector_cache(target.user_id)
        return await _concluded(target, RefreshOutcome.REFRESHED, _Granted(refreshed.credentials))
    if landing is _Landing.CONTENDED:
        # Served to this flight, never stored: what a waiter would read is the expired
        # token, so it is told the refresh failed rather than handed that one.
        return await _concluded(
            target,
            RefreshOutcome.WRITE_CONTENDED,
            _Granted(refreshed.credentials),
            published=RefreshOutcome.FAILED.value,
        )
    return await _concluded(target, RefreshOutcome.WRITE_LOST, await _winner(target))


async def _settle_revocation[C](
    target: RefreshTarget[C], stored: StoredToken[C], status_code: int | None
) -> _Verdict[C]:
    """``invalid_grant`` disconnects only when the refused token is still the stored one."""
    landing = await _transition(lambda db: target.revoke_if_unchanged(db, stored.ciphertext))
    if landing is _Landing.CONTENDED:
        # Unverified — the holder of the row may be replacing that very token.
        failed = _Refused(target.failed_error, RefreshOutcome.FAILED.value)
        return await _concluded(target, RefreshOutcome.REVOCATION_CONTENDED, failed)
    if landing is _Landing.LOST:
        return await _concluded(target, RefreshOutcome.REVOCATION_SUPERSEDED, await _winner(target))
    await invalidate_oauth_connector_cache(target.user_id)
    refused = _Refused(_revoked(target, status_code), RefreshOutcome.REVOKED.value)
    return await _concluded(target, RefreshOutcome.REVOKED, refused)


def _revoked[C](target: RefreshTarget[C], status_code: int | None) -> Callable[[], Exception]:
    """The revocation error with its status bound, raised by every caller of the flight."""
    return lambda: target.revoked_error(status_code)


async def _winner[C](target: RefreshTarget[C]) -> _Verdict[C]:
    """The token another writer stored, when its holder is still servable."""
    stored = await _read(target)
    if stored is None or not stored.active:
        return _Refused(target.inactive_error, RefreshOutcome.INACTIVE.value, target)
    return _Granted(stored.credentials)


async def _write[C](
    target: RefreshTarget[C], expected_ciphertext: str, refreshed: Refreshed[C]
) -> _Landing:
    """The conditional write, carried to its end through a cancellation once started."""
    landing = _Landing.LOST

    async def write() -> None:
        nonlocal landing
        landing = await _transition(
            lambda db: target.write_if_unchanged(db, expected_ciphertext, refreshed)
        )

    if await write_through_cancellation(
        write, attempts=_WRITE_CANCELLATION_ATTEMPTS, label="oauth_refresh_write"
    ):
        raise asyncio.CancelledError
    return landing


async def _transition(apply: Callable[[AsyncSession], Awaitable[bool]]) -> _Landing:
    """One conditional transition on a short session, under a bounded wait for its row.

    Args:
        apply: The holder's transition; True when it landed.

    Returns:
        How the transition ended — a row held past the bound is CONTENDED, read from
        the server's SQLSTATE, never from a message.

    Raises:
        DBAPIError: Any other database failure.
    """
    landing = _Landing.LOST
    async with get_db_context() as db:
        # A literal, not a bind: SET takes no parameters, and the value is a validated int.
        await db.execute(
            text(f"SET LOCAL lock_timeout = {settings.oauth_refresh_write_lock_timeout_ms}")
        )
        try:
            landing = _Landing.LANDED if await apply(db) else _Landing.LOST
        except DBAPIError as exc:
            if classify_database_error(exc) != "timeout":
                raise
            # The failed transaction ends HERE: the session helper reports no incident.
            await db.rollback()
            landing = _Landing.CONTENDED
    return landing


async def _concluded[C](
    target: RefreshTarget[C],
    outcome: RefreshOutcome,
    verdict: _Verdict[C],
    *,
    published: str | None = None,
) -> _Verdict[C]:
    """Count the attempt, publish its verdict for the waiters, log its facts.

    Args:
        target: The holder of the token.
        outcome: The metrics label of the attempt.
        verdict: What this flight's callers receive.
        published: The verdict word waiters read, when it is not this flight's own.

    Returns:
        ``verdict``.
    """
    oauth_refresh_outcomes_total.labels(kind=target.kind, outcome=outcome.value).inc()
    own = verdict.verdict if isinstance(verdict, _Refused) else _GRANTED
    await _publish(target, published or own)
    logger.info("oauth_refresh_concluded", kind=target.kind, outcome=outcome.value)
    return verdict


async def _read[C](target: RefreshTarget[C]) -> StoredToken[C] | None:
    async with get_db_context() as db:
        return await target.read(db)


async def _published[C](target: RefreshTarget[C], start_marker: str | None) -> _Verdict[C] | None:
    """A verdict published since this caller began waiting, or None while there is none."""
    marker = await _marker(target)
    if marker is None or marker == start_marker:
        return None
    verdict = marker.partition(":")[2]
    if verdict == _GRANTED:
        return await _winner(target)
    if verdict == RefreshOutcome.REVOKED.value:
        return _Refused(_revoked(target, None), verdict)
    if verdict == RefreshOutcome.FAILED.value:
        return _Refused(target.failed_error, verdict)
    return _Refused(target.inactive_error, RefreshOutcome.INACTIVE.value)


def _marker_key[C](target: RefreshTarget[C]) -> str:
    return f"{OAUTH_REFRESH_MARKER_PREFIX}:{target.flight_key}"


async def _marker[C](target: RefreshTarget[C]) -> str | None:
    """The last published verdict; None when there is none or Redis cannot say."""
    try:
        redis = await get_redis_cache()
        raw = await redis.get(_marker_key(target))
    except Exception as error:  # no marker is « not yet », never a failure
        logger.debug("oauth_refresh_marker_unreadable", error_type=type(error).__name__)
        return None
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else str(raw)


async def _publish[C](target: RefreshTarget[C], verdict: str) -> None:
    """Publish ``<attempt>:<verdict>``; a lost marker only makes a waiter wait longer."""
    try:
        redis = await get_redis_cache()
        await redis.set(
            _marker_key(target), f"{uuid.uuid4().hex}:{verdict}", ex=claim_ttl_seconds()
        )
    except Exception as error:  # the verdict is already in the database
        logger.debug("oauth_refresh_marker_unpublished", error_type=type(error).__name__)


def claim_ttl_seconds() -> int:
    """How long a claim outlives a holder that died.

    An attempt is one exchange and at most ONE bounded transition (the write or the
    revocation), so the claim covers both, and a margin.
    """
    bounded_transition = settings.oauth_refresh_write_lock_timeout_ms / 1000
    return math.ceil(worst_case_refresh_seconds() + bounded_transition) + _CLAIM_MARGIN_SECONDS


async def invalidate_oauth_connector_cache(user_id: UUID) -> None:
    """Invalidate settings after a durable OAuth transition, without masking it on Redis outage."""
    try:
        cache = await get_redis_cache()
        await cache.delete(f"user_connectors:{user_id}")
    except Exception as error:  # the transition is already durable
        logger.warning(
            "oauth_connector_cache_invalidation_failed",
            user_id=str(user_id),
            error_type=type(error).__name__,
        )
