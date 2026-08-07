"""Instance-wide daily spend ceiling (live-demonstrator programme, lot 1).

Per-user limits bound what ONE account consumes; they cannot bound what an
instance spends, because N accounts × their quota is unbounded. A public
demonstrator hands a fresh account to every visitor, so without this
ceiling a single scripted loop drains the budget. The same protection is
useful on a private instance: it is the switch that guarantees a bad day
costs a known amount.

Design:
- **Authority is PostgreSQL.** Recording is ONE atomic UPSERT with column
  arithmetic (imitating ``ChatRepository.create_or_update_token_summary``),
  so concurrent runs can never lose spend to a read-modify-write race.
- **The check is conservative**: reaching the ceiling is exhaustion, and an
  unknown spend (database unreachable) DENIES. The money side fails closed.
- **Recording is best effort**: it happens after the answer was served, so
  a failure there is logged, never raised.
- **Configuration may only LOWER** a deployment bound (same doctrine as the
  public-demo ceilings): the effective ceiling is the smallest configured
  value, and an absent configuration disables the feature entirely — an
  instance that never sets it behaves exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.domains.usage_limits.models import InstanceDailyBudget

logger = structlog.get_logger(__name__)

#: Cost families a run can bill. Every euro counts against the ceiling —
#: a demonstrator that only counted LLM tokens would be blind to images, and
#: speech synthesis is exactly what a visitor tries first on a public demo.
_COST_FIELDS = (
    "cost_eur",
    "google_api_cost_eur",
    "image_generation_cost_eur",
    "tts_cost_eur",
)

#: Cost keys the run summary publishes but the ceiling deliberately ignores,
#: each with the reason. Empty is the correct state: a ceiling that skips a
#: real euro is not a ceiling. It exists so the completeness guard can tell
#: "decided not to count" from "nobody noticed" — the second is how a spend
#: cap silently stops capping (measured 2026-08-06: TTS billed the owner and
#: never reached the ledger).
_EXCLUDED_COST_FIELDS: dict[str, str] = {}


def seconds_until_next_utc_day(now: datetime | None = None) -> int:
    """Seconds until the ledger rolls over, at least one.

    The ceiling resets on the UTC day boundary, so "when can I come back" is
    computable rather than a guess. Never zero: telling a client to retry
    immediately would walk it straight back into the same refusal.

    Args:
        now: Injected instant (tests); defaults to the wall clock.

    Returns:
        Whole seconds until the next UTC midnight.
    """
    current = (now or datetime.now(UTC)).astimezone(UTC)
    next_day = datetime.combine(current.date() + timedelta(days=1), time.min, tzinfo=UTC)
    return max(1, int((next_day - current).total_seconds()))


@dataclass(frozen=True)
class InstanceBudgetDecision:
    """The verdict plus what an operator (or a visitor) needs to see."""

    allowed: bool
    spent_eur: Decimal | None = None
    ceiling_eur: Decimal | None = None
    error_code: str | None = None

    @property
    def remaining_eur(self) -> Decimal | None:
        """What is left today, never negative (an overshoot reads as zero)."""
        if self.ceiling_eur is None or self.spent_eur is None:
            return None
        return max(Decimal("0"), self.ceiling_eur - self.spent_eur)


class InstanceBudgetService:
    """Stateless helpers over the durable daily ledger."""

    @staticmethod
    def resolve_ceiling(env_ceiling: Decimal | None, db_ceiling: Decimal | None) -> Decimal | None:
        """The effective ceiling: the SMALLEST configured bound, or None.

        Args:
            env_ceiling: Deployment bound (environment), or None.
            db_ceiling: Operator value (admin setting), or None.

        Returns:
            The effective ceiling, or None when the feature is disabled.
        """
        configured = [value for value in (env_ceiling, db_ceiling) if value is not None]
        return min(configured) if configured else None

    @staticmethod
    def total_cost_eur(summary: dict[str, Any]) -> Decimal:
        """Sum every billable family of one run's usage summary."""
        total = Decimal("0")
        for field in _COST_FIELDS:
            value = summary.get(field) or 0
            total += Decimal(str(value))
        return total

    @staticmethod
    async def check(
        session: Any, *, ceiling_eur: Decimal | None, now: datetime | None = None
    ) -> InstanceBudgetDecision:
        """Is the instance still allowed to spend today?

        Args:
            session: Async SQLAlchemy session.
            ceiling_eur: Effective ceiling; ``None`` disables the check.
            now: Injected UTC instant (tests); defaults to the wall clock.

        Returns:
            The decision. An unreachable database denies with
            ``instance_budget_unavailable``.
        """
        if ceiling_eur is None:
            return InstanceBudgetDecision(allowed=True)
        utc_day = (now or datetime.now(UTC)).astimezone(UTC).date()
        try:
            result = await session.execute(
                select(InstanceDailyBudget.spent_cost_eur).where(
                    InstanceDailyBudget.utc_day == utc_day
                )
            )
            spent = result.scalar_one_or_none()
        except Exception as exc:  # noqa: BLE001 — bounded: never leak SQL details
            # The error TYPE, never its message: this failure blocks the whole
            # instance, so an operator must be able to tell a database outage
            # from a mapper/config mistake — a silent fail-closed is
            # indefensible in production. The message could carry SQL and
            # values, so it stays out.
            logger.error("instance_budget_check_failed", error_type=type(exc).__name__)
            return InstanceBudgetDecision(
                allowed=False,
                ceiling_eur=ceiling_eur,
                error_code="instance_budget_unavailable",
            )
        spent_eur = Decimal(str(spent)) if spent is not None else Decimal("0")
        return InstanceBudgetDecision(
            allowed=spent_eur < ceiling_eur,
            spent_eur=spent_eur,
            ceiling_eur=ceiling_eur,
        )

    @staticmethod
    async def record_spend(session: Any, *, cost_eur: Decimal, now: datetime | None = None) -> None:
        """Add one run's cost to today's ledger (atomic, best effort).

        Args:
            session: Async SQLAlchemy session (the caller owns the commit).
            cost_eur: Positive amount; zero or negative is ignored.
            now: Injected UTC instant (tests).
        """
        if cost_eur <= 0:
            return
        utc_day = (now or datetime.now(UTC)).astimezone(UTC).date()
        statement = pg_insert(InstanceDailyBudget).values(
            utc_day=utc_day, spent_cost_eur=cost_eur, run_count=1
        )
        statement = statement.on_conflict_do_update(
            index_elements=["utc_day"],
            set_={
                "spent_cost_eur": InstanceDailyBudget.spent_cost_eur
                + statement.excluded.spent_cost_eur,
                "run_count": InstanceDailyBudget.run_count + statement.excluded.run_count,
            },
        )
        try:
            # SAVEPOINT: the caller shares this transaction with the run's
            # token summary. Swallowing a failed statement without one would
            # leave the transaction poisoned and take the caller's commit
            # down with it — losing the very accounting we came to write.
            async with session.begin_nested():
                await session.execute(statement)
        except Exception as exc:  # noqa: BLE001 — accounting never breaks a run
            # The answer is already served; losing one increment is a
            # measurement gap, not a reason to fail the visitor's request.
            # The type is logged so a systematic loss is diagnosable.
            logger.error("instance_budget_record_failed", error_type=type(exc).__name__)

    @staticmethod
    async def record_run_summary(session: Any, summary: dict[str, Any]) -> None:
        """Add one run's total cost to today's ledger, from its usage summary.

        Unconditional by design: arming this only when a ceiling is configured
        would leave a window where an administrator sets one and the counter
        stays mute, so the ceiling would never trigger. One UPSERT on one
        indexed row per run is negligible next to the token logs written
        alongside it, and the ledger doubles as "what does this instance spend
        per day".

        Never raises: the answer is already served when this runs.

        Args:
            session: The caller's session; the increment joins its transaction.
            summary: Aggregated per-run summary (see ``TrackingContext``).
        """
        try:
            cost = InstanceBudgetService.total_cost_eur(summary)
            if cost <= 0:
                return
            await InstanceBudgetService.record_spend(session, cost_eur=cost)
        except Exception as exc:  # noqa: BLE001 — accounting never breaks a run
            # Same doctrine as ``record_spend``: the TYPE, never the message.
            # A malformed summary value would otherwise reach the logs through
            # the exception text.
            logger.error("instance_spend_record_failed", error_type=type(exc).__name__)
