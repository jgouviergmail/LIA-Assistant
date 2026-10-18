"""Leader-elected self-check tick (spec 2026-08-27, pillar 2).

One tick: run the engine, persist the snapshot, prune retention, stamp the
liveness tick. The tick key is stamped ONLY on full success so a failing loop
trips the staleness check instead of hiding behind a partial pass
(product_rollup doctrine). The tick also synchronises incidents from the
snapshot verdicts, closes the alert incidents whose resolution was lost
(Alertmanager read before the transaction opens), and pumps the budgeted LLM
diagnosis (best-effort) once its session is closed: no network wait — the
Alertmanager read, the evidence pack, the model — runs inside a transaction of
the tick (ADR-304).
"""

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_DIAGNOSTICS_SCHEDULER_TICK,
    SCHEDULER_JOB_ID_DIAGNOSTICS_SELF_CHECK,
)
from src.domains.diagnostics.diagnosis import diagnose_incidents
from src.domains.diagnostics.engine import run_self_check
from src.domains.diagnostics.incident_sync import (
    reconcile_alert_incidents,
    sync_incidents_from_results,
)
from src.domains.diagnostics.notifications import notify_admins_of_incident
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.telemetry.alertmanager import AlertmanagerClient
from src.infrastructure.telemetry.models import AlertsResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.diagnostics.models import Incident

logger = structlog.get_logger(__name__)


async def _read_alertmanager() -> tuple[AlertsResult, datetime | None]:
    """What Alertmanager holds as firing, and when the instance that answered started.

    Read before the tick's session opens (ADR-304), the listing first: an
    instance that restarts between the two reads reports its NEW start, so the
    reconciliation waits instead of trusting a listing it cannot date. Any
    failure is an unreadable Alertmanager, never a lost tick: the client turns
    transport faults into a typed result, but a malformed URL raises
    ``httpx.InvalidURL`` — no ``httpx.HTTPError`` — and it used to kill every
    tick before the snapshot was saved.

    Returns:
        The firing alerts (suppressed ones included) and the instance's start;
        an ``unavailable`` listing and None when anything failed.
    """
    try:
        client = AlertmanagerClient(
            base_url=settings.diagnostics_alertmanager_url,
            timeout_seconds=settings.diagnostics_http_timeout_seconds,
        )
        firing = await client.active_alerts(include_suppressed=True)
        if firing.status != "ok":
            return firing, None
        started = await client.status()
    except Exception as exc:
        logger.warning("diagnostics_alertmanager_read_failed", error_type=type(exc).__name__)
        return AlertsResult(status="unavailable", error=type(exc).__name__), None
    return firing, started.started_at


async def _reconcile_lost_resolutions(
    db: AsyncSession,
    repo: DiagnosticsRepository,
    firing: AlertsResult,
    alertmanager_started_at: datetime | None,
) -> list[str]:
    """Close the alert incidents whose resolution was lost, under a SAVEPOINT.

    Maintenance, not the tick's purpose: a failure here costs the tick this
    pass only — never the snapshot, the incident sync or the liveness stamp
    (measured on dev 2026-10-18: an unbindable statement failed the whole
    tick before it was fixed).

    Args:
        db: The tick's session.
        repo: Repository bound to it.
        firing: Alertmanager's firing alerts, read before the session opened.
        alertmanager_started_at: When that Alertmanager started (None: unknown).

    Returns:
        The correlation keys resolved; none on failure.
    """
    try:
        async with db.begin_nested():
            return await reconcile_alert_incidents(
                repo,
                firing,
                alertmanager_started_at=alertmanager_started_at,
                now=datetime.now(UTC),
                silence_close_seconds=settings.diagnostics_incident_silence_close_seconds,
            )
    except Exception:
        logger.exception("diagnostics_incident_reconciliation_failed")
        return []


async def _incidents_to_diagnose(repo: DiagnosticsRepository) -> list[Incident]:
    """The open incidents the diagnosis pump takes this tick (best-effort read)."""
    try:
        return await repo.incidents_needing_diagnosis(settings.diagnostics_diagnosis_batch_size)
    except Exception:
        logger.exception("diagnostics_diagnosis_pump_failed")
        return []


