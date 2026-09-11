"""The sweep that turns an anticipated instant into a question (lot 1).

One tick does four things, in this order and for a reason:

1. **housekeeping** — give back the claims whose holder stopped answering,
   close the pending rows whose window has closed, then delete what has been
   settled longer than the retention. All three are bounded statements, and
   they run FIRST so a row that expired thirty seconds ago is never claimed by
   the same pass — and so a moment abandoned by a killed worker is offered
   again rather than lost, which measurement showed it was.
2. **choose the accounts** — active, heartbeat on, present recently, and
   **inside their own notification window**. That last one is not an
   optimisation: an account outside its window will not be served whatever is
   detected, so detecting for it spends a calendar read to file a row that
   expires unread.
3. **detect, then file** — each kind's detector proposes candidates and the
   repository files the ones whose identity is new.
4. **claim ONE, revalidate it, serve it, settle it** — one at a time per
   account, revalidated against its source before anything is said, and settled
   from an EXPLICIT result. Never from the absence of an exception.

**What a moment bypasses, and what it does not.** It is served through the same
``ProactiveTaskRunner`` as a push wake, with ``skip_probabilistic_gate=True``:
the « guaranteed minimum » smoothing exists to spread a day's quota over a
window, and a moment answers an instant. Everything else holds — notification
window, daily quota, global cooldown, cross-type cooldown, activity cooldown —
so a moment changes WHEN a decision is taken, never how many may fire.

The capability is read at CALL time, not at boot: an operator switching moments
off must be obeyed without a restart.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

import structlog
from sqlalchemy import func, select

from src.core.config import settings
from src.core.constants import (
    HEARTBEAT_NOTIFY_END_HOUR_DEFAULT,
    HEARTBEAT_NOTIFY_START_HOUR_DEFAULT,
    SCHEDULER_JOB_MOMENT_SWEEP,
)
from src.core.time_utils import resolve_user_timezone
from src.domains.feature_switches.registry import (
    PlatformCapability,
    is_capability_enabled,
)
from src.domains.moments.kinds import MOMENT_KIND_SPECS
from src.domains.moments.models import MomentKind, MomentSkipReason, MomentState
from src.domains.moments.preferences import is_kind_enabled
from src.domains.moments.repository import MomentRepository
from src.domains.moments.schemas import ServedMoment
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.locks.scheduler_lock import ttl_for_interval
from src.infrastructure.observability.metrics_moments import (
    proactive_moment_latency_seconds,
    proactive_moments_total,
)
from src.infrastructure.proactive.eligibility import is_within_hour_window

logger = structlog.get_logger(__name__)

#: The surface name this sweep records its reads under.
CONSULTATION_SURFACE = "moment"


async def _housekeeping(now: datetime) -> tuple[int, int, int]:
    """Give back dead claims, close what missed its window, delete the rest.

    The order is the whole point. A claim whose holder stopped answering is
    reachable by NOTHING else in the repository — expiry reads pending rows,
    the purge reads settled ones, a new claim reads pending — so it must be
    handed back FIRST; a row whose window has also closed is then expired by
    the very next statement, in this same pass.

    Returns:
        (reclaimed, expired, purged).
    """
    async with get_db_context() as db:
        repo = MomentRepository(db)
        reclaimed = await repo.reclaim_stale(
            now=now,
            older_than=timedelta(minutes=settings.moments_claim_lease_minutes),
        )
        expired = await repo.expire_stale(now=now)
        purged = await repo.purge_settled(
            before=now - timedelta(days=settings.moments_retention_days)
        )
        await db.commit()
    for kind in expired:
        proactive_moments_total.labels(kind=kind, outcome="expired").inc()
    return reclaimed, len(expired), purged


async def _eligible_accounts(now: datetime) -> list[Any]:
    """The accounts worth a pass right now.

    The hour window is filtered in PYTHON, never in SQL: it depends on each
    person's own timezone, and a single corrupted zone in a SQL predicate takes
    the whole batch down (ADR-232's measured trap).

    Args:
        now: The instant the pass runs at.

    Returns:
        Account rows, at most ``moments_sweep_batch_size``.
    """
    from src.domains.habits.presence import last_seen_at
    from src.domains.users.models import User

    async with get_db_context() as db:
        rows = (
            (
                await db.execute(
                    select(User)
                    .where(
                        User.is_active.is_(True),
                        User.heartbeat_enabled.is_(True),
                    )
                    .order_by(func.random())
                    .limit(settings.moments_sweep_batch_size)
                )
            )
            .scalars()
            .all()
        )

        eligible: list[Any] = []
        for user in rows:
            user_now = now.astimezone(resolve_user_timezone(user))
            # The columns are NOT NULL, so the fallbacks only ever serve a
            # duck-typed row — and they are the model's OWN constants, never a
            # second pair of magic numbers to drift from it.
            if not is_within_hour_window(
                user_now.hour,
                getattr(user, "heartbeat_notify_start_hour", HEARTBEAT_NOTIFY_START_HOUR_DEFAULT),
                getattr(user, "heartbeat_notify_end_hour", HEARTBEAT_NOTIFY_END_HOUR_DEFAULT),
            ):
                continue
            seen = await last_seen_at(user)
            if seen is not None:
                idle_days = (now - seen).days
                if idle_days > settings.heartbeat_inactive_skip_days:
                    continue
            eligible.append(user)
    return eligible


async def _detect_for(user: Any, now: datetime) -> int:
    """Run every kind's detector for one account and file what is new.

    Args:
        user: The account row.
        now: The instant the pass runs at.

    Returns:
        How many moments were really filed.
    """
    started = perf_counter()
    opened: list[str] = []
    failed: list[str] = []
    candidates = []
    for kind, spec in MOMENT_KIND_SPECS.items():
        # A refused kind is not even looked at: running its detector would
        # spend a calendar read to file a row nothing will ever serve, and the
        # register would claim a source LIA opened for no reason.
        if not is_kind_enabled(user, kind.value):
            continue
        try:
            found = await spec.detector(user, now)
        except Exception as exc:  # noqa: BLE001 — one kind must not kill the pass
            failed.append(kind.value)
            logger.warning(
                "moment_detector_failed",
                kind=kind.value,
                user_id=str(user.id),
                error_type=type(exc).__name__,
            )
            continue
        opened.append(kind.value)
        candidates.extend(found)

    filed: list[str] = []
    if candidates:
        async with get_db_context() as db:
            filed = await MomentRepository(db).insert_candidates(candidates)
            await db.commit()
        for filed_kind in filed:
            proactive_moments_total.labels(kind=filed_kind, outcome="detected").inc()

    # Every detector above opened one of the person's sources, on LIA's own
    # initiative and while nobody was watching.
    record_surface_consultations(
        surface=CONSULTATION_SURFACE,
        user_id=user.id,
        opened=opened,
        failed=failed,
        duration_ms=int((perf_counter() - started) * 1000),
    )
    return len(filed)


async def _serve(
    served: ServedMoment, user_id: uuid.UUID
) -> tuple[MomentState, MomentSkipReason | None]:
    """Put the moment in front of the heartbeat decision, under every gate.

    Returns:
        The settled state, and the bounded reason when it is a skip.
    """
    from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
    from src.infrastructure.proactive.runner import execute_proactive_task
    from src.infrastructure.scheduler.heartbeat_notification import (
        _create_heartbeat_eligibility_checker,
    )

    stats = await execute_proactive_task(
        task=HeartbeatProactiveTask(moment=served),
        eligibility_checker=_create_heartbeat_eligibility_checker(),
        batch_size=1,
        user_ids=[user_id],
        skip_probabilistic_gate=True,
    )
    if stats.success > 0:
        return MomentState.SERVED, None
    if stats.skip_reasons.get("usage_limit_exceeded"):
        # A ceiling refused the call: nothing was generated and nothing went
        # wrong (ADR-272). It is a skip, never a failure.
        return MomentState.SKIPPED, MomentSkipReason.QUOTA
    if stats.skip_reasons.get("no_target"):
        return MomentState.SKIPPED, MomentSkipReason.LLM_SKIP
    if stats.failed:
        return MomentState.SKIPPED, MomentSkipReason.DISPATCH_FAILED
    return MomentState.SKIPPED, MomentSkipReason.NOT_ELIGIBLE


async def _decide(
    user: Any,
    kind: str,
    source_ref: str,
    payload: dict[str, Any],
) -> tuple[MomentState, MomentSkipReason | None]:
    """Re-read the fact, then either say something or explain the silence.

    Split out of :func:`_serve_one` so the claim/settle bookkeeping and the
    decision stay separately readable — and so neither grows the other's
    cyclomatic complexity.

    Args:
        user: The account row.
        kind: The moment's kind value, as stored.
        source_ref: What the moment is about, in the source's vocabulary.
        payload: What the detector filed.

    Returns:
        The settled state, and the bounded reason when it is a skip.
    """
    if not is_kind_enabled(user, kind):
        # Filed before the refusal, claimed after it. The person changed their
        # mind, which is not a failure: the row is closed, not skipped.
        logger.info("moment_kind_refused", kind=kind, user_id=str(user.id))
        return MomentState.CANCELLED, None

    try:
        spec = MOMENT_KIND_SPECS[MomentKind(kind)]
    except KeyError, ValueError:
        # A kind this build no longer knows — a row filed before a downgrade.
        # Closed rather than left claimed for ever, and never served blind.
        logger.warning("moment_kind_unknown", kind=kind, user_id=str(user.id))
        return MomentState.CANCELLED, None

    try:
        facts = await spec.revalidator(user, source_ref, payload)
    except Exception as exc:  # noqa: BLE001 — a failed re-read says nothing
        logger.warning(
            "moment_revalidation_failed",
            kind=kind,
            user_id=str(user.id),
            error_type=type(exc).__name__,
        )
        return MomentState.SKIPPED, MomentSkipReason.REVALIDATION_FAILED

    if not facts.still_valid:
        return MomentState.CANCELLED, None

    return await _serve(
        ServedMoment(kind=kind, headline=spec.headline, lines=facts.lines),
        uuid.UUID(str(user.id)),
    )


async def _serve_one(user: Any, now: datetime) -> str:
    """Claim the account's oldest due moment and take it to a settled state.

    Returns:
        A bounded outcome name for the metric, or ``"none"`` when nothing was
        due for this account.
    """
    user_id = uuid.UUID(str(user.id))
    owner = uuid.uuid4().hex
    async with get_db_context() as db:
        moment = await MomentRepository(db).claim_due(user_id=user_id, now=now, owner=owner)
        await db.commit()
        if moment is None:
            return "none"
        # Copied out of the row rather than carried on it: the session closes
        # below, and a lazily-loaded attribute after that is a MissingGreenlet.
        moment_id = uuid.UUID(str(moment.id))
        kind = str(moment.kind)
        source_ref = str(moment.source_ref)
        payload = dict(moment.payload or {})
        due_at = moment.due_at

    state, reason = await _decide(user, kind, source_ref, payload)

    async with get_db_context() as db:
        await MomentRepository(db).settle(
            moment_id,
            owner=owner,
            state=state,
            skip_reason=reason,
            now=datetime.now(UTC),
        )
        await db.commit()

    outcome = state.value if reason is None else f"skipped_{reason.value}"
    proactive_moments_total.labels(kind=kind, outcome=outcome).inc()
    if state is MomentState.SERVED:
        proactive_moment_latency_seconds.observe(
            max((datetime.now(UTC) - due_at).total_seconds(), 0.0)
        )
    return outcome


def _lock_ttl() -> int:
    """How long the sweep's lock outlives its holder — the shared rule."""
    return ttl_for_interval(settings.moments_sweep_interval_minutes * 60)


async def run_moment_sweep() -> dict[str, Any]:
    """One pass of the moment sweep. Never raises.

    Returns:
        A small dict of counters, for the scheduler's structured log.
    """
    if not await is_capability_enabled(PlatformCapability.MOMENTS):
        return {"skipped": "capability_off"}
    # A moment is served by the heartbeat task: the heartbeat's own switch
    # governs it too (ADR-280 amendment 2026-09-11).
    if not await is_capability_enabled(PlatformCapability.HEARTBEAT):
        return {"skipped": "heartbeat_capability_off"}

    redis = await get_redis_cache()
    # The lock is deliberately NOT released on exit — it expires by TTL, so
    # that N workers cannot re-run the same job inside one interval. Its
    # default TTL is five minutes, which is also this sweep's default
    # interval: left at the default, one tick in two would find the previous
    # tick's lock still alive and skip. The TTL is therefore tied to the
    # interval and kept just under it.
    async with SchedulerLock(redis, SCHEDULER_JOB_MOMENT_SWEEP, ttl_seconds=_lock_ttl()) as lock:
        if not lock.acquired:
            return {"lock_busy": 1}

        now = datetime.now(UTC)
        reclaimed, expired, purged = await _housekeeping(now)
        accounts = await _eligible_accounts(now)

        filed = 0
        outcomes: dict[str, int] = {}
        for user in accounts:
            try:
                filed += await _detect_for(user, now)
                outcome = await _serve_one(user, now)
            except Exception as exc:  # noqa: BLE001 — one account, never the sweep
                outcome = "error"
                logger.warning(
                    "moment_sweep_account_failed",
                    user_id=str(user.id),
                    error_type=type(exc).__name__,
                )
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

        # The per-account outcomes are nested rather than merged: a future
        # settled state named like one of the housekeeping counters would have
        # silently overwritten it in the log.
        result = {
            "accounts": len(accounts),
            "filed": filed,
            "reclaimed": reclaimed,
            "expired": expired,
            "purged": purged,
            "outcomes": outcomes,
        }
        logger.info("moment_sweep_completed", **result)
        return result
