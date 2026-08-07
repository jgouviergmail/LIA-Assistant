"""How many strangers a demonstrator may enrol in one UTC day.

Per-address rate limiting bounds one caller; it cannot bound an instance,
because the identity it keys on is chosen by the caller. Measured 2026-08-07
against the running demonstrator: thirty accounts in 6,4 seconds and not one
refusal, because ``CF-Connecting-IP`` was supplied per request and the bucket
key moved with it. Even intact, five registrations a minute is three hundred
verification emails an hour from a single address.

What pays for those emails is the operator's smarthost quota and their
domain's sending reputation, and the daily SPEND ceiling is blind to both:
mail is not a cost family. So this is the bound that holds — counted from the
accounts themselves, which no header can rotate.

Design, deliberately the same as the spend ceiling (ADR-216):
- **the authority is PostgreSQL**, not a cache an attacker can outrun;
- **the reservation is ONE atomic statement**, never a count followed by an
  insert. The first version counted rows, and a burst walked through it: with
  a ceiling of five, forty registrations released together by a thread barrier
  produced **37 accounts** (measured 2026-08-07). Every request read the count
  before any of them committed. Sequential probing had hidden it, because
  password hashing is slow enough to serialise a `curl` loop;
- **a refused attempt consumes nothing**: the UPSERT's ``WHERE`` means the
  counter only moves when the reservation is granted, so a burst of refusals
  cannot burn the day for honest visitors;
- **reaching the ceiling is exhaustion**, and an unreadable ledger DENIES: an
  instance that cannot reserve cannot bound the mail it emits;
- **the window is the UTC day**, the one the ledger and the nightly purge
  already use — a second definition of "tomorrow" would drift the day one of
  them moved;
- **an absent limit disables it entirely**, so an instance that never sets it
  behaves exactly as it did before.

Created: 2026-08-07 (live-demonstrator programme, security audit)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.usage_limits.instance_budget import seconds_until_next_utc_day
from src.domains.usage_limits.models import InstanceDailyBudget

logger = structlog.get_logger(__name__)

__all__ = [
    "DemoSignupDecision",
    "reserve_demo_signup",
    "seconds_until_next_utc_day",
]


@dataclass(frozen=True)
class DemoSignupDecision:
    """The verdict plus what a refused visitor needs to be told."""

    allowed: bool
    #: Accounts this instance created since UTC midnight, ``None`` when the
    #: database could not answer — which is itself a refusal.
    created_today: int | None
    limit: int | None
    retry_after_seconds: int


async def reserve_demo_signup(
    session: AsyncSession,
    *,
    limit: int | None,
    now: datetime | None = None,
) -> DemoSignupDecision:
    """Claim one of today's visitor slots, atomically, or refuse.

    One statement does the whole decision. ``ON CONFLICT DO UPDATE ... WHERE
    signup_count < :limit`` makes Postgres take a row lock on today's ledger
    line, evaluate the bound against the COMMITTED value, and either increment
    and return the new rank or return nothing at all. Two simultaneous callers
    are serialised by that row lock, which is exactly what counting rows in a
    separate SELECT could not do.

    Args:
        session: Database session; the caller owns the transaction.
        limit: Slots per UTC day. ``None`` disables the ceiling.
        now: Injected instant (tests); defaults to the wall clock.

    Returns:
        The verdict, the rank the reservation got, and when to come back.
    """
    current = (now or datetime.now(UTC)).astimezone(UTC)
    retry_after = seconds_until_next_utc_day(current)

    if limit is None:
        return DemoSignupDecision(
            allowed=True, created_today=None, limit=None, retry_after_seconds=retry_after
        )

    utc_day = current.date()
    # One statement, built in one expression: MyPy types the `.returning()`
    # result differently from the Insert it came from, and rebinding the same
    # name is what made that a type error rather than a detail.
    reservation = (
        pg_insert(InstanceDailyBudget)
        .values(utc_day=utc_day, signup_count=1)
        .on_conflict_do_update(
            index_elements=["utc_day"],
            set_={"signup_count": InstanceDailyBudget.signup_count + 1},
            # The bound lives HERE, inside the statement Postgres serialises.
            # A ``WHERE`` that fails leaves the row untouched and returns no
            # line, so a refusal costs nothing.
            where=InstanceDailyBudget.signup_count < limit,
        )
        .returning(InstanceDailyBudget.signup_count)
    )

    try:
        reserved = (await session.execute(reservation)).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 — an unreservable ceiling refuses
        logger.error(
            "demo_signup_reservation_failed",
            error_type=type(exc).__name__,
            detail="refusing the registration: an instance that cannot reserve "
            "a slot cannot bound the mail it sends",
        )
        return DemoSignupDecision(
            allowed=False, created_today=None, limit=limit, retry_after_seconds=retry_after
        )

    if reserved is None:
        # Either the row exists and is at the ceiling, or the INSERT lost the
        # race and the UPDATE's WHERE refused. Both mean: full for today.
        logger.warning("demo_signup_ceiling_reached", limit=limit, retry_after_seconds=retry_after)
        return DemoSignupDecision(
            allowed=False, created_today=None, limit=limit, retry_after_seconds=retry_after
        )

    return DemoSignupDecision(
        allowed=True,
        created_today=int(reserved),
        limit=limit,
        retry_after_seconds=retry_after,
    )
