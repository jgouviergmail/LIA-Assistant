"""Repository for product outcomes and events (ADR-178).

All state transitions are single atomic UPDATEs (never SELECT → mutate →
flush), and the one-outcome-per-run invariant is enforced by the unique
``run_id`` constraint + UPSERT (pattern: ``ChatRepository.create_or_update_
token_summary``). Aggregate queries feed the DB-backed Prometheus gauges —
the exact/deduplicated product truth stays in SQL (North Star is never
derived from Prometheus counters).
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import Select, delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.chat.models import MessageTokenSummary
from src.domains.product.constants import ProductEventType
from src.domains.product.models import ProductEvent, ProductOutcome
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

#: Result types eligible for behavioral E2 validation (approved action kept
#: without correction/reversion for the full window — spec §4 counting rules).
_E2_ELIGIBLE_RESULT_TYPES = ("action", "automation_run")


class ProductRepository:
    """Data access for ``product_outcomes`` / ``product_events``."""

    def __init__(self, db: AsyncSession) -> None:
        """Store the session (one repository per unit of work).

        Args:
            db: Async SQLAlchemy session owned by the caller.
        """
        self.db = db

    # ------------------------------------------------------------------
    # Writes (atomic)
    # ------------------------------------------------------------------

    async def upsert_produced(
        self,
        *,
        user_id: UUID,
        run_id: str,
        result_type: str,
        domain: str,
        execution_mode: str,
        channel: str,
        device_class: str,
        locale: str,
        latency_ms: int | None,
        turn_count: int | None,
        app_version: str | None,
    ) -> None:
        """Record a produced outcome, idempotently per run.

        A HITL-resumed run finalizes twice with the same ``run_id``: the
        second pass refreshes the volatile fields but NEVER downgrades a
        state/evidence already advanced by validation.

        Args:
            user_id: Owner of the run.
            run_id: Unique run identifier.
            result_type: Bounded ``RESULT_TYPES`` value.
            domain: Bounded domain or ``unknown``.
            execution_mode: ``pipeline`` | ``react``.
            channel: Bounded ``CHANNELS`` value.
            device_class: Bounded ``DEVICE_CLASSES`` value.
            locale: Backend-canonical language code.
            latency_ms: Request-to-presentation latency, if measured.
            turn_count: Turns consumed, if known.
            app_version: Backend version string, if known.
        """
        now = datetime.now(UTC)
        stmt = (
            pg_insert(ProductOutcome)
            .values(
                user_id=user_id,
                run_id=run_id,
                result_type=result_type,
                domain=domain,
                execution_mode=execution_mode,
                channel=channel,
                device_class=device_class,
                locale=locale,
                state="produced",
                evidence_level="E3",
                produced_at=now,
                latency_ms=latency_ms,
                turn_count=turn_count,
                app_version=app_version,
            )
            .on_conflict_do_update(
                constraint="product_outcomes_run_id_key",
                set_={
                    "result_type": result_type,
                    "domain": domain,
                    "execution_mode": execution_mode,
                    "latency_ms": latency_ms,
                    "turn_count": turn_count,
                    "updated_at": now,
                },
                where=(ProductOutcome.__table__.c.state == "produced"),
            )
        )
        await self.db.execute(stmt)

    async def apply_feedback(
        self, *, user_id: UUID, run_id: str, verdict: str
    ) -> list[tuple[str, str]]:
        """Apply an explicit user verdict to the run's outcome (E1 path).

        Args:
            user_id: Feedback author (ownership filter).
            run_id: Run whose outcome is judged.
            verdict: ``thumbs_up`` | ``thumbs_down``.

        Returns:
            ``(result_type, domain)`` for each row that actually
            TRANSITIONED (used for exact counter increments) — empty when
            the verdict was a no-op re-affirmation.
        """
        now = datetime.now(UTC)
        if verdict == "thumbs_up":
            stmt = (
                update(ProductOutcome)
                .where(
                    ProductOutcome.user_id == user_id,
                    ProductOutcome.run_id == run_id,
                    ProductOutcome.evidence_level != "E1",
                )
                .values(
                    state="validated",
                    evidence_level="E1",
                    validated_at=func.coalesce(ProductOutcome.validated_at, now),
                    updated_at=now,
                )
                .returning(ProductOutcome.result_type, ProductOutcome.domain)
            )
        else:
            # Explicit negative signal: the result leaves the useful set and
            # counts as a correction (v1 approximation, program spec).
            stmt = (
                update(ProductOutcome)
                .where(
                    ProductOutcome.user_id == user_id,
                    ProductOutcome.run_id == run_id,
                    ProductOutcome.state != "rejected",
                )
                .values(state="rejected", corrected=True, updated_at=now)
                .returning(ProductOutcome.result_type, ProductOutcome.domain)
            )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.fetchall()]

    async def upgrade_e2_candidates(self, window_hours: int) -> list[tuple[str, str]]:
        """Promote uncorrected action outcomes older than the window to E2.

        Spec §4: an E2 action requires technical success AND the absence of
        correction/reversion during the full validation window.

        Args:
            window_hours: Behavioral validation window (settings-driven).

        Returns:
            ``(result_type, domain)`` per promoted row (counter increments).
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=window_hours)
        stmt = (
            update(ProductOutcome)
            .where(
                ProductOutcome.state == "produced",
                ProductOutcome.result_type.in_(_E2_ELIGIBLE_RESULT_TYPES),
                ProductOutcome.produced_at < cutoff,
                ProductOutcome.corrected.is_(False),
                ProductOutcome.reverted.is_(False),
            )
            .values(state="validated", evidence_level="E2", validated_at=now, updated_at=now)
            .returning(ProductOutcome.result_type, ProductOutcome.domain)
        )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.fetchall()]

    async def backfill_costs(self) -> int:
        """Fill ``cost_eur`` from ``message_token_summary`` (EUR-only contract).

        Returns:
            Number of outcomes backfilled.
        """
        total_expr = (
            MessageTokenSummary.total_cost_eur
            + MessageTokenSummary.google_api_cost_eur
            + MessageTokenSummary.image_generation_cost_eur
        )
        cost_subq = (
            select(total_expr)
            .where(MessageTokenSummary.run_id == ProductOutcome.run_id)
            .scalar_subquery()
        )
        stmt = (
            update(ProductOutcome)
            .where(
                ProductOutcome.cost_eur.is_(None),
                exists(select(1).where(MessageTokenSummary.run_id == ProductOutcome.run_id)),
            )
            .values(cost_eur=cost_subq)
        )
        result = await self.db.execute(stmt)
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def purge_older_than(self, retention_days: int) -> tuple[int, int]:
        """Delete raw rows past retention (decision #6: 180 d, env-driven).

        Args:
            retention_days: Raw retention in days (settings, never hardcoded).

        Returns:
            ``(outcomes_deleted, events_deleted)``.
        """
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        outcomes = await self.db.execute(
            delete(ProductOutcome).where(ProductOutcome.produced_at < cutoff)
        )
        events = await self.db.execute(
            delete(ProductEvent).where(ProductEvent.occurred_at < cutoff)
        )
        outcomes_deleted = int(outcomes.rowcount or 0)  # type: ignore[attr-defined]
        events_deleted = int(events.rowcount or 0)  # type: ignore[attr-defined]
        return outcomes_deleted, events_deleted

    async def record_event(
        self,
        *,
        user_id: UUID | None,
        event_type: ProductEventType,
        run_id: str | None,
        channel: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append a bounded lifecycle event.

        Args:
            user_id: Owner, or None for anonymous pre-signup client events
                (arbitration a — counts only, no identifier stored).
            event_type: Bounded ``ProductEventType``.
            run_id: Related run, when run-scoped.
            channel: Bounded ``CHANNELS`` value.
            payload: Small bounded payload (never free text / PII).
        """
        self.db.add(
            ProductEvent(
                user_id=user_id,
                run_id=run_id,
                event_type=event_type.value,
                channel=channel,
                occurred_at=datetime.now(UTC),
                payload=payload,
            )
        )

    # ------------------------------------------------------------------
    # Aggregates (DB-backed gauges — exact SQL truth)
    # ------------------------------------------------------------------

    @staticmethod
    def _validated_in_window(cutoff: datetime) -> Select[tuple[UUID]]:
        """Selectable of distinct users with a validated outcome since cutoff."""
        return (
            select(ProductOutcome.user_id)
            .where(
                ProductOutcome.state == "validated",
                ProductOutcome.validated_at >= cutoff,
            )
            .distinct()
        )

    async def count_useful_users(self, window_days: int, evidence: str) -> int:
        """Distinct users with >=1 validated outcome in the window (NS-01).

        Args:
            window_days: Rolling window size.
            evidence: ``any`` | ``E1`` | ``E2``.

        Returns:
            Exact deduplicated user count.
        """
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        stmt = select(func.count(func.distinct(ProductOutcome.user_id))).where(
            ProductOutcome.state == "validated",
            ProductOutcome.validated_at >= cutoff,
        )
        if evidence != "any":
            stmt = stmt.where(ProductOutcome.evidence_level == evidence)
        return int(await self.db.scalar(stmt) or 0)

    async def personal_results(self, *, user_id: UUID, since: datetime) -> dict[str, int]:
        """What this account ACHIEVED over its billing cycle.

        The dashboard led with messages, tokens and cost — administration
        figures that say how much was spent and never what came of it. These
        three say the latter, and each counts its own kind: a validated ANSWER
        is not a successful ACTION.

        Only ``validated`` rows are counted. ``produced`` means the result was
        presented (E3), which is not the same as confirmed useful (E1 by the
        reader's thumb, E2 by an uncorrected validation window).

        Exact aggregates over the whole set — never the length of a page
        (ADR-185): a figure shown to the user is a claim.

        Args:
            user_id: Owner (every query is scoped to it).
            since: Start of the billing cycle (UTC).

        Returns:
            ``useful_results`` (every kind), ``actions``, ``automations``.
        """
        # ONE pass, three columns. Three separate counts would each see their
        # own READ COMMITTED snapshot, and `actions` is a SUBSET of
        # `useful_results`: a row landing between two reads would show the
        # reader more actions than results — not a smaller truth, an
        # impossible one. The window and the state are applied once, so the
        # three figures cannot describe different populations either.
        useful, actions, automations = (
            await self.db.execute(
                select(
                    func.count(),
                    func.count().filter(ProductOutcome.result_type == "action"),
                    func.count().filter(ProductOutcome.result_type == "automation_run"),
                ).where(
                    ProductOutcome.user_id == user_id,
                    ProductOutcome.state == "validated",
                    ProductOutcome.produced_at >= since,
                )
            )
        ).one()
        return {
            "useful_results": int(useful or 0),
            "actions": int(actions or 0),
            "automations": int(automations or 0),
        }

    async def penetration_by_device(self, window_days: int) -> dict[str, float]:
        """Useful users / engaged users, overall and per device class (NS-02).

        v1 engaged denominator: distinct users with >=1 produced outcome in
        the window (documented approximation — routine/proactive engagement
        joins in a later lot).

        Args:
            window_days: Rolling window size.

        Returns:
            ``{"all": ratio, "<device_class>": ratio, ...}`` — only entries
            whose denominator is > 0.
        """
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        produced = (
            select(
                ProductOutcome.device_class.label("device_class"),
                func.count(func.distinct(ProductOutcome.user_id)).label("engaged"),
            )
            .where(ProductOutcome.produced_at >= cutoff)
            .group_by(ProductOutcome.device_class)
        )
        validated = (
            select(
                ProductOutcome.device_class.label("device_class"),
                func.count(func.distinct(ProductOutcome.user_id)).label("useful"),
            )
            .where(
                ProductOutcome.state == "validated",
                ProductOutcome.validated_at >= cutoff,
            )
            .group_by(ProductOutcome.device_class)
        )
        engaged_rows = {r.device_class: int(r.engaged) for r in await self.db.execute(produced)}
        useful_rows = {r.device_class: int(r.useful) for r in await self.db.execute(validated)}

        ratios: dict[str, float] = {}
        total_engaged = sum(engaged_rows.values())
        if total_engaged > 0:
            ratios["all"] = sum(useful_rows.values()) / total_engaged
        for device, engaged in engaged_rows.items():
            if engaged > 0:
                ratios[device] = useful_rows.get(device, 0) / engaged
        return ratios

    async def activation_rate(self, window_days: int, first_value_days: int = 7) -> float | None:
        """Signup-cohort activation (ACT-02).

        Args:
            window_days: Signup cohort window.
            first_value_days: Max days from signup to first validated outcome.

        Returns:
            Activated / registered for the cohort, or None when empty.
        """
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        registered = int(
            await self.db.scalar(
                select(func.count()).select_from(User).where(User.created_at >= cutoff)
            )
            or 0
        )
        if registered == 0:
            return None
        activated = int(
            await self.db.scalar(
                select(func.count(func.distinct(ProductOutcome.user_id)))
                .select_from(ProductOutcome)
                .join(User, User.id == ProductOutcome.user_id)
                .where(
                    User.created_at >= cutoff,
                    ProductOutcome.state == "validated",
                    ProductOutcome.validated_at
                    <= User.created_at + timedelta(days=first_value_days),
                )
            )
            or 0
        )
        return activated / registered

    async def retention_rate(self, period_days: int) -> float | None:
        """Rolling useful-retention (RET proxy, documented in the dictionary).

        Users validated in the PREVIOUS period who validated again in the
        CURRENT period, over the previous-period users. Exact signup-cohort
        curves ship with the PostgreSQL datasource (Phase 3).

        Args:
            period_days: 1, 7 or 30.

        Returns:
            Return ratio, or None when the previous period is empty.
        """
        now = datetime.now(UTC)
        curr_cutoff = now - timedelta(days=period_days)
        prev_cutoff = now - timedelta(days=2 * period_days)
        prev_users = (
            select(ProductOutcome.user_id)
            .where(
                ProductOutcome.state == "validated",
                ProductOutcome.validated_at >= prev_cutoff,
                ProductOutcome.validated_at < curr_cutoff,
            )
            .distinct()
            .subquery()
        )
        prev_count = int(await self.db.scalar(select(func.count()).select_from(prev_users)) or 0)
        if prev_count == 0:
            return None
        returned = int(
            await self.db.scalar(
                select(func.count(func.distinct(ProductOutcome.user_id))).where(
                    ProductOutcome.state == "validated",
                    ProductOutcome.validated_at >= curr_cutoff,
                    ProductOutcome.user_id.in_(select(prev_users.c.user_id)),
                )
            )
            or 0
        )
        return returned / prev_count

    async def funnel_counts(self, window_days: int) -> dict[str, int]:
        """v1 funnel stage populations (bounded ``FUNNEL_STAGES``).

        Args:
            window_days: Rolling window size.

        Returns:
            ``{stage: distinct_users}`` for registered / technical_result /
            useful_result.
        """
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        registered = int(
            await self.db.scalar(
                select(func.count()).select_from(User).where(User.created_at >= cutoff)
            )
            or 0
        )
        technical = int(
            await self.db.scalar(
                select(func.count(func.distinct(ProductOutcome.user_id))).where(
                    ProductOutcome.produced_at >= cutoff
                )
            )
            or 0
        )
        useful = int(
            await self.db.scalar(
                select(func.count(func.distinct(ProductOutcome.user_id))).where(
                    ProductOutcome.state == "validated",
                    ProductOutcome.validated_at >= cutoff,
                )
            )
            or 0
        )
        return {
            "registered": registered,
            "technical_result": technical,
            "useful_result": useful,
        }

    async def data_quality_ratios(self, window_days: int = 30) -> dict[str, float]:
        """Bounded data-quality checks (``DATA_QUALITY_CHECKS``).

        Args:
            window_days: Inspection window.

        Returns:
            ``{check: ratio}`` — only checks whose denominator is > 0.
        """
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        outcomes_total = int(
            await self.db.scalar(
                select(func.count())
                .select_from(ProductOutcome)
                .where(ProductOutcome.produced_at >= cutoff)
            )
            or 0
        )
        ratios: dict[str, float] = {}
        if outcomes_total > 0:
            with_domain = int(
                await self.db.scalar(
                    select(func.count())
                    .select_from(ProductOutcome)
                    .where(
                        ProductOutcome.produced_at >= cutoff,
                        ProductOutcome.domain != "unknown",
                    )
                )
                or 0
            )
            with_cost = int(
                await self.db.scalar(
                    select(func.count())
                    .select_from(ProductOutcome)
                    .where(
                        ProductOutcome.produced_at >= cutoff,
                        ProductOutcome.cost_eur.is_not(None),
                    )
                )
                or 0
            )
            ratios["outcomes_with_domain"] = with_domain / outcomes_total
            ratios["outcomes_with_cost"] = with_cost / outcomes_total
        events_total = int(
            await self.db.scalar(
                select(func.count())
                .select_from(ProductEvent)
                .where(ProductEvent.occurred_at >= cutoff)
            )
            or 0
        )
        if events_total > 0:
            with_run = int(
                await self.db.scalar(
                    select(func.count())
                    .select_from(ProductEvent)
                    .where(
                        ProductEvent.occurred_at >= cutoff,
                        ProductEvent.run_id.is_not(None),
                    )
                )
                or 0
            )
            ratios["events_with_run"] = with_run / events_total
        return ratios
