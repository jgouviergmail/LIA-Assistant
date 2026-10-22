"""Short, ordered PostgreSQL reservations; an unknown bill never silently releases funds."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from src.domains.proactive_discussions.finance_models import (
    DiscussionBudgetBucket,
    DiscussionSpendReservation,
)
from src.domains.proactive_discussions.models import DiscussionPreference
from src.domains.proactive_discussions.repository import DiscussionRepository, owns_claim
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.shared.discussion_sources import DiscussionValue


class BudgetLimits(DiscussionValue):
    """The three operator ceilings, in USD: per account and day, per instance and day,
    per run.
    """

    owner_daily: Decimal = Field(gt=0, allow_inf_nan=False)
    instance_daily: Decimal = Field(gt=0, allow_inf_nan=False)
    run_max: Decimal = Field(gt=0, allow_inf_nan=False)


@dataclass(frozen=True)
class SpendReservation:
    """A run's held allowance: whose, which run, which UTC day, how much (USD)."""

    owner_id: UUID
    run_id: UUID
    day: date
    amount: Decimal


#: Why a reservation was declined: the claim no longer holds the account, the run
#: ceiling itself is below what the run's first call may cost, or the day has less
#: room than that call.
ReservationRefusal = Literal["stale_claim", "ceiling_too_low", "no_room"]


def _amount(value: Decimal) -> Decimal:
    if not value.is_finite() or value < 0:
        raise ValueError("invalid discretionary amount")
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_CEILING)


@dataclass(frozen=True)
class BudgetAvailability:
    """Today's allowance as the reservation reads it, without taking any lock.

    Booleans only, on purpose: a person is told THAT a ceiling stops a run, never
    by how much, and never what the other accounts spent. A run starts only when
    the run ceiling and both days can each hold its first call's bound.
    """

    run_insufficient: bool
    owner_available: bool
    instance_available: bool
    resets_at: datetime


def utc_day_end(now: datetime) -> datetime:
    """The instant the UTC day holding ``now`` ends, and its buckets start again."""
    day = now.astimezone(UTC).date()
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=UTC)


def _receipt(row: DiscussionSpendReservation) -> SpendReservation:
    return SpendReservation(
        owner_id=row.user_id, run_id=row.run_id, day=row.day, amount=row.estimate_usd
    )


