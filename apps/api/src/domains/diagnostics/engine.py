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
import socket
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _EgressAttempt:
    """One name resolution then TCP connect, each phase timed in milliseconds.

    ``failure`` names the phase that failed and how (``None`` when the target
    was reached); the durations of a failed attempt are not read.
    """

    failure: str | None
    resolve_ms: float = 0.0
    connect_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        """Duration of the whole attempt, the value the check reports."""
        return round(self.resolve_ms + self.connect_ms, 1)


async def _probe_platform_egress() -> ProbeOutcome:
    """Can this instance still open a connection to the outside at all?

    Born from the 2026-08-28 outage: ``net.ipv4.ip_forward`` fell to 0 on the
    host, every container lost outbound routing, and the platform could only
    report the CONSEQUENCE — 100 % LLM failures, two open circuit breakers —
    while the cause stayed invisible for four hours. DNS kept resolving (the
    container resolver needs no forwarding) and the host itself reached the
    internet fine, so every intuitive test exonerated a broken platform.

    Each attempt is a name resolution then a TCP connect — no TLS, no request:
    this measures reachability, never a third party's health, and it borrows no
    credentials. The phases are named apart because they fail apart (ADR-361):
    Docker's embedded resolver waits 4 s before failing over to its next DNS
    server, so a datagram lost twice used to consume a single 5 s attempt and
    read « unreachable » for a platform whose connection was never even tried.
    A loss is therefore confirmed over paced attempts before it is critical.

    Returns:
        ``ok`` with the attempt's duration in milliseconds; ``degraded`` when the
        target was reached only after a failed attempt or slower than
        ``DIAGNOSTICS_EGRESS_PROBE_SLOW_SECONDS``; ``critical`` when every attempt
        failed; ``unknown`` when the target is unreadable.
    """
    target = str(getattr(settings, "diagnostics_egress_probe_target", "") or "").strip()
    parsed = _parse_egress_target(target)
    if parsed is None:
        # A typo in the setting must never read as "the platform is cut off".
        return CheckStatus.UNKNOWN, None, f"malformed target '{target}'"
    host, port = parsed

    budget = float(settings.diagnostics_egress_probe_timeout_seconds)
    attempts = int(settings.diagnostics_egress_probe_attempts)
    failures: list[str] = []
    for number in range(1, attempts + 1):
        slot_started = time.monotonic()
        attempt = await _egress_attempt(host, port, budget)
        if attempt.failure is None:
            return _egress_success(target, attempt, failures, number, attempts)
        failures.append(attempt.failure)
        if number < attempts:
            # A fast failure waits out its slot, so N attempts span (N - 1)
            # budgets: a loss shorter than that is a hiccup, not a cut.
            await asyncio.sleep(max(0.0, budget - (time.monotonic() - slot_started)))

    plural = "s" if attempts > 1 else ""
    reasons = "; ".join(dict.fromkeys(failures))
    return (
        CheckStatus.CRITICAL,
        None,
        f"{target} unreachable after {attempts} attempt{plural}: {reasons}",
    )


def _parse_egress_target(target: str) -> tuple[str, int] | None:
    """Split ``host:port``, stripping the brackets of an IPv6 literal.

    Args:
        target: The configured probe target.

    Returns:
        ``(host, port)``, or ``None`` when the target is unreadable.
    """
    host, separator, port_text = target.rpartition(":")
    if host.startswith("[") and host.endswith("]"):
        # `[::1]:443` is the standard spelling for an IPv6 literal, but
        # getaddrinfo does not accept the brackets: Linux raises `gaierror`
        # (measured in CI 2026-08-28) where Windows tolerated them — so an IPv6
        # target would have been reported as "the platform is cut off" on the
        # very platform that runs in production.
        host = host[1:-1]
    port = int(port_text) if port_text.isdigit() else 0
    if not separator or not host or not 1 <= port <= 65535:
        return None
    return host, port


