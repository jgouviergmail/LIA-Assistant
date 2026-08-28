"""Self-check engine: evaluate the registry into one health snapshot.

Runs on the scheduler leader only (the job wires it); Prometheus-backed checks
degrade to ``unknown`` when the source is unreachable while in-process probes
keep working — the engine can therefore still say "my own observability tier
is down". Probe failures never escape: for the reachability probes the
exception IS the signal, and only the exception CLASS NAME is recorded
(messages can carry hosts or credentials).
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
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
    InProcessCheck,
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

    probes = probe_registry()
    for check_def in IN_PROCESS_CHECKS:
        if check_def.enabled_setting and not getattr(settings, check_def.enabled_setting, None):
            # Not configured: the check is ABSENT, not green. See InProcessCheck.
            continue
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


def probe_registry() -> dict[str, Callable[[], Awaitable[ProbeOutcome]]]:
    """The in-process probes, by check id — built at call time on purpose.

    One definition, two readers: ``run_self_check`` dispatches through it and
    ``assert_probe_coverage`` compares its keys with the registry. Late binding
    (rebuilt per call) is what lets a test substitute a probe by name.

    Returns:
        Mapping of ``check_id`` to the coroutine function evaluating it.
    """
    return {
        "database": _probe_database,
        "redis": _probe_redis,
        "circuit_breakers": _probe_circuit_breakers,
        "scheduler_tick": _probe_scheduler_tick,
        "platform_egress": _probe_platform_egress,
    }


def assert_probe_coverage(
    in_process_checks: tuple[InProcessCheck, ...] | None = None,
) -> None:
    """Refuse to boot when a registered check has no probe, or vice versa.

    ``run_self_check`` looks the probe up by ``check_id``: a missing entry is a
    ``KeyError`` that kills the whole tick — no snapshot, no verdict, and the
    only trace is a scheduler error nobody reads. The reverse (a probe no check
    declares) is dead code that fakes coverage. ADR-085 doctrine.

    Args:
        in_process_checks: Override for tests; defaults to the real registry.

    Raises:
        AssertionError: A check has no probe, or a probe has no check.
    """
    checks = in_process_checks if in_process_checks is not None else IN_PROCESS_CHECKS
    declared = {check.check_id for check in checks}
    implemented = set(probe_registry())
    missing = declared - implemented
    orphans = implemented - declared
    assert not missing, f"in-process checks with no probe: {sorted(missing)}"
    assert not orphans, f"probes with no check declaring them: {sorted(orphans)}"


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


async def _probe_platform_egress() -> ProbeOutcome:
    """Can this instance still open a connection to the outside at all?

    Born from the 2026-08-28 outage: ``net.ipv4.ip_forward`` fell to 0 on the
    host, every container lost outbound routing, and the platform could only
    report the CONSEQUENCE — 100 % LLM failures, two open circuit breakers —
    while the cause stayed invisible for four hours. DNS kept resolving (the
    container resolver needs no forwarding) and the host itself reached the
    internet fine, so every intuitive test exonerated a broken platform.

    One bounded TCP connect, no TLS and no request: this measures reachability,
    never a third party's health, and it borrows no credentials.

    Returns:
        ``ok`` with the connect duration in milliseconds, ``critical`` when the
        target cannot be reached, ``unknown`` when the target is unreadable.
    """
    target = str(getattr(settings, "diagnostics_egress_probe_target", "") or "").strip()
    host, separator, port_text = target.rpartition(":")
    port = int(port_text) if port_text.isdigit() else 0
    if not separator or not host or not 1 <= port <= 65535:
        # A typo in the setting must never read as "the platform is cut off".
        return CheckStatus.UNKNOWN, None, f"malformed target '{target}'"

    timeout = float(settings.diagnostics_egress_probe_timeout_seconds)
    started = time.monotonic()
    writer: asyncio.StreamWriter | None = None
    elapsed_ms = 0.0
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        # Stop the clock HERE: the teardown below is not part of what we measure,
        # and a shown number is the measured number.
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    except (TimeoutError, OSError) as exc:
        # The exception IS the signal; only its class name is recorded.
        return CheckStatus.CRITICAL, None, f"{target} unreachable ({type(exc).__name__})"
    finally:
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    return CheckStatus.OK, elapsed_ms, target


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