class SpendRepository(DiscussionRepository):
    """Discretionary reservations: held before a run spends, settled from its real spend."""

    async def _reservation(self, owner: UUID, run_id: UUID) -> DiscussionSpendReservation | None:
        row: DiscussionSpendReservation | None = await self.db.scalar(
            select(DiscussionSpendReservation)
            .where(
                DiscussionSpendReservation.user_id == owner,
                DiscussionSpendReservation.run_id == run_id,
            )
            .with_for_update()
        )
        return row

    async def _buckets(self, owner: UUID, day: date) -> tuple[DiscussionBudgetBucket, ...]:
        rows = await self.db.scalars(
            select(DiscussionBudgetBucket)
            .where(
                DiscussionBudgetBucket.day == day,
                DiscussionBudgetBucket.scope_key.in_(("instance", f"owner:{owner}")),
            )
            .order_by(DiscussionBudgetBucket.scope_key)
            .with_for_update()
        )
        return tuple(rows.all())

    async def reserve(
        self,
        claim: RunClaim,
        *,
        estimate: Decimal,
        limits: BudgetLimits,
        now: datetime,
        minimum: Decimal = Decimal(0),
    ) -> SpendReservation | ReservationRefusal:
        """Hold a run's allowance in both of today's buckets, or decline.

        The run holds its estimate or what is left of the account's and the
        instance's day, whichever is smallest: a run never needs the whole run
        ceiling to start, only room for its first call (``minimum``). Amounts are
        rounded up to eight decimals. A second call for the same run returns the
        reservation it already holds.

        Args:
            claim: The run's claim.
            estimate: The run's upper cost, in USD (at most the run ceiling).
            limits: The configured ceilings.
            now: The current instant; buckets are UTC days.
            minimum: The least the run must hold to make its first call, in USD.

        Returns:
            The reservation, or why it was declined.

        Raises:
            ValueError: The estimate or the minimum is not a finite, non-negative
                amount, or the estimate is not within the run ceiling.
        """
        requested, floor = _amount(estimate), _amount(minimum)
        if requested <= 0 or requested > limits.run_max:
            raise ValueError("a run reserves a positive amount within its ceiling")
        if requested < floor:
            # A configuration no day can fix: never reported as a day without room.
            return "ceiling_too_low"
        await self._owner(claim.owner_id)
        preference = await self._preference(claim.owner_id, lock=True)
        if not owns_claim(preference, claim, now):
            return "stale_claim"
        existing = await self._reservation(claim.owner_id, claim.run_id)
        if existing is not None:
            return _receipt(existing) if existing.state == "held" else "stale_claim"
        day = now.astimezone(UTC).date()
        await self.db.execute(
            insert(DiscussionBudgetBucket)
            .values(
                [
                    {"scope_key": "instance", "user_id": None, "day": day},
                    {"scope_key": f"owner:{claim.owner_id}", "user_id": claim.owner_id, "day": day},
                ]
            )
            .on_conflict_do_nothing(
                index_elements=[DiscussionBudgetBucket.scope_key, DiscussionBudgetBucket.day]
            )
        )
        buckets = await self._buckets(claim.owner_id, day)
        if len(buckets) != 2:
            return "no_room"
        amount = min(requested, *(_room(bucket, limits) for bucket in buckets))
        if not _can_start(amount, floor):
            return "no_room"
        for bucket in buckets:
            bucket.held_usd += amount
        row = DiscussionSpendReservation(
            user_id=claim.owner_id,
            run_id=claim.run_id,
            day=day,
            estimate_usd=amount,
            actual_usd=Decimal(0),
            state="held",
        )
        self.db.add(row)
        await self.db.flush()
        return _receipt(row)

    async def settle(self, owner: UUID, run_id: UUID, *, actual: Decimal, uncertain: bool) -> bool:
        """Close a reservation with what the run really spent.

        A certain settlement moves the real spend to spent and releases the rest of
        the hold. An uncertain one keeps held what was issued to calls and is not
        billed yet — the most an unknown bill can be, so it never silently releases
        funds — and releases the reservation's unissued remainder; a later certain
        receipt still settles it. Measured 2026-10-21: holding the whole estimate, one
        interrupted run that had issued 0.09 USD kept 4.94 USD held and refused every
        later run of the day. Known spend is never decreased.

        Args:
            owner: The account.
            run_id: The run.
            actual: What the run really spent, in USD.
            uncertain: Whether part of the bill is unknown.

        Returns:
            True when the reservation changed; False when it is absent, already
            settled, or unchanged.

        Raises:
            ValueError: The amount is invalid or lower than the known spend, or the
                reservation lost its buckets.
        """
        actual = _amount(actual)
        row = await self._reservation(owner, run_id)
        if row is None or row.state == "settled":
            return False
        if actual < row.actual_usd:
            raise ValueError("a late receipt cannot erase already known spend")
        if row.state == "uncertain" and uncertain and actual == row.actual_usd:
            return False
        buckets = await self._buckets(owner, row.day)
        if len(buckets) != 2:
            raise ValueError("discretionary reservation lost its budget buckets")
        previous_hold = (
            row.estimate_usd
            if row.state == "held"
            else max(Decimal(0), row.issued_usd - row.actual_usd)
        )
        retained = max(Decimal(0), row.issued_usd - actual) if uncertain else Decimal(0)
        for bucket in buckets:
            bucket.held_usd += retained - previous_hold
            bucket.spent_usd += actual - row.actual_usd
        row.actual_usd, row.state = actual, "uncertain" if uncertain else "settled"
        await self.db.flush()
        return True

    async def issue(
        self,
        claim: RunClaim,
        *,
        amount: Decimal,
        now: datetime,
        committed: Decimal = Decimal(0),
    ) -> bool:
        """Issue one call's upper bound, while the claim and the hold allow it.

        The run's exposure is what it has committed (its known spend and the holds
        nobody has billed yet) plus this call's bound: a finished call counts for
        what it cost, never for the bound it was admitted under, so a pessimistic
        bound does not consume the reservation of the calls after it. ``issued_usd``
        keeps the highest exposure reached, which crash recovery reads as possibly
        spent.

        Args:
            claim: The run's claim.
            amount: The call's upper cost, in USD.
            now: The current instant.
            committed: What the run had committed before this call, in USD.

        Returns:
            True when issued; False when the claim, the hold, its day or its room
            refuses.

        Raises:
            ValueError: An amount is not a finite, non-negative amount.
        """
        exposure = _amount(committed) + _amount(amount)
        await self._owner(claim.owner_id)
        preference = await self._preference(claim.owner_id, lock=True)
        if not owns_claim(preference, claim, now):
            return False
        row = await self._reservation(claim.owner_id, claim.run_id)
        if (
            row is None
            or row.state != "held"
            or row.day != now.astimezone(UTC).date()
            or exposure > row.estimate_usd
        ):
            return False
        row.issued_usd = max(row.issued_usd, exposure)
        await self.db.flush()
        return True

    async def availability(
        self,
        owner: UUID,
        *,
        limits: BudgetLimits,
        now: datetime,
        minimum: Decimal = Decimal(0),
    ) -> BudgetAvailability:
        """Whether a run could start today, by the reservation's own predicate.

        Args:
            owner: The account asking.
            limits: The configured ceilings.
            now: The clock; buckets are UTC days.
            minimum: The least a run must hold to make its first call, in USD.

        Returns:
            Whether the run ceiling and each day's ceiling still let a run start,
            and when the days renew.
        """
        day = now.astimezone(UTC).date()
        used = {
            bucket.scope_key: bucket.spent_usd + bucket.held_usd
            for bucket in await self.db.scalars(
                select(DiscussionBudgetBucket).where(
                    DiscussionBudgetBucket.day == day,
                    DiscussionBudgetBucket.scope_key.in_(("instance", f"owner:{owner}")),
                )
            )
        }
        owner_room = max(Decimal(0), limits.owner_daily - used.get(f"owner:{owner}", Decimal(0)))
        instance_room = max(Decimal(0), limits.instance_daily - used.get("instance", Decimal(0)))
        floor = _amount(minimum)
        return BudgetAvailability(
            run_insufficient=limits.run_max < floor,
            owner_available=_can_start(owner_room, floor),
            instance_available=_can_start(instance_room, floor),
            resets_at=utc_day_end(now),
        )

    async def recover_expired(self, *, now: datetime, limit: int) -> int:
        """Settle the reservations whose run lost its claim, oldest first.

        Each is settled at its known spend, as uncertain when part of it was issued to
        a call; rows another worker holds are skipped.

        Args:
            now: The current instant.
            limit: How many reservations this pass may settle (1 to 100).

        Returns:
            The number of reservations recovered.

        Raises:
            ValueError: The batch size is outside 1..100.
        """
        if not 1 <= limit <= 100:
            raise ValueError("reservation recovery batch outside 1..100")
        row = DiscussionSpendReservation
        preference = DiscussionPreference
        rows = (
            await self.db.scalars(
                select(row)
                .outerjoin(preference, preference.user_id == row.user_id)
                .where(
                    row.state == "held",
                    or_(
                        preference.id.is_(None),
                        preference.active_run_id.is_distinct_from(row.run_id),
                        preference.lease_until <= now,
                    ),
                )
                .order_by(row.created_at, row.id)
                .limit(limit)
                .with_for_update(of=row, skip_locked=True)
            )
        ).all()
        for reservation in rows:
            await self.settle(
                reservation.user_id,
                reservation.run_id,
                actual=reservation.actual_usd,
                uncertain=reservation.issued_usd > 0,
            )
        return len(rows)


def _room(bucket: DiscussionBudgetBucket, limits: BudgetLimits) -> Decimal:
    """What a bucket's ceiling still leaves today, never negative."""
    ceiling = limits.instance_daily if bucket.scope_key == "instance" else limits.owner_daily
    return max(Decimal(0), ceiling - bucket.spent_usd - bucket.held_usd)


def _can_start(room: Decimal, minimum: Decimal) -> bool:
    """The one rule, for the reservation and the settings alike: room for the first call."""
    return room > 0 and room >= minimum
