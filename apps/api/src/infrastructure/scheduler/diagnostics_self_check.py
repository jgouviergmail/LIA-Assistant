"""Leader-elected self-check tick (spec 2026-08-27, pillar 2).

One tick: run the engine, persist the snapshot, prune retention, stamp the
liveness tick. The tick key is stamped ONLY on full success so a failing loop
trips the staleness check instead of hiding behind a partial pass
(product_rollup doctrine). The tick also synchronises incidents from the
snapshot verdicts and pumps the budgeted LLM diagnosis (both best-effort).
"""

import time

import structlog

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_DIAGNOSTICS_SCHEDULER_TICK,
    SCHEDULER_JOB_ID_DIAGNOSTICS_SELF_CHECK,
)
from src.domains.diagnostics.diagnosis import diagnose_incidents
from src.domains.diagnostics.engine import run_self_check
from src.domains.diagnostics.incident_sync import sync_incidents_from_results
from src.domains.diagnostics.notifications import notify_admins_of_incident
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


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

        async with get_db_context() as db:
            repo = DiagnosticsRepository(db)
            await repo.save_snapshot(
                taken_at=snapshot.taken_at,
                overall=snapshot.overall.value,
                results=snapshot.to_results_jsonb(),
            )
            pruned = await repo.prune_snapshots(settings.diagnostics_snapshot_retention_days)
            sync_outcome = await sync_incidents_from_results(repo, snapshot.results)
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

            # Diagnosis pump (spec pillar 4): pull-based, budget-capped,
            # best-effort — a broken LLM must not break the health tick.
            try:
                pending = await repo.incidents_needing_diagnosis(
                    settings.diagnostics_diagnosis_batch_size
                )
                if pending:
                    from src.domains.agents.prompts.prompt_loader import load_prompt

                    # `{language}` is left UNRESOLVED on purpose: the batch
                    # writes one variant per admin language and fills it there.
                    system_prompt = str(load_prompt("diagnostician_prompt")).replace(
                        "{max_actions}", str(settings.diagnostics_diagnosis_max_actions)
                    )
                    diagnosed = await diagnose_incidents(
                        pending, db=db, system_prompt=system_prompt
                    )
                    if diagnosed:
                        await db.commit()
            except Exception:
                logger.exception("diagnostics_diagnosis_pump_failed")

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
            duration_seconds=round(time.monotonic() - started, 3),
        )
    except Exception:
        background_job_errors_total.labels(job_name=SCHEDULER_JOB_ID_DIAGNOSTICS_SELF_CHECK).inc()
        logger.exception("diagnostics_self_check_failed")
    finally:
        diagnostics_self_check_duration_seconds.observe(time.monotonic() - started)