async def _egress_attempt(host: str, port: int, budget: float) -> _EgressAttempt:
    """Resolve then connect within one budget, naming the phase that failed.

    The resolution goes through the running loop's resolver — the one every
    outbound call of the process uses. A resolution cancelled by its timeout
    keeps its executor thread until the system resolver gives up; attempts are
    sequential, so at most one such thread per attempt.

    Args:
        host: Host name or IP literal (no brackets).
        port: TCP port.
        budget: Seconds for both phases together.

    Returns:
        The attempt: its failure (phase and exception class only — a message can
        carry hosts), or the durations of both phases.
    """
    loop = asyncio.get_running_loop()
    started = time.monotonic()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=budget
        )
    except TimeoutError:
        return _EgressAttempt(failure="name resolution timed out")
    except OSError as exc:
        return _EgressAttempt(failure=f"name resolution failed ({type(exc).__name__})")
    resolved = time.monotonic()
    # A slow resolution leaves the connect what is left of the budget: say how
    # much it took, or a connect starved by the resolver reads as the culprit.
    resolve_ms = round((resolved - started) * 1000, 1)

    writer: asyncio.StreamWriter | None = None
    try:
        _reader, writer = await asyncio.wait_for(
            _connect_first([str(info[4][0]) for info in infos], port),
            timeout=max(0.0, budget - (resolved - started)),
        )
        # Stop the clock HERE: the teardown below is not part of what we measure,
        # and a shown number is the measured number.
        connected = time.monotonic()
    except TimeoutError:
        return _EgressAttempt(
            failure=f"connect timed out (name resolution took {resolve_ms:.0f} ms)"
        )
    except OSError as exc:
        return _EgressAttempt(
            failure=f"connect failed ({type(exc).__name__}, "
            f"name resolution took {resolve_ms:.0f} ms)"
        )
    finally:
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    return _EgressAttempt(
        failure=None,
        resolve_ms=resolve_ms,
        connect_ms=round((connected - resolved) * 1000, 1),
    )


async def _connect_first(
    addresses: list[str], port: int
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Open a connection to the first address that accepts, in resolver order.

    The order ``open_connection`` follows when it resolves a name itself, so the
    split into two phases changes what is named, never which address is tried.

    Args:
        addresses: Resolved addresses, in the resolver's preference order.
        port: TCP port.

    Returns:
        The stream pair of the first address that accepted.

    Raises:
        OSError: When no address accepted (the last refusal is re-raised).
    """
    last_error: OSError = OSError("the resolver returned no address")
    for address in addresses:
        try:
            return await asyncio.open_connection(address, port)
        except OSError as exc:
            last_error = exc
    raise last_error


def _egress_success(
    target: str,
    attempt: _EgressAttempt,
    failures: list[str],
    number: int,
    attempts: int,
) -> ProbeOutcome:
    """The verdict of a reached target: clean, or reached but not cleanly.

    Args:
        target: The configured target, for the detail.
        attempt: The successful attempt.
        failures: What the earlier attempts of this tick ran into.
        number: Which attempt succeeded (1-based).
        attempts: How many attempts the tick allowed.

    Returns:
        ``ok`` with the target as detail, or ``degraded`` with what was seen.
    """
    timing = f"name resolution {attempt.resolve_ms:.0f} ms, connect {attempt.connect_ms:.0f} ms"
    if failures:
        reasons = "; ".join(dict.fromkeys(failures))
        detail = f"{target} reached on attempt {number}/{attempts} ({timing}) after: {reasons}"
        return CheckStatus.DEGRADED, attempt.total_ms, detail
    if attempt.total_ms >= float(settings.diagnostics_egress_probe_slow_seconds) * 1000:
        return CheckStatus.DEGRADED, attempt.total_ms, f"{target} reached slowly: {timing}"
    return CheckStatus.OK, attempt.total_ms, target


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
