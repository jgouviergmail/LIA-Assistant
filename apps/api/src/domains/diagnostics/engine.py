"""Self-check engine: evaluate the registry into one health snapshot.

Runs on the scheduler leader only (the job wires it); Prometheus-backed checks
degrade to ``unknown`` when the source is unreachable while in-process probes
keep working — the engine can therefore still say "my own observability tier
is down". Probe failures never escape: for the reachability probes the
exception IS the signal, and only the exception CLASS NAME is recorded
(messages can carry hosts or credentials).
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime

import structlog
from sqlalchemy import text

from src.core.config import settings
from src.core.constants import REDIS_KEY_DIAGNOSTICS_SCHEDULER_TICK
from src.domains.diagnostics.checks import (
    IN_PROCESS_CHECKS,
    PROM_CHECKS,
    CheckResult,
    CheckStatus,
    overall_status,
)
from src.domains.diagnostics.query_catalogue import render_query
from src.infrastructure.telemetry.models import PromSample
from src.infrastructure.telemetry.prometheus import PrometheusClient

logger = structlog.get_logger(__name__)

#: Probe return shape: (status, value, detail).
ProbeOutcome = tuple[CheckStatus, float | None, str]


class HealthSnapshotDTO:
    """One self-check run: overall verdict plus per-check results."""

    def __init__(self, taken_at: datetime, results: list[CheckResult]) -> None:
        """Compute the overall verdict from the results.

        Args:
            taken_at: When the self-check ran (aware UTC).
            results: Per-check results.
        """
        self.taken_at = taken_at
        self.results = results
        self.overall = overall_status(results)

    def to_results_jsonb(self) -> list[dict[str, object]]:
        """Serialize results as plain dicts for the JSONB column.

        One-way by design: snapshots are read back as raw dicts by the admin
        API, never reconstructed into CheckResult objects.

        Returns:
            JSON-serializable per-check rows (exact measured values).
        """
        return [
            {
                "check_id": r.check_id,
                "status": r.status.value,
                "value": r.value,
                "detail": r.detail,
                "alertname": r.alertname,
            }
            for r in self.results
        ]


async def run_self_check(prom_client: PrometheusClient | None = None) -> HealthSnapshotDTO:
    """Evaluate every registered check and fold the verdicts.

    Args:
        prom_client: Injected Prometheus client (tests); defaults to one built
            from settings.

    Returns:
        The snapshot DTO (not yet persisted — the job owns persistence).
    """
    client = prom_client or PrometheusClient(
        base_url=settings.diagnostics_prometheus_url,
        timeout_seconds=settings.diagnostics_http_timeout_seconds,
    )
    results: list[CheckResult] = []

    # Sequential on purpose: five cheap instant queries at a 5-minute cadence
    # do not justify concurrency, and a plain loop keeps failure attribution
    # trivial (systemic rule: a handful of indexed queries — loop, not gather).
    for check in PROM_CHECKS:
        promql = render_query(check.query_id, **check.params)
        prom_result = await client.instant_query(promql)
        if prom_result.status != "ok":
            results.append(
                CheckResult(
                    check_id=check.check_id,
                    status=CheckStatus.UNKNOWN,
                    value=None,
                    detail=prom_result.error or "unavailable",
                    alertname=check.alertname,
                )
            )
            continue
        value = _scalar_from_samples(prom_result.samples)
        if value is None:
            results.append(
                CheckResult(
                    check_id=check.check_id,
                    status=CheckStatus.UNKNOWN,
                    value=None,
                    detail="no_data",
                    alertname=check.alertname,
                )
            )
            continue
        warn = float(getattr(settings, check.warn_setting))
        crit = float(getattr(settings, check.crit_setting))
        if value >= crit:
            status = CheckStatus.CRITICAL
        elif value >= warn:
            status = CheckStatus.DEGRADED
        else:
            status = CheckStatus.OK
        results.append(
            CheckResult(
                check_id=check.check_id,
                status=status,
                value=value,
                detail="",
                alertname=check.alertname,
            )
        )

    probes = {
        "database": _probe_database,
        "redis": _probe_redis,
        "circuit_breakers": _probe_circuit_breakers,
        "scheduler_tick": _probe_scheduler_tick,
    }
    for check_def in IN_PROCESS_CHECKS:
        probe = probes[check_def.check_id]
        try:
            status, value, detail = await probe()
        except Exception as exc:
            # The exception IS the signal for reachability probes; only the
            # class name is recorded (messages can carry hosts/credentials).
            status, value, detail = CheckStatus.CRITICAL, None, type(exc).__name__
        results.append(
            CheckResult(
                check_id=check_def.check_id,
                status=status,
                value=value,
                detail=detail,
                alertname=check_def.alertname,
            )
        )

    return HealthSnapshotDTO(taken_at=datetime.now(UTC), results=results)


def _scalar_from_samples(samples: list[PromSample]) -> float | None:
    """First finite sample value, or None (no data / NaN / infinity)."""
    for sample in samples:
        value = float(sample.value)
        if math.isfinite(value):
            return value
    return None


async def _probe_database() -> ProbeOutcome:
    """SELECT 1 through a fresh session (own session per probe — repo rule)."""
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        await db.execute(text("SELECT 1"))
    return CheckStatus.OK, None, ""


async def _probe_redis() -> ProbeOutcome:
    """PING the cache client."""
    from src.infrastructure.cache.redis import get_redis_cache

    redis = await get_redis_cache()
    await redis.ping()
    return CheckStatus.OK, None, ""


async def _probe_circuit_breakers() -> ProbeOutcome:
    """Count open breakers (this worker's view — the one that serves runs)."""
    from src.infrastructure.resilience.circuit_breaker import CircuitBreakerRegistry

    statuses = CircuitBreakerRegistry.get_all_status()
    open_services = sorted(
        service for service, status in statuses.items() if status.get("state") == "open"
    )
    if open_services:
        return (
            CheckStatus.DEGRADED,
            float(len(open_services)),
            ",".join(open_services[:10]),
        )
    return CheckStatus.OK, 0.0, ""


async def _probe_scheduler_tick() -> ProbeOutcome:
    """Age of the last self-check tick (written by the job after each run)."""
    from src.infrastructure.cache.redis import get_redis_cache

    redis = await get_redis_cache()
    raw = await redis.get(REDIS_KEY_DIAGNOSTICS_SCHEDULER_TICK)
    if raw is None:
        # Fresh boot / first run: no tick yet is absence of history, not an
        # outage — the check reports blindness, never invents one.
        return CheckStatus.UNKNOWN, None, "no_tick_recorded"
    age_seconds = time.time() - float(raw)
    if age_seconds > settings.diagnostics_check_scheduler_tick_stale_seconds:
        return CheckStatus.CRITICAL, age_seconds, "stale_tick"
    return CheckStatus.OK, age_seconds, ""