async def _pump_diagnoses(pending: list[Incident]) -> int:
    """Diagnose the pending incidents (spec pillar 4): pull-based, budget-capped, best-effort.

    Called once the tick's session is closed: the pump waits on Prometheus, Loki
    and the model, and opens short sessions of its own for what it reads and
    stores. A broken LLM must not break the health tick.

    Args:
        pending: Incidents read by the tick, their session already closed.

    Returns:
        How many diagnoses were stored; 0 when the pump failed.
    """
    if not pending:
        return 0
    try:
        from src.domains.agents.prompts.prompt_loader import load_prompt

        # `{language}` is left UNRESOLVED on purpose: the batch writes one
        # variant per admin language and fills it there.
        system_prompt = str(load_prompt("diagnostician_prompt")).replace(
            "{max_actions}", str(settings.diagnostics_diagnosis_max_actions)
        )
        return await diagnose_incidents(pending, system_prompt=system_prompt)
    except Exception:
        logger.exception("diagnostics_diagnosis_pump_failed")
        return 0


async def run_diagnostics_self_check() -> None:
    """Execute one self-check tick (engine → persist → prune → tick stamp)."""
    if not getattr(settings, "diagnostics_enabled", False):
        return

    from src.infrastructure.observability.metrics import background_job_errors_total
    from src.infrastructure.observability.metrics_diagnostics import (
        diagnostics_checks_total,
        diagnostics_self_check_duration_seconds,
    )

    started = time.monotonic()
    try:
        snapshot = await run_self_check()
        for result in snapshot.results:
            diagnostics_checks_total.labels(
                check_id=result.check_id, status=result.status.value
            ).inc()
        # Read BEFORE the session opens: a network wait never holds a
        # transaction (ADR-304). Suppressed alerts are still firing.
        firing, alertmanager_started_at = await _read_alertmanager()

        async with get_db_context() as db:
            repo = DiagnosticsRepository(db)
            await repo.save_snapshot(
                taken_at=snapshot.taken_at,
                overall=snapshot.overall.value,
                results=snapshot.to_results_jsonb(),
            )
            pruned = await repo.prune_snapshots(settings.diagnostics_snapshot_retention_days)
            sync_outcome = await sync_incidents_from_results(repo, snapshot.results)
            reconciled = await _reconcile_lost_resolutions(
                db, repo, firing, alertmanager_started_at
            )
            await db.commit()

            # Counters AFTER the commit (product_rollup doctrine: an aborted
            # transaction must not leave phantom increments), notifications
            # only for incidents THIS tick opened — a touch never re-pushes.
            from src.infrastructure.observability.metrics_diagnostics import (
                diagnostics_incidents_total,
            )

            for incident_id, correlation_key in zip(
                sync_outcome.opened_ids, sync_outcome.opened_keys, strict=True
            ):
                diagnostics_incidents_total.labels(source="self_check", severity="critical").inc()
                try:
                    await notify_admins_of_incident(
                        incident_id=incident_id,
                        correlation_key=correlation_key,
                        severity="critical",
                        title=f"Self-check critical: {correlation_key}",
                        db=db,
                    )
                except Exception:
                    logger.exception(
                        "diagnostics_self_check_notify_failed",
                        correlation_key=correlation_key,
                    )
            if sync_outcome.opened_ids:
                await db.commit()

            pending = await _incidents_to_diagnose(repo)

        # The session is closed (its exit committed the read above): the pump
        # waits on Prometheus, Loki and the model with no transaction open.
        diagnosed = await _pump_diagnoses(pending)

        # Stamped only after the whole tick succeeded: the liveness probe must
        # see a FAILING loop as stale, not as alive-but-unlucky. TTL bounds
        # stale keys after the feature is switched off.
        redis = await get_redis_cache()
        await redis.set(
            REDIS_KEY_DIAGNOSTICS_SCHEDULER_TICK,
            str(time.time()),
            ex=settings.diagnostics_check_scheduler_tick_stale_seconds * 4,
        )

        logger.info(
            "diagnostics_self_check_completed",
            overall=snapshot.overall.value,
            checks=len(snapshot.results),
            snapshots_pruned=pruned,
            alert_incidents_reconciled=len(reconciled),
            alertmanager=firing.status,
            diagnoses_stored=diagnosed,
            duration_seconds=round(time.monotonic() - started, 3),
        )
    except Exception:
        background_job_errors_total.labels(job_name=SCHEDULER_JOB_ID_DIAGNOSTICS_SELF_CHECK).inc()
        logger.exception("diagnostics_self_check_failed")
    finally:
        diagnostics_self_check_duration_seconds.observe(time.monotonic() - started)
